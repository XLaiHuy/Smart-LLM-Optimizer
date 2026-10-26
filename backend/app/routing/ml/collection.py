"""Pinned public JSON collection and deterministic source-group splits."""

import ast
import builtins
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.training import GradingSpec, RawTrainingSample, TrainingCorpus, TrainingSource

MAX_SOURCE_BYTES = 20 * 1024 * 1024


def source_path(source: TrainingSource) -> Path:
    path = Path(source.local_path)
    return path if path.is_absolute() else ROOT / path


async def collect_source(source: TrainingSource, remote: bool) -> bytes:
    path = source_path(source)
    if remote:
        if (
            not source.hf_repo
            or not re.fullmatch(r"[\w.-]+/[\w.-]+", source.hf_repo)
            or not source.hf_revision
            or not re.fullmatch(r"[a-f0-9]{40}", source.hf_revision)
            or not source.hf_file
            or ".." in source.hf_file.split("/")
            or source.hf_file.startswith("/")
        ):
            raise ValueError("HF_SOURCE_NOT_PINNED")
        url = f"https://huggingface.co/datasets/{source.hf_repo}/resolve/{source.hf_revision}/{quote(source.hf_file, safe='/')}"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_SOURCE_BYTES:
                        raise ValueError("SOURCE_TOO_LARGE")
                raw = bytes(chunks)
    else:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("SOURCE_TOO_LARGE")
        raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.sha256:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if remote:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".download")
        temp.write_bytes(raw)
        temp.replace(path)
    return raw


def group_split(group: str) -> Literal["train", "calibration", "threshold", "holdout"]:
    bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 100
    return (
        "train"
        if bucket < 50
        else "calibration"
        if bucket < 70
        else "threshold"
        if bucket < 85
        else "holdout"
    )


def parse_corpus(raw: bytes, source: TrainingSource, limit: int = 2000) -> TrainingCorpus:
    try:
        document: Any = json.loads(raw)
    except json.JSONDecodeError:
        if source.adapter == "canonical":
            raise
        document = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if source.adapter == "canonical":
        return TrainingCorpus.model_validate({**document, "samples": document["samples"][:limit]})
    samples = []
    if source.adapter in {"gsm8k", "mbpp", "aya"}:
        rows = document if isinstance(document, list) else document["data"]
        if source.adapter == "aya":
            # Do not truncate Aya by file order.  The source contains many
            # Vietnamese rows; choose a deterministic hash-spread subset from
            # the complete source before constructing the capped corpus.
            rows = [row for row in rows if row.get("language_code") == "vie"]
            rows = sorted(
                rows,
                key=lambda row: hashlib.sha256(
                    str(row.get("inputs", "")).encode("utf-8")
                ).hexdigest(),
            )[:limit]
        for row in rows:
            identity_prompt = None
            if source.adapter == "gsm8k":
                prompt = str(row["question"]).strip() + "\nGive only the final numeric answer."
                gold = str(row["answer"]).rsplit("####", 1)[-1].strip()
                grading = GradingSpec(kind="numeric")
                domain = "math_reasoning"
            elif source.adapter == "mbpp":
                prompt = (
                    str(row["text"]).strip()
                    + "\nReturn complete Python code defining the requested function."
                )
                gold = "Pass all pinned source tests."
                grading = GradingSpec(
                    kind="code",
                    tests=tuple(row["test_list"]),
                    test_setup=str(row.get("test_setup_code") or ""),
                    docker_image=row.get("docker_image"),
                )
                identity_prompt = prompt
                # The callable name is an interface, not a hidden test answer.
                # Without it MBPP often asks for a function without specifying
                # the exact name expected by the evaluator.
                names = sorted(
                    {
                        node.func.id
                        for test in grading.tests
                        for node in ast.walk(ast.parse(test))
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id not in vars(builtins)
                    }
                )
                if not names:
                    raise ValueError("MBPP callable interface missing")
                prompt += "\nRequired callable name(s): " + ", ".join(names) + "."
                domain = "coding_algorithms"
            else:
                prompt, gold = str(row["inputs"]).strip(), str(row["targets"]).strip()
                grading = GradingSpec(kind="open")
                domain = "dialogue_chat"
            if not prompt or not gold or len(prompt.encode()) > 12000 or len(gold.encode()) > 12000:
                continue
            group = (
                source.adapter
                + ":"
                + hashlib.sha256((identity_prompt or prompt).encode()).hexdigest()
            )
            samples.append(
                RawTrainingSample(
                    task_id=group,
                    group_id=group,
                    domain=domain,
                    split=group_split(group),
                    messages=(Message(role="user", content=prompt),),
                    gold=gold,
                    grading=grading,
                )
            )
        return TrainingCorpus(samples=tuple(samples[:limit]))
    if source.adapter == "vmlu":
        rows = document if isinstance(document, list) else document["data"]
        for row in rows:
            question = row["question"]
            choices = row["choices"]
            answer = str(row["answer"]).strip().upper()
            if not 2 <= len(choices) <= 26 or answer not in tuple(
                chr(65 + i) for i in range(len(choices))
            ):
                raise ValueError("VMLU_SCHEMA_INVALID")
            group = "vmlu:" + hashlib.sha256(question.strip().encode()).hexdigest()
            choice_text = "\n".join(
                chr(65 + i) + ". " + re.sub(r"^[A-Z][.)]\s*", "", c) for i, c in enumerate(choices)
            )
            samples.append(
                RawTrainingSample(
                    task_id=str(row["id"]),
                    group_id=group,
                    domain=str(row.get("subject", "vmlu")),
                    split=group_split(group),
                    messages=(
                        Message(
                            role="user",
                            content=f"{question}\n{choice_text}\nKết luận bằng chữ cái đáp án.",
                        ),
                    ),
                    gold=answer,
                    grading=GradingSpec(
                        kind="mcq", choices=tuple(chr(65 + i) for i in range(len(choices)))
                    ),
                )
            )
    else:
        for article in document["data"]:
            document_id = article.get("title") or json.dumps(
                [p["context"] for p in article["paragraphs"]], ensure_ascii=False
            )
            group = "viquad:" + hashlib.sha256(document_id.strip().encode()).hexdigest()
            for paragraph in article["paragraphs"]:
                context = paragraph["context"]
                # Keep every paragraph/question from a document in the same split.
                for qa in paragraph["qas"]:
                    impossible = qa.get("is_impossible", False)
                    answers = [a["text"] for a in qa["answers"]]
                    if not impossible and not answers:
                        raise ValueError("VIQUAD_MISSING_GOLD")
                    samples.append(
                        RawTrainingSample(
                            task_id=str(qa["id"]),
                            group_id=group,
                            domain="viquad2_unanswerable" if impossible else "viquad2",
                            split=group_split(group),
                            messages=(
                                Message(
                                    role="user",
                                    content=f"Untrusted document evidence:\n{context}\n\nCâu hỏi: {qa['question']}\nTrả lời ngắn; nếu thiếu bằng chứng, nói không có thông tin.",
                                ),
                            ),
                            gold=json.dumps(
                                {"is_impossible": impossible, "answers": answers},
                                ensure_ascii=False,
                            ),
                            has_rag_context=True,
                            grading=GradingSpec(kind="extractive_qa"),
                        )
                    )
    return TrainingCorpus(samples=tuple(samples[:limit]))
