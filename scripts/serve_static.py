import http.server, os, sys
os.chdir(os.path.join(os.path.dirname(__file__)))
print(f"Serving on http://localhost:8094", flush=True)
http.server.HTTPServer(("", 8094), http.server.SimpleHTTPRequestHandler).serve_forever()
