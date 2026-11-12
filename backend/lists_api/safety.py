"""Link validation only. User-controlled URLs are NEVER fetched by the backend."""

import ipaddress
import re
import unicodedata
from urllib.parse import unquote_plus, urlsplit, urlunsplit

TRACKING = {"gclid", "fbclid", "msclkid", "ref_src"}
SENSITIVE = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|"
    r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}\b|"
    r"\b(?:\d[ -]?){13,19}\b",
    re.I,
)


def redact(text: str) -> str:
    clean = "".join(" " if unicodedata.category(c) in {"Cc", "Cf"} else c for c in text)
    return SENSITIVE.sub("[redacted]", clean)


def canonical_url(value: str, *, drop_query: bool = False) -> str:
    if len(value) > 2048 or any(
        ord(c) < 33 or c == "\\" or unicodedata.category(c) == "Cf" for c in value
    ):
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
        labels = host.split(".")
        if (
            len(host) > 253
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in labels)
            or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host)
            or labels[-1].isdigit()
        ):
            raise ValueError("Invalid host") from None
    else:
        # Reject all literals, including public ones: no need for IP links in this product.
        raise ValueError(f"IP address links are not supported (IPv{ip.version})")
    if parts.port not in {None, 443 if parts.scheme == "https" else 80}:
        raise ValueError("Nonstandard port")
    # Preserve query order and escaping: repeated keys and signatures can depend on both.
    pairs = parts.query.split("&") if parts.query else []
    keys = [unquote_plus(p.split("=", 1)[0]).lower() for p in pairs]
    signed = any(
        k.startswith(("x-amz-", "x-goog-")) or k in {"signature", "sig", "token", "access_token"}
        for k in keys
    )
    query = (
        ""
        if drop_query
        else "&".join(
            p
            for p, k in zip(pairs, keys, strict=True)
            if signed or (not k.startswith("utm_") and k not in TRACKING)
        )
    )
    return urlunsplit((parts.scheme, host, parts.path or "/", query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def page_identity(url: str) -> str:
    """Match http/https, www and trailing slash variants; keep meaningful result query keys."""
    p = urlsplit(canonical_url(url))
    return host_of(url) + p.path.rstrip("/") + ("?" + p.query if p.query else "")
