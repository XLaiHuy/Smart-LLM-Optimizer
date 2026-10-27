"""Check the built production proxy past its former 30-second cutoff, no paid API."""
import argparse
import json
from pathlib import Path
from time import perf_counter

import httpx


def run(args):
    report={'provider_calls':0,'scope':'isolated_production_docker_proxy','cases':[]}
    with httpx.Client(base_url=args.url,timeout=145) as client:
        for delay,status in ((36,200),(32,504)):
            start=perf_counter()
            response=client.post('/api/v1/chat',json={'delay':delay,'status':status})
            elapsed=perf_counter()-start
            assert response.status_code==status,(response.status_code,response.text[:200])
            data=response.json()
            if status==504: assert data['error']['code']=='PROVIDER_TIMEOUT'
            report['cases'].append({'delay_seconds':delay,'http_status':status,'elapsed_seconds':round(elapsed,3),'json_delivered':True})
            print(json.dumps(report['cases'][-1]),flush=True)
    report['passed']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://localhost:3002')
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
