"""Simple HTTP server for viewing HTML docs."""
import http.server
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
server = http.server.HTTPServer(("0.0.0.0", 8095), http.server.SimpleHTTPRequestHandler)
print("Serving docs at http://localhost:8095/camp_renewal_preview.html")
server.serve_forever()
