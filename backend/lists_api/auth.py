import hashlib

import jwt
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .config import Settings


class Authenticator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = (
            jwt.PyJWKClient(settings.jwt_jwks_url, cache_keys=True, timeout=2, lifespan=300)
            if settings.auth_mode == "jwt"
            else None
        )

    def validate(self, token: str) -> str:
        assert self.jwks is not None
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or len(str(header.get("kid", ""))) > 256:
            raise jwt.InvalidTokenError("Unsupported signing header")
        key = self.jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self.settings.jwt_audience,
            issuer=self.settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=15,
        )
        subject = claims["sub"]
        scope = claims.get("scope", "")
        if not isinstance(subject, str) or not subject or len(subject) > 256:
            raise jwt.InvalidTokenError("Invalid subject")
        if not isinstance(scope, str) or self.settings.jwt_scope not in scope.split():
            raise jwt.InvalidTokenError("Insufficient scope")
        return hashlib.sha256(subject.encode()).hexdigest()

    async def __call__(self, request: Request) -> str:
        if self.settings.auth_mode == "none":
            return "local-development"
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 8192:
            raise HTTPException(
                401, "A valid access token is required", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            return await run_in_threadpool(self.validate, header[7:])
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(
                503, "Identity service is temporarily unavailable", headers={"Retry-After": "30"}
            ) from None
        except (jwt.PyJWTError, ValueError, OSError):
            raise HTTPException(
                401, "Access token is invalid or expired", headers={"WWW-Authenticate": "Bearer"}
            ) from None
