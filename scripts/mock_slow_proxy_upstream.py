"""Isolated slow upstream for production Docker proxy tests. No provider calls."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        time.sleep(body.get('delay', 0))
        status = body.get('status', 200)
        payload = {'ok': True, 'provider_calls': 0} if status == 200 else {'error': {'code': 'PROVIDER_TIMEOUT', 'message': 'Fake test timeout', 'request_id': 'fake-only', 'retry_after_seconds': None}}
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
