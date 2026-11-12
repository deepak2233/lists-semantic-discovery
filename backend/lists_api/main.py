import asyncio
import logging
import re
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Authenticator
from .config import Settings
from .controls import RateLimiter, ResultCache
from .ranking import Ranker, make_query
from .retrieval import BraveProvider, DemoProvider, ProviderUnavailable, SearchProvider
from .schemas import RecommendRequest, RecommendResponse

logger = logging.getLogger("lists")


class BodyLimitMiddleware:
    """Bound both declared and chunked request bodies before JSON validation."""

    def __init__(self, app, limit: int = 16384):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"detail": "Request body is too large"}, 413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)


def create_app(
    settings: Settings | None = None,
    provider: SearchProvider | None = None,
    ranker: Ranker | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    authenticator = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # HTTPX access logs would include search queries. Do not emit them.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        async with httpx.AsyncClient(
            timeout=settings.provider_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=16),
        ) as client:
            app.state.provider = provider or (
                DemoProvider()
                if settings.provider == "demo"
                else BraveProvider(
                    client, settings.brave_api_key, settings.provider_timeout_seconds
                )
            )
            app.state.ranker = ranker or await run_in_threadpool(
                Ranker, settings.semantic_model_path
            )
            app.state.cache = ResultCache(settings.cache_ttl_seconds)
            app.state.limiter = RateLimiter(settings.requests_per_minute)
            app.state.slots = asyncio.Semaphore(settings.max_inflight)
            app.state.counts = Counter()
            yield
            app.state.cache.values.clear()

    app = FastAPI(
        title="LISTS Discovery API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment == "development" else None,
    )
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_origin_regex=r"chrome-extension://[a-p]{32}"
        if settings.environment == "development"
        else None,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        origin = request.headers.get("origin")
        valid_dev_origin = (
            settings.environment == "development"
            and origin
            and re.fullmatch(r"chrome-extension://[a-p]{32}", origin)
        )
        if origin and origin not in settings.allowed_origins and not valid_dev_origin:
            response = JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if hasattr(app.state, "counts"):
            app.state.counts[str(response.status_code)] += 1
        # No page URL, query, body, subject or exception string in request logs.
        logger.info(
            "request_complete status=%s request_id=%s",
            response.status_code,
            request.state.request_id,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default error embeds the offending input, potentially exposing source text.
        details = [
            {"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in error.errors()
        ]
        return JSONResponse({"detail": details}, status_code=422)

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        return {"status": "ready", "provider": settings.provider, "ranker": app.state.ranker.name}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics(subject: str = Depends(authenticator)):
        lines = ["# TYPE lists_http_responses_total counter"]
        lines += [
            f'lists_http_responses_total{{status="{s}"}} {n}'
            for s, n in sorted(app.state.counts.items())
        ]
        return "\n".join(lines) + "\n"

    @app.post("/v1/recommend", response_model=RecommendResponse)
    async def recommend(
        payload: RecommendRequest, request: Request, subject: str = Depends(authenticator)
    ):
        started = time.perf_counter()
        if not app.state.limiter.allow(subject):
            raise HTTPException(
                429, "Request limit reached. Try again in a minute.", headers={"Retry-After": "60"}
            )
        key = app.state.cache.key(subject, payload.model_dump_json() + app.state.ranker.name)
        cached = app.state.cache.get(key)
        if cached is not None:
            results, count, warnings = cached
        else:
            try:
                await asyncio.wait_for(app.state.slots.acquire(), timeout=0.05)
            except TimeoutError:
                raise HTTPException(
                    503, "Server is busy. Try again shortly.", headers={"Retry-After": "1"}
                ) from None
            try:
                candidates = await app.state.provider.search(make_query(payload))
                results, count = await run_in_threadpool(
                    app.state.ranker.rank,
                    payload,
                    candidates,
                    use_provider_rank=settings.provider != "demo",
                )
            except ProviderUnavailable:
                raise HTTPException(
                    503, "Web search is temporarily unavailable.", headers={"Retry-After": "30"}
                ) from None
            finally:
                app.state.slots.release()
            warnings = []
            if settings.provider == "demo":
                warnings.append("Demo corpus only. These are not live web search results.")
            if not settings.semantic_model_path:
                warnings.append("Lexical ranking is active. Semantic model is not configured.")
            if len(results) < payload.limit:
                warnings.append("Fewer relevant, distinct pages were available than requested.")
            app.state.cache.put(key, (results, count, warnings))
        return RecommendResponse(
            request_id=request.state.request_id,
            mode="demo" if settings.provider == "demo" else "live",
            ranker=app.state.ranker.name,
            recommendations=results,
            warnings=warnings,
            candidate_count=count,
            cached=cached is not None,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    return app


app = create_app()
