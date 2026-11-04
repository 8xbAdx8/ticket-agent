"""Two client processes, one leased authority; secrets never cross IPC."""
from concurrent.futures import ProcessPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import json,urllib.request,urllib.error
from tests.v39.test_service import sim

def client(args):
    url,pid=args
    req=urllib.request.Request(url,data=json.dumps(dict(proposal_id=pid)).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read())
    except urllib.error.HTTPError as exc:return json.loads(exc.read())

def clients(service,ctx,pid):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            try:result=service.confirm(ctx,p['proposal_id']);status=200
            except ValueError as exc:result=dict(error=str(exc));status=409
            raw=json.dumps(result).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        ids=[pid,pid] if isinstance(pid,str) else pid
        with ProcessPoolExecutor(max_workers=2) as pool:return list(pool.map(client,[(f'http://127.0.0.1:{server.server_port}',value) for value in ids]))
    finally:server.shutdown();server.server_close();thread.join()

def test_same_proposal_two_process_clients_one_authority(sim):
    s,ctx=sim
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['P']))
    results=clients(s,ctx,p['proposal_id'])
    assert results[0]==results[1] and results[0]['status']=='PENDING_PAYMENT'
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==1
        assert [tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments')]==[(1,0),(1,0)]
        assert c.execute('SELECT count(*) FROM v39_idempotency').fetchone()[0]==1
