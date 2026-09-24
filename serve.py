"""Local dev server for web/ that disables browser caching (so edits show on reload)."""
import functools
import http.server
import sys
from pathlib import Path


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
handler = functools.partial(NoCache, directory=str(Path(__file__).parent / "web"))
print(f"Serving web/ at http://localhost:{port}")
http.server.ThreadingHTTPServer(("", port), handler).serve_forever()
