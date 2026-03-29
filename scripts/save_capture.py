"""Tiny HTTP server that accepts POST /save with base64 PNG body."""
import http.server
import base64
import json
import os

SAVE_PATH = os.path.join(os.path.dirname(__file__), "patch_v24_thumb.png")

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        data = json.loads(body)
        b64 = data['image'].split(',')[1] if ',' in data['image'] else data['image']
        img_bytes = base64.b64decode(b64)
        with open(SAVE_PATH, 'wb') as f:
            f.write(img_bytes)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "size": len(img_bytes), "path": SAVE_PATH}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

print(f"Save server on http://localhost:9998, will save to {SAVE_PATH}")
http.server.HTTPServer(("", 9998), Handler).serve_forever()
