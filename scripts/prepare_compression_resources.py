"""Prepare pinned LLMLingua assets explicitly; serving never downloads them.

Run inside the backend container, using the same HF_HUB_CACHE as serving.
Default is offline verification. --download is an operator action, never CI.
"""

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

REPOSITORY = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
REVISION = "5f0c82792b7ea14c6484e015b6a072009496b7f2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = Path(
        snapshot_download(
            REPOSITORY,
            revision=REVISION,
            local_files_only=not args.download,
            max_workers=2,
        )
    )
    # Verify a complete local snapshot even after an explicit download.
    snapshot_download(REPOSITORY, revision=REVISION, local_files_only=True)
    files = []
    for path in sorted(directory.iterdir()):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            files.append(
                {
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": digest.hexdigest(),
                }
            )
    weights = next(item for item in files if item["name"] == "model.safetensors")
    if (
        weights["sha256"]
        != "22b9ecde52fec5c97e8c54a293be768727df95a81c6c8dccb03f262a50c58324"
    ):
        raise ValueError("Pinned weights checksum mismatch")
    report = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "snapshot": str(directory),
        "verified_local_only": True,
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "revision": REVISION,
                "files": len(files),
                "bytes": sum(item["bytes"] for item in files),
                "verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
