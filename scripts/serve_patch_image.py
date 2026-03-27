"""Serve patch_v24_image.html on port 8092."""
import http.server
import os

os.chdir(os.path.dirname(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.path = "/patch_v24_image.html"
        return super().do_GET()

print("Serving on http://localhost:8092")
http.server.HTTPServer(("", 8092), Handler).serve_forever()
