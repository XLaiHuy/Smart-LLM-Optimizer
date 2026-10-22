"""Download real, published Vietnamese benchmarks with official ground-truth labels.

Sources:
1. tridm/VMLU (Multi-disciplinary MCQ: STEM, Humanities, Law, Medicine)
   Ground-truth: official 'answer' key ('A', 'B', 'C', 'D')
2. taidng/UIT-ViQuAD2.0 (Reading comprehension & Grounded RAG)
   Ground-truth: official 'answers.text' extracted spans & 'is_impossible'

Creates:
- data/benchmarks/real_benchmark_50.json  (Quick evaluation)
- data/benchmarks/real_benchmark_200.json (Standard evaluation)
- data/benchmarks/real_benchmark_600.json (Holdout / Full evaluation)
"""

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "benchmarks"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_vmlu(limit: int) -> list[dict]:
    print(f"Fetching {limit} samples from tridm/VMLU (Hugging Face)...")
    results = []
    offset = 0
    batch_size = 100
    while len(results) < limit:
        needed = min(batch_size, limit - len(results))
        url = f"https://datasets-server.huggingface.co/rows?dataset=tridm/VMLU&config=default&split=train&offset={offset}&limit={needed}"
        resp = requests.get(url, timeout=25)
        if resp.status_code != 200:
            print(f"Error fetching VMLU offset {offset}: {resp.status_code}")
            break
        rows = resp.json().get("rows", [])
        if not rows:
            break
        for item in rows:
            row = item["row"]
            ans = row.get("answer")
            if not ans:
                continue
            choices = row.get("choices", [])
            choice_str = "\n".join(
                [f"{chr(65 + i)}. {c}" for i, c in enumerate(choices[:4])]
            )
            formatted_q = f"Câu hỏi:\n{row['question']}\n\nCác lựa chọn:\n{choice_str}\n\nHãy suy luận ngắn gọn và kết luận bằng chữ cái đáp án đúng (A, B, C, hoặc D) ở dòng cuối theo định dạng: Đáp án: X"
            results.append(
                {
                    "task_id": f"vmlu-{row.get('id', len(results) + 1)}",
                    "benchmark": "tridm/VMLU",
                    "domain": "vmlu_multidisciplinary_mcq",
                    "question": row["question"],
                    "choices": choices[:4],
                    "formatted_prompt": formatted_q,
                    "ground_truth": ans.strip().upper(),
                    "grader_type": "mcq_letter",
                    "source_split": "train",
                }
            )
            if len(results) >= limit:
                break
        offset += len(rows)
    print(f"-> Fetched {len(results)} valid VMLU samples with ground truth.")
    return results


def fetch_viquad(limit: int) -> list[dict]:
    print(f"Fetching {limit} samples from taidng/UIT-ViQuAD2.0 (Hugging Face)...")
    results = []
    offset = 0
    batch_size = 100
    while len(results) < limit:
        needed = min(batch_size, limit - len(results))
        url = f"https://datasets-server.huggingface.co/rows?dataset=taidng/UIT-ViQuAD2.0&config=default&split=train&offset={offset}&limit={needed}"
        resp = requests.get(url, timeout=25)
        if resp.status_code != 200:
            print(f"Error fetching ViQuAD offset {offset}: {resp.status_code}")
            break
        rows = resp.json().get("rows", [])
        if not rows:
            break
        for item in rows:
            row = item["row"]
            answers = row.get("answers", {}).get("text", [])
            is_impossible = row.get("is_impossible", False)
            if not answers and not is_impossible:
                continue
            context = row.get("context", "")
            q = row.get("question", "")
            formatted_q = f"Đoạn văn bản tham khảo:\n{context}\n\nDựa vào đoạn văn bản trên, hãy trả lời câu hỏi sau một cách chính xác, ngắn gọn và trung thực:\n{q}"
            results.append(
                {
                    "task_id": f"viquad-{row.get('id', len(results) + 1)}",
                    "benchmark": "taidng/UIT-ViQuAD2.0",
                    "domain": "viquad_reading_comprehension",
                    "title": row.get("title", ""),
                    "context": context,
                    "question": q,
                    "formatted_prompt": formatted_q,
                    "ground_truth": answers,
                    "is_impossible": is_impossible,
                    "grader_type": "token_f1_exact_match",
                    "source_split": "train",
                }
            )
            if len(results) >= limit:
                break
        offset += len(rows)
    print(f"-> Fetched {len(results)} valid UIT-ViQuAD samples with ground truth.")
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Downloading Real Benchmark Datasets with Verified Ground Truth ===")

    # Target counts:
    # 50:  25 VMLU + 25 ViQuAD
    # 200: 100 VMLU + 100 ViQuAD
    # 600: 300 VMLU + 300 ViQuAD

    total_needed = 300
    all_vmlu = fetch_vmlu(total_needed)
    all_viquad = fetch_viquad(total_needed)

    for count, (vmlu_n, viquad_n) in [
        (50, (25, 25)),
        (200, (100, 100)),
        (600, (300, 300)),
    ]:
        subset_vmlu = all_vmlu[:vmlu_n]
        subset_viquad = all_viquad[:viquad_n]
        combined = []
        # Interleave
        for i in range(max(len(subset_vmlu), len(subset_viquad))):
            if i < len(subset_vmlu):
                combined.append(subset_vmlu[i])
            if i < len(subset_viquad):
                combined.append(subset_viquad[i])

        out_file = OUT_DIR / f"real_benchmark_{count}.json"
        payload = {
            "version": "1.0.0",
            "purpose": "scientific_benchmark",
            "provenance": {
                "vmlu": "https://huggingface.co/datasets/tridm/VMLU",
                "uit_viquad": "https://huggingface.co/datasets/taidng/UIT-ViQuAD2.0",
            },
            "total_samples": len(combined),
            "vmlu_count": len(subset_vmlu),
            "viquad_count": len(subset_viquad),
            "samples": combined,
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"-> Created {out_file} ({len(combined)} samples)")

    print(
        "\n[SUCCESS] All authentic benchmark datasets prepared with official ground truths!"
    )


if __name__ == "__main__":
    main()
