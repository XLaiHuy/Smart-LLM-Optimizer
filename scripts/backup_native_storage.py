"""Consistent SQLite backup inside the service container; never copies WAL files.

Operator command only. Writes a verified backup plus an accounting fingerprint.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def fingerprint(db):
    result = {}
    for table in ('budget_reservations', 'usage_records', 'inference_calls', 'messages', 'sessions', 'request_attempts'):
        columns = db.execute(f'PRAGMA table_info({table})').fetchall()
        if not columns:
            continue
        rows = sorted((tuple(row) for row in db.execute(f'SELECT * FROM {table}')), key=repr)
        result[table] = {'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}
    return result


def backup(source, target):
    if target.exists():
        raise ValueError('Backup path already exists')
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30) as src:
        with sqlite3.connect(target) as dest:
            src.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity failed')
            manifest = {'created_at': datetime.now(UTC).isoformat(), 'source': str(source), 'backup': str(target), 'integrity': 'ok', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'protected_tables': fingerprint(dest), 'revision': dest.execute('SELECT version_num FROM alembic_version').fetchone()[0]}
    target.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('/app/runtime-db/smartllm.db'))
    parser.add_argument('--target', type=Path, required=True)
    args=parser.parse_args()
    backup(args.source.resolve(), args.target.resolve())
