"""Snapshot installed lockfile packages' declared license metadata, not a legal verdict."""

import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inventory() -> dict:
    node = []
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for location, entry in sorted(lock["packages"].items()):
        if "node_modules/" not in location or entry.get("link"):
            continue
        name = location.rsplit("node_modules/", 1)[-1]
        installed = ROOT / location / "package.json"
        meta = (
            json.loads(installed.read_text(encoding="utf-8"))
            if installed.exists()
            else {}
        )
        node.append(
            {
                "name": name,
                "version": entry.get("version"),
                "declared_license": entry.get("license") or meta.get("license"),
                "source": location,
                "review_status": "metadata_only",
            }
        )
    python = []
    import re

    lock_text = (ROOT / "backend/requirements.lock").read_text(encoding="utf-8")
    for name, version in re.findall(
        r"^([a-zA-Z0-9_.-]+)==([^\s;]+)", lock_text, re.MULTILINE
    ):
        try:
            meta = importlib.metadata.metadata(name)
            classifiers = [
                v for v in meta.get_all("Classifier", []) if v.startswith("License ::")
            ]
            declared = meta.get("License-Expression") or meta.get("License")
            python.append(
                {
                    "name": name,
                    "version": version,
                    "declared_license": declared.splitlines()[0] if declared else None,
                    "license_classifiers": classifiers,
                    "review_status": "metadata_only",
                }
            )
        except importlib.metadata.PackageNotFoundError:
            python.append(
                {
                    "name": name,
                    "version": version,
                    "declared_license": None,
                    "review_status": "not_installed",
                }
            )
    return {
        "method": "Declared metadata for pinned dependencies; compatibility is not established by this inventory.",
        "node": node,
        "python": python,
    }


if __name__ == "__main__":
    output = ROOT / "docs/THIRD_PARTY_INVENTORY.json"
    output.write_text(
        json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output.relative_to(ROOT)}")
