# TEMP probe: replicates server.py's SSE lifecycle (events, then __end__ which
# ends the response) so the browser's real EventSource close behaviour can be
# observed. Not shipped.
import http.server, json, socketserver, time

STATE = {
    "thread_id": "AGT-probe", "done": True, "awaiting_approval": False,
    "awaiting_clarification": False, "workflow_status": "completed",
    "execution_plan": {"steps": []}, "current_step_index": 0,
    "execution_results": {}, "execution_exit_codes": {}, "variables": {},
    "audit_log": [], "entities": {}, "elapsed_seconds": 3,
}


class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if "/stream" not in self.path:
            return super().do_GET()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        # one node frame, then done -- then the response simply ENDS, exactly
        # like event_gen() breaking on the __end__ sentinel.
        for ev, payload in (("node", {"state": STATE}), ("done", {"state": STATE})):
            self.wfile.write(f"event: {ev}\ndata: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.05)
        # return -> connection closed by server


socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", 8131), H) as httpd:
    httpd.serve_forever()
