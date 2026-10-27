"""Read-only comparison of migrated live DB against the pre-migration snapshot."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def rows(db, table, columns):
    projection=', '.join('"'+c+'"' for c in columns)
    return sorted((tuple(r) for r in db.execute(f'SELECT {projection} FROM "{table}"')), key=repr)


def verify(before, live, output):
    result={'integrity': None, 'protected_tables': {}, 'unchanged': True}
    with sqlite3.connect(before.as_uri()+'?mode=ro',uri=True) as old, sqlite3.connect(live.as_uri()+'?mode=ro',uri=True) as new:
        result['integrity']=new.execute('PRAGMA integrity_check').fetchone()[0]
        assert result['integrity']=='ok'
        result['revision']=new.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        assert result['revision']=='h108'
        for table in ('users', 'budget_reservations','usage_records','inference_calls','messages','sessions','request_attempts'):
            columns=[r[1] for r in old.execute(f'PRAGMA table_info("{table}")')]
            if not columns: continue
            left,right=rows(old,table,columns),rows(new,table,columns)
            same=left==right
            result['protected_tables'][table]={'rows_before':len(left),'rows_after':len(right),'identical_original_columns':same}
            result['unchanged'] &= same
        result['epochs']=[dict(zip(('id','started_at'),r)) for r in new.execute('SELECT id,started_at FROM analytics_epochs')]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    assert result['unchanged'], 'Existing data changed; inspect before further deployment'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--live',type=Path,default=Path('/app/runtime-db/smartllm.db'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verify(args.before.resolve(),args.live.resolve(),args.output.resolve())
