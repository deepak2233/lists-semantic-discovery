"""Link validation only. User-controlled URLs are NEVER fetched by the backend."""

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"gclid", "fbclid", "msclkid", "ref_src"}
SENSITIVE = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|"
    r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}\b|"
    r"\b(?:\d[ -]?){13,19}\b",
    re.I,
)


def redact(text: str) -> str:
    return SENSITIVE.sub("[redacted]", text)


def canonical_url(value: str, *, drop_query: bool = False) -> str:
    if len(value) > 2048 or any(ord(c) < 33 or c == "\\" for c in value):
        raise ValueError("Invalid URL")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or parts.username or parts.password:
        raise ValueError("Only public HTTP(S) URLs without credentials are supported")
    host = (parts.hostname or "").rstrip(".").lower().encode("idna").decode("ascii")
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Private or incomplete host")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
            raise ValueError("Invalid host") from None
    else:
        # Reject all literals, including public ones: no need for IP links in this product.
        raise ValueError(f"IP address links are not supported (IPv{ip.version})")
    if parts.port not in {None, 443 if parts.scheme == "https" else 80}:
        raise ValueError("Nonstandard port")
    query = (
        []
        if drop_query
        else [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING
        ]
    )
    return urlunsplit((parts.scheme, host, parts.path or "/", urlencode(sorted(query)), ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def page_identity(url: str) -> str:
    """Match http/https, www and trailing slash variants; keep meaningful result query keys."""
    p = urlsplit(canonical_url(url))
    return host_of(url) + p.path.rstrip("/") + ("?" + p.query if p.query else "")
