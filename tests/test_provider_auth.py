import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from lists_api.auth import Authenticator
from lists_api.config import Settings
from lists_api.retrieval import BraveProvider, ProviderUnavailable


def test_brave_contract_and_result_sanitization():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.search.brave.com"
        assert request.headers["X-Subscription-Token"] == "test-key"
        assert request.url.params["count"] == "20"
        assert request.url.params["safesearch"] == "strict"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://public.example.org/article?utm_source=x",
                            "title": "<b>Search</b>",
                            "description": "Sentence &amp; document embeddings",
                        },
                        {"url": "http://127.0.0.1/", "title": "private", "description": "excluded"},
                    ]
                }
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await BraveProvider(client, "test-key").search("semantic retrieval")
            assert len(result) == 2  # Deduplication is the ranker's responsibility.
            assert result[0].title == "Search"
            assert result[0].snippet == "Sentence & document embeddings"

    asyncio.run(run())
    assert [r.url.params["offset"] for r in calls] == ["0", "1"]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_error_contract(status):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status))
        ) as client:
            with pytest.raises(ProviderUnavailable):
                await BraveProvider(client, "secret").search("topic")

    asyncio.run(run())


def test_provider_total_deadline_and_circuit():
    calls = 0

    async def slow(request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            provider = BraveProvider(client, "test", timeout=0.001)
            for _ in range(4):
                with pytest.raises(ProviderUnavailable):
                    await provider.search("topic")
            assert calls == 3

    asyncio.run(run())


def test_malformed_response_is_dependency_failure():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"web": {"results": "wrong"}})
            )
        ) as client:
            with pytest.raises(ProviderUnavailable):
                await BraveProvider(client, "test").search("topic")

    asyncio.run(run())


@pytest.fixture
def signed_auth():
    settings = replace(
        Settings(),
        auth_mode="jwt",
        jwt_issuer="https://id.example.org/",
        jwt_audience="lists",
        jwt_jwks_url="https://id.example.org/keys",
    )
    auth = Authenticator(settings)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    )
    claims = {
        "sub": "user-a",
        "iss": settings.jwt_issuer,
        "aud": "lists",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "scope": "recommend:read",
    }
    return auth, key, claims


def test_valid_access_token(signed_auth):
    auth, key, claims = signed_auth
    subject = auth.validate(jwt.encode(claims, key, algorithm="RS256"))
    assert len(subject) == 64 and subject != "user-a"


@pytest.mark.parametrize(
    "claims_update",
    [
        {"aud": "another-api"},
        {"iss": "https://evil.example.org/"},
        {"exp": 1},
        {"scope": "unrelated:read"},
        {"sub": ""},
    ],
)
def test_invalid_claims_rejected(signed_auth, claims_update):
    auth, key, claims = signed_auth
    with pytest.raises(jwt.PyJWTError):
        auth.validate(jwt.encode(claims | claims_update, key, algorithm="RS256"))


def test_algorithm_confusion_rejected(signed_auth):
    auth, _, claims = signed_auth
    with pytest.raises(jwt.PyJWTError):
        auth.validate(jwt.encode(claims, "x" * 40, algorithm="HS256"))
