import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from lists_api.config import Settings
from lists_api.main import create_app
from lists_api.retrieval import ProviderUnavailable


def test_end_to_end_demo_contract(payload):
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").json()["status"] == "ready"
        response = client.post("/v1/recommend", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["mode"] == "demo"
        assert data["ranker"] == "bm25-rrf-mmr"
        assert 1 <= len(data["recommendations"]) <= 10
        assert len({r["url"] for r in data["recommendations"]}) == len(data["recommendations"])
        assert response.headers["Cache-Control"] == "no-store"
        assert data["request_id"] == response.headers["X-Request-ID"]
        assert any("not live" in w for w in data["warnings"])


@pytest.mark.parametrize(
    "update",
    [
        {"limit": 11},
        {"limit": "10"},
        {"summary": "short"},
        {"language": "hi"},
        {"html": "<script>bad</script>"},
        {"page_url": "http://127.0.0.1/admin"},
        {"keywords": ["x" * 100]},
    ],
)
def test_reject_invalid_payloads(payload, update):
    with TestClient(create_app()) as client:
        response = client.post("/v1/recommend", json=payload | update)
    assert response.status_code == 422
    assert "private=remove" not in response.text
    assert "input" not in response.json().get("detail", [{}])[0]


def test_body_limit_and_chunked_limit():
    with TestClient(create_app()) as client:
        assert client.post("/v1/recommend", content=b"x" * 17000).status_code == 413
        response = client.post("/v1/recommend", content=iter([b"x" * 9000, b"y" * 9000]))
        assert response.status_code == 413


def test_cors_and_browser_origin_guard(payload):
    origin = "chrome-extension://" + "a" * 32
    with TestClient(create_app()) as client:
        response = client.post("/v1/recommend", json=payload, headers={"Origin": origin})
        assert response.headers["Access-Control-Allow-Origin"] == origin
        response = client.post(
            "/v1/recommend", json=payload, headers={"Origin": "https://untrusted.example.org"}
        )
        assert response.status_code == 403
        preflight = client.options(
            "/v1/recommend",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200


def test_host_guard():
    with TestClient(create_app(), base_url="http://evil.example.org") as client:
        assert client.get("/health/live").status_code == 400


def test_rate_limit_applies_to_cache_hits(payload):
    settings = replace(Settings(), requests_per_minute=2, cache_ttl_seconds=60)
    with TestClient(create_app(settings)) as client:
        assert not client.post("/v1/recommend", json=payload).json()["cached"]
        assert client.post("/v1/recommend", json=payload).json()["cached"]
        response = client.post("/v1/recommend", json=payload)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"


def test_provider_failure_never_returns_demo_as_live(payload):
    class BrokenProvider:
        async def search(self, query):
            raise ProviderUnavailable("secret provider response")

    with TestClient(create_app(provider=BrokenProvider())) as client:
        response = client.post("/v1/recommend", json=payload)
        assert response.status_code == 503
        assert "secret" not in response.text


def test_auth_required_before_provider_call(payload):
    settings = replace(
        Settings(),
        auth_mode="jwt",
        jwt_issuer="https://id.example.org/",
        jwt_audience="lists",
        jwt_jwks_url="https://id.example.org/keys",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/recommend", json=payload)
        assert response.status_code == 401
        assert client.get("/metrics").status_code == 401
        assert client.get("/health/live").status_code == 200


def test_metrics_and_logs_do_not_expose_payload(payload, caplog):
    with TestClient(create_app()) as client:
        client.post("/v1/recommend", json=payload)
        metric = client.get("/metrics").text
        assert 'status="200"' in metric
        assert "reader.example" not in metric + caplog.text
        assert payload["summary"] not in metric + caplog.text


def test_empty_candidates_are_honest(payload):
    class EmptyProvider:
        async def search(self, query):
            return []

    with TestClient(create_app(provider=EmptyProvider())) as client:
        result = client.post("/v1/recommend", json=payload).json()
        assert result["recommendations"] == []
        assert any("Fewer" in w for w in result["warnings"])


def test_admission_rejects_excess_inflight_work(payload):
    class SlowProvider:
        async def search(self, query):
            await asyncio.sleep(0.25)
            return []

    with TestClient(
        create_app(replace(Settings(), max_inflight=1), provider=SlowProvider())
    ) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(client.post, "/v1/recommend", json=payload) for _ in range(2)]
            statuses = sorted(f.result().status_code for f in requests)
        assert statuses == [200, 503]


def test_invalid_extension_origin_is_rejected(payload):
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/recommend", json=payload, headers={"Origin": "chrome-extension://" + "z" * 32}
        )
        assert response.status_code == 403
