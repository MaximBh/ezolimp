import base64
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
import re
import sys


FRONTEND_DIR = Path(__file__).resolve().parent
LEGACY_ROUTES = {
    "/index.html": "/",
    "/main.html": "/",
    "/catalog.html": "/catalog",
    "/training.html": "/training",
    "/pvp.html": "/pvp",
    "/leaderboard.html": "/leaderboard",
    "/analytics.html": "/analytics",
    "/profile.html": "/profile",
    "/admin.html": "/admin",
}
STATIC_ROUTES = {
    "/": "main.html",
    "/catalog": "catalog.html",
    "/training": "training.html",
    "/pvp": "pvp.html",
    "/leaderboard": "leaderboard.html",
    "/analytics": "analytics.html",
    "/profile": "profile.html",
    "/admin": "admin.html",
}
INLINE_SCRIPT_PATTERN = re.compile(rb"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)


def content_security_policy(filename):
    try:
        page = (FRONTEND_DIR / filename).read_bytes()
    except OSError:
        page = b""
    hashes = []
    for attrs, script in INLINE_SCRIPT_PATTERN.findall(page):
        if re.search(rb"\bsrc\s*=", attrs, re.IGNORECASE):
            continue
        normalized_script = script.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest = base64.b64encode(hashlib.sha256(normalized_script).digest()).decode("ascii")
        hashes.append(f"'sha256-{digest}'")
    script_sources = " ".join(["'self'", *hashes])
    return (
        "default-src 'self'; "
        f"script-src {script_sources}; script-src-attr 'none'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https: http://localhost:8001 http://127.0.0.1:8001; font-src 'self' data:; "
        "connect-src 'self' http://localhost:8001 http://127.0.0.1:8001 "
        "ws://localhost:8001 ws://127.0.0.1:8001; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    )


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _route_request(self):
        parsed = urlsplit(self.path)
        path = parsed.path

        if path in LEGACY_ROUTES or path in {"/training", "/profile"}:
            destination = LEGACY_ROUTES.get(path, path)
            query = parse_qsl(parsed.query, keep_blank_values=True)
            if path in {"/training.html", "/training"}:
                task_id = next((value for key, value in query if key == "task" and value), None)
                if task_id:
                    destination = f"/training/{quote(task_id, safe='')}"
                    query = [(key, value) for key, value in query if key != "task"]
            elif path in {"/profile.html", "/profile"}:
                user_id = next((value for key, value in query if key == "id" and value), None)
                if user_id:
                    destination = f"/profile/{quote(user_id, safe='')}"
                    query = [(key, value) for key, value in query if key != "id"]
            if path in LEGACY_ROUTES or destination != path:
                if query:
                    destination = f"{destination}?{urlencode(query)}"
                self.send_response(308)
                self.send_header("Location", destination)
                self.end_headers()
                return True

        canonical_path = path.rstrip("/") or "/"
        if canonical_path != path and (
            canonical_path in STATIC_ROUTES
            or re.fullmatch(r"/(training|profile)/\d+", canonical_path)
        ):
            destination = canonical_path + (f"?{parsed.query}" if parsed.query else "")
            self.send_response(308)
            self.send_header("Location", destination)
            self.end_headers()
            return True

        filename = STATIC_ROUTES.get(path)
        if filename is None and path.lstrip("/") in set(STATIC_ROUTES.values()):
            filename = path.lstrip("/")
        if filename is None and re.fullmatch(r"/training/\d+", path):
            filename = "training.html"
        if filename is None and re.fullmatch(r"/profile/\d+", path):
            filename = "profile.html"

        if filename:
            self.path = f"/{filename}" + (f"?{parsed.query}" if parsed.query else "")
        return False

    def do_GET(self):
        if not self._route_request():
            super().do_GET()

    def do_HEAD(self):
        if not self._route_request():
            super().do_HEAD()

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        path = urlsplit(self.path).path
        filename = STATIC_ROUTES.get(path)
        if filename is None and path.lstrip("/") in set(STATIC_ROUTES.values()):
            filename = path.lstrip("/")
        if filename is None and re.fullmatch(r"/(?:training|profile)/\d+", path):
            filename = "training.html" if path.startswith("/training/") else "profile.html"
        if filename:
            self.send_header("Content-Security-Policy", content_security_policy(filename))
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = ThreadingHTTPServer(("127.0.0.1", port), FrontendHandler)
    print(f"EzOlimp frontend: http://localhost:{port}")
    server.serve_forever()
