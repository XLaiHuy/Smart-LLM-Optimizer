"""Deployed HTTP smoke using owned completed-request replays only; no new generation.

Verifies payload hash before replay; cannot introduce a new provider request.
Temporary login sessions are revoked in finally. No credentials are printed.
"""
import argparse
import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import httpx
from app.contracts.dtos import ChatRequest


def run(args):
    report={'provider_calls_created':0,'replay_only':True,'checks':[],'replays':[]}
    db=sqlite3.connect('/app/runtime-db/smartllm.db',timeout=30)
    tokens=[]
    def cookie(user_id):
        token=secrets.token_urlsafe(32)
        digest=hashlib.sha256(token.encode()).hexdigest()
        db.execute('INSERT INTO auth_sessions (token_hash,user_id,expires_at) VALUES (?,?,?)',(digest,user_id,(datetime.now(UTC)+timedelta(minutes=10)).isoformat()))
        db.commit();tokens.append(digest)
        return {'smartllm_session':token}
    def check(client,path,expected=200):
        response=client.get(path)
        assert response.status_code==expected,(path,response.status_code)
        report['checks'].append({'path':path,'status':response.status_code})
        return response
    try:
        admin=db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
        with httpx.Client(base_url=args.url,timeout=30,cookies=cookie(admin),follow_redirects=False) as client:
            check(client,'/api/v1/health/ready')
            runtime=check(client,'/api/v1/runtime-settings').json()
            assert [m['model_id'] for m in runtime['models']]==['openai/gpt-oss-20b','openai/gpt-oss-120b','gpt-6-luna']
            assert all(m['available'] for m in runtime['models'])
            report['runtime']=runtime
            usage=check(client,'/api/v1/usage?project=true').json()
            assert usage['reporting_epoch'] and usage['totals']['calls']==0 and usage['requests']==0
            report['accounting']={k:usage[k] for k in ('reporting_epoch','settled_usd','reserved_usd','available_usd')}
            export=check(client,'/api/v1/usage/export?project=true&format=csv')
            assert 'reporting_epoch' in export.text
            for path in ('/','/settings','/dashboard'): check(client,path)
            for path in ('/research','/pipeline','/research-guide'):
                response=client.get(path)
                assert response.status_code in (307,308) and response.headers['location']=='/'
                report['checks'].append({'path':path,'status':response.status_code,'redirect':'/'})
        directory=Path('/app/data/system-audit/fresh-memory-math-long-fixed-20261027')
        for name in ('activate_20b','activate_luna','fresh_unknown'):
            body=json.loads((directory/(name+'.request.json')).read_text())
            attempt=db.execute('SELECT id,owner_user_id,payload_hash,status FROM request_attempts WHERE client_request_id=? AND session_id=?',(body['client_request_id'],body['session_id'])).fetchone()
            assert attempt and attempt[3]=='succeeded'
            req=ChatRequest.model_validate(body)
            payload_hash=hashlib.sha256(json.dumps(req.model_dump(mode='json',exclude={'response_schema'} if req.response_schema is None else set()),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            assert payload_hash==attempt[2], 'Hash mismatch: stop before dispatch'
            with httpx.Client(base_url=args.url,timeout=30,cookies=cookie(attempt[1])) as client:
                start=perf_counter()
                response=client.post('/api/v1/chat',json=body)
                assert response.status_code==200,response.status_code
                data=response.json()
                assert data['request_id']==attempt[0]
                execution=check(client,'/api/v1/requests/'+attempt[0]+'/execution').json()
                assert execution['legacy'] and execution['status']=='succeeded'
                assert execution['route']['model_id']==data['route']['model_id']
                report['replays'].append({'case':name,'request_id':attempt[0],'model_id':data['route']['model_id'],'ml_executed':data['route']['ml_executed'],'attention_executed':data['route']['attention_executed'],'replay_http_ms':round((perf_counter()-start)*1000,2)})
            foreign=db.execute('SELECT id FROM users WHERE id != ? LIMIT 1',(attempt[1],)).fetchone()[0]
            with httpx.Client(base_url=args.url,timeout=30,cookies=cookie(foreign)) as other:
                check(other,'/api/v1/requests/'+attempt[0]+'/execution',404)
        report['passed']=True
    finally:
        for digest in tokens: db.execute('DELETE FROM auth_sessions WHERE token_hash=?',(digest,))
        db.commit();db.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report.get('passed',False),'http_checks':len(report['checks']),'chat_replays':len(report['replays']),'provider_calls_created':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://frontend:3000')
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
