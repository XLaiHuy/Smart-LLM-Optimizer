"""TRAIN-only option rotations from six arithmetically verified public parents.

Gold is verified arithmetic, not a guessed model-success label. Provider outcomes
are deliberately absent. Variants never increase independent group counts.
"""

import argparse
import json
import re
from pathlib import Path

from analyze_router_errors import load, surface_issues, write
from app.contracts.dtos import Message
from app.contracts.training import TrainingCorpus
from app.routing.ml.graders import arithmetic, numeric
from app.routing.ml.pilot import validate_corpus

PARENTS = {
    "0aea20c07d67ac49ccbe25134e08cb99de926ceea5ff393f395d07afcb8e9629": "-15/5",
    "1ec04afb482d196e6466199191c04443cb87d244e66a0b341329c5f2e9d99c19": "125-200",
    "2d7482a8118e237ca2e5644ad1320675df2109bebff57870ad2b704ee4bb05b6": "(-42)*(-5)",
    "5a148f6b12312c973b597283ea1885f3436480151952c138beeff3e105d3a571": "3*2+4+5-7+10",
    "ab250953b4f13aa61ba2cf9849618bd3355dfd68439e2eb485ed9284949c5998": "-909+909",
    "de6994dac3a9dba81b41fc6a2e2574fc1a714a0c56c9c1b94e78c4921421c499": "23-17",
}


def options(parent):
    parts = re.split(r"(?:^|\n)\s*([A-D])[.]\s*", parent.messages[0].content)
    if parts[1::2] != list("ABCD"):
        raise ValueError("Expected exactly four source options")
    values = [v.strip().split("\nChỉ trả lời", 1)[0].strip() for v in parts[2::2]]
    return parts[0].strip(), values


def rotate(parent, shift):
    if (
        parent.split != "train"
        or parent.grading is None
        or parent.grading.synthetic
        or shift not in (1, 2, 3)
    ):
        raise ValueError(
            "Only original TRAIN parents and nonidentity rotations allowed"
        )
    stem, values = options(parent)
    values = values[shift:] + values[:shift]
    gold = "ABCD"[("ABCD".index(parent.gold) - shift) % 4]
    prompt = (
        stem
        + "\n\n"
        + "\n\n".join(f"{c}. {v}" for c, v in zip("ABCD", values, strict=True))
    )
    prompt += "\nChỉ trả lời một chữ cái trong các lựa chọn."
    return parent.model_copy(
        update={
            "task_id": parent.task_id + f":rotate-{shift}",
            "messages": (Message(role="user", content=prompt),),
            "gold": gold,
            "grading": parent.grading.model_copy(
                update={
                    "synthetic": True,
                    "label_source": "synthetic_verified",
                    "parent_group_id": parent.group_id,
                }
            ),
        }
    )


def prepare(previous, supplemental, output):
    if output.exists():
        raise ValueError("Do not overwrite a frozen supplement")
    old = TrainingCorpus.model_validate(load(previous / "corpus.json"))
    fresh = TrainingCorpus.model_validate(load(supplemental / "corpus.json"))
    # Filter source input only, before looking at provider outcomes.
    retained = tuple(
        s
        for s in old.samples
        if s.split != "holdout" and not surface_issues(s.messages[-1].content)
    )
    retained += tuple(
        s for s in fresh.samples if not surface_issues(s.messages[-1].content)
    )
    proofs, variants = [], []
    for suffix, expression in PARENTS.items():
        parent = next(s for s in retained if s.task_id.endswith(suffix))
        _, values = options(parent)
        expected = arithmetic(expression)
        actual = [numeric(re.sub(r"[−–]\s*", "-", v)) for v in values]
        valid = ["ABCD"[i] for i, v in enumerate(actual) if v == expected]
        if valid != [parent.gold]:
            raise ValueError(
                "Parent must have exactly one independently verified answer"
            )
        proofs.append(
            {
                "parent_task_id": parent.task_id,
                "expression": expression,
                "verified_result": str(expected),
                "source_gold": parent.gold,
                "verification": "exact Decimal arithmetic and unique matching option; automated, not human review",
            }
        )
        variants.extend(rotate(parent, shift) for shift in (1, 2, 3))
    corpus = TrainingCorpus(samples=retained + tuple(variants))
    validate_corpus(corpus)
    output.mkdir(parents=True)
    (output / "prepared-dev-with-variants.json").write_text(
        corpus.model_dump_json(indent=2), encoding="utf-8"
    )
    write(output / "parent-arithmetic-proofs.json", proofs)
    write(
        output / "status.json",
        {
            "source_parent_groups": 6,
            "additional_prompt_variants": len(variants),
            "additional_independent_groups": 0,
            "prepared_dev_rows": len(corpus.samples),
            "independent_dev_groups": len({s.group_id for s in corpus.samples}),
            "model_success_labels_created": 0,
            "synthetic_in_calibration_threshold_or_holdout": False,
            "provider_outcomes": "not collected; do not train by fabricating pass/fail",
            "source_family_limitation": "Not a replacement for fresh independent Vietnamese MCQ tests",
        },
    )
    print(json.dumps(load(output / "status.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--supplemental", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.previous, args.supplemental, args.output)
