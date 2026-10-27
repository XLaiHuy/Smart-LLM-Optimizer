"""Local private handoff only. Never prints secret contents or uploads anything."""

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / "handoff-private/smartllm-linux-private-20261027.zip"
    if target.exists():
        raise ValueError("Private archive already exists; inspect instead of overwriting")
    backup = ROOT / "data/backups/pre-global-thresholds-0690085-071-20261027.sqlite3"
    with sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity failed")
        counts = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in ("users", "sessions", "messages", "usage_records", "documents")}
    # This is the verified SQLite backup, NEVER the damaged host smartllm.db.
    files = [(ROOT / ".env", ".env.source-private"),
             (ROOT / "config/models.json", "config/models.json"),
             (backup, "data/smartllm.db"),
             (backup.with_suffix(".manifest.json"), "database-backup.manifest.json")]
    env = (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
    replacements = {"DATABASE_PATH": "data/smartllm.db", "UPLOAD_DIRECTORY": "data/uploads",
                    "MODEL_CATALOG_PATH": "config/models.json", "SMARTLLM_ROOT": ".",
                    "RESEARCH_LIVE_ENABLED": "false"}
    updated, seen = [], set()
    for line in env:
        key = line.partition("=")[0]
        if key in replacements:
            line = key + "=" + replacements[key]
            seen.add(key)
        updated.append(line)
    updated.extend(k + "=" + v for k, v in replacements.items() if k not in seen)
    for folder in ("data/uploads", "data/router-assets", "data/tokenizer"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file():
                files.append((path, path.relative_to(ROOT).as_posix()))
    # Windows sees Linux HF symlinks as zero-byte placeholders. Reconstruct
    # portable regular snapshot files from Git-blob or SHA256 blob identity.
    hub = ROOT / "data/huggingface/hub/models--microsoft--llmlingua-2-bert-base-multilingual-cased-meetingbank"
    mapping = {}
    blobs = list((hub / "blobs").iterdir())
    for blob in blobs:
        if blob.is_file():
            mapping[blob.name] = blob
    # Pin mapping by recognizable file structure rather than copying placeholders.
    names = {}
    for name, blob in mapping.items():
        if len(name) == 64:
            names["model.safetensors"] = blob
            continue
        data = blob.read_bytes()
        if data.startswith(b"version https://git-lfs"):
            continue
        try:
            doc = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            names["README.md" if b"---" in data[:8] else "vocab.txt"] = blob
            continue
        if "model_type" in doc:
            names["config.json"] = blob
        elif "model" in doc and "normalizer" in doc:
            names["tokenizer.json"] = blob
        elif "tokenizer_class" in doc:
            names["tokenizer_config.json"] = blob
        elif "unk_token" in doc:
            names["special_tokens_map.json"] = blob
    required = {"model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt"}
    if not required <= names.keys():
        raise ValueError("Incomplete portable compressor assets")
    revision = "5f0c82792b7ea14c6484e015b6a072009496b7f2"
    for name, path in names.items():
        files.append((path, f"{hub.relative_to(ROOT).as_posix()}/snapshots/{revision}/{name}"))
    target.parent.mkdir(exist_ok=True)
    manifest = {"contains_secrets": True, "database_source": str(backup.relative_to(ROOT)),
                "database_counts": counts, "snapshot_time": "2026-10-27T15:53:34.663136+00:00",
                "note": "Verified point-in-time database backup; no WAL/SHM, old corrupt DB or paid jobs included.",
                "files": []}
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path, name in files:
            digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
            archive.write(path, name)
            manifest["files"].append({"path": name, "bytes": path.stat().st_size, "sha256": digest})
        archive.writestr(".env", "\n".join(updated) + "\n")
        archive.write(ROOT / "docs/LINUX_LAB_HANDOFF.md", "LINUX_LAB_HANDOFF.md")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError("ZIP integrity failed: " + bad)
    print(json.dumps({"archive": str(target), "bytes": target.stat().st_size,
                      "sha256": hashlib.file_digest(target.open("rb"), "sha256").hexdigest(),
                      "contains_secrets": True, "database_counts": counts}))


if __name__ == "__main__":
    main()
