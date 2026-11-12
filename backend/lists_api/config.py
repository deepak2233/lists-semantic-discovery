"""Configuration is explicit; production fails closed on missing identity settings."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    provider: str = "demo"
    brave_api_key: str = ""
    auth_mode: str = "none"
    jwt_issuer: str = ""
    jwt_audience: str = ""
    jwt_jwks_url: str = ""
    jwt_scope: str = "recommend:read"
    allowed_origins: tuple[str, ...] = ()
    web_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    semantic_model_path: str = ""
    provider_timeout_seconds: float = 3.0
    cache_ttl_seconds: float = 0.0
    requests_per_minute: int = 30
    max_inflight: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        def csv(name: str, default: str = "") -> tuple[str, ...]:
            return tuple(v.strip() for v in os.getenv(name, default).split(",") if v.strip())

        return cls(
            environment=os.getenv("LISTS_ENV", "development"),
            provider=os.getenv("LISTS_PROVIDER", "demo"),
            brave_api_key=os.getenv("BRAVE_API_KEY", ""),
            auth_mode=os.getenv("LISTS_AUTH_MODE", "none"),
            jwt_issuer=os.getenv("JWT_ISSUER", ""),
            jwt_audience=os.getenv("JWT_AUDIENCE", ""),
            jwt_jwks_url=os.getenv("JWT_JWKS_URL", ""),
            jwt_scope=os.getenv("JWT_REQUIRED_SCOPE", "recommend:read"),
            allowed_origins=csv("LISTS_ALLOWED_ORIGINS"),
            web_origins=csv("LISTS_WEB_ORIGINS"),
            allowed_hosts=csv("LISTS_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"),
            semantic_model_path=os.getenv("LISTS_MODEL_PATH", ""),
            provider_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "3")),
            cache_ttl_seconds=float(os.getenv("CACHE_TTL_SECONDS", "0")),
            requests_per_minute=int(os.getenv("REQUESTS_PER_MINUTE", "30")),
            max_inflight=int(os.getenv("MAX_INFLIGHT", "8")),
        )

    def validate(self) -> None:
        if self.environment not in {"development", "demo", "production"}:
            raise ValueError("LISTS_ENV must be development, demo or production")
        if self.provider not in {"demo", "brave"} or self.auth_mode not in {"none", "jwt"}:
            raise ValueError("Unsupported provider or authentication mode")
        if self.provider == "brave" and not self.brave_api_key:
            raise ValueError("BRAVE_API_KEY is required for live retrieval")
        if self.auth_mode == "jwt":
            if not all((self.jwt_issuer, self.jwt_audience, self.jwt_jwks_url, self.jwt_scope)):
                raise ValueError("JWT issuer, audience, JWKS URL and scope are required")
            if any(urlsplit(u).scheme != "https" for u in (self.jwt_issuer, self.jwt_jwks_url)):
                raise ValueError("JWT issuer and JWKS endpoint must use HTTPS")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("Use explicit allowed hosts")
        if any(not re.fullmatch(r"chrome-extension://[a-p]{32}", o) for o in self.allowed_origins):
            raise ValueError("Only packaged extension origins are supported")
        for origin in self.web_origins:
            parsed = urlsplit(origin)
            loopback = parsed.hostname in {"localhost", "127.0.0.1"}
            if (
                not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path
                or (
                    parsed.scheme != "https"
                    and not (
                        self.environment != "production" and parsed.scheme == "http" and loopback
                    )
                )
            ):
                raise ValueError("Web origins must be exact HTTPS origins or development loopback")
        if self.environment == "demo" and (self.provider != "demo" or self.auth_mode != "none"):
            raise ValueError("Public demo mode only permits the fixed corpus and no paid provider")
        if self.environment == "production":
            if (
                self.auth_mode != "jwt"
                or self.provider != "brave"
                or not (self.allowed_origins or self.web_origins)
            ):
                raise ValueError(
                    "Production requires JWT auth, live retrieval and explicit origins"
                )
        if self.semantic_model_path and not Path(self.semantic_model_path).is_dir():
            raise ValueError("LISTS_MODEL_PATH must point to a reviewed local model directory")
        if not 0.1 <= self.provider_timeout_seconds <= 10:
            raise ValueError("Provider timeout must be between 0.1 and 10 seconds")
        if not 0 <= self.cache_ttl_seconds <= 300:
            raise ValueError("Cache TTL must be between 0 and 300 seconds")
        if self.requests_per_minute < 1 or not 1 <= self.max_inflight <= 64:
            raise ValueError("Invalid capacity settings")
