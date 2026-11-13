import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ALLOWED_PDF_HOSTS = frozenset({
    "vos.olimpiada.ru",
    "xn--b1ayi3a.xn--l1afu.xn--p1ai",
})
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PDF_DOWNLOAD_SECONDS = 90


def validate_pdf_url(value: str, resolve: bool = True) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError):
        raise ValueError("PDF URL is invalid")

    if (
        parsed.scheme.lower() != "https"
        or host not in ALLOWED_PDF_HOSTS
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or not parsed.path.startswith("/")
    ):
        raise ValueError("PDF URL is not from an approved HTTPS source")

    if resolve:
        try:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("PDF source could not be resolved") from exc
        if not addresses:
            raise ValueError("PDF source has no addresses")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address[4][0])
            except ValueError as exc:
                raise ValueError("PDF source resolved to an invalid address") from exc
            if not ip.is_global:
                raise ValueError("PDF source resolved to a non-public address")
    return raw


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_pdf_url(target, resolve=True)
        return super().redirect_request(req, fp, code, msg, headers, target)


_OPENER = build_opener(_SafeRedirectHandler())


def open_pdf_url(url: str, method: str = "GET", timeout: int = 30):
    approved_url = validate_pdf_url(url, resolve=True)
    request = Request(
        approved_url,
        method=method,
        headers={"User-Agent": "EzOlimp-PDF/1.0"},
    )
    return _OPENER.open(request, timeout=timeout)
