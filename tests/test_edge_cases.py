import asyncio
from dataclasses import replace
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from lists_api.auth import Authenticator
from lists_api.config import Settings
from lists_api.controls import RateLimiter, ResultCache
from lists_api.main import create_app
from lists_api.ranking import Ranker
from lists_api.retrieval import Candidate
from lists_api.safety import canonical_url
from lists_api.schemas import RecommendRequest
from lists_api.web import create_web_app


@pytest.mark.parametrize(
    "query",
    [
        "q=a%20b&q=c%2Bd&sig=abc%2Fdef&u%74m_source=keep",
        "X-Amz-Signature=abcdef&X-Amz-Date=20261113T000000Z&z=2&a=1",
        "token=abc&x=hello%20world&x=hello+world",
    ],
)
def test_signed_query_bytes_are_preserved(query):
    assert canonical_url("https://example.org/a?" + query) == "https://example.org/a?" + query


def test_repeated_query_order_and_escaping_survive_cleanup():
    assert (
        canonical_url("https://example.org/a?z=2&q=a%20b&q=c%2Bd&utm_source=remove")
        == "https://example.org/a?z=2&q=a%20b&q=c%2Bd"
    )


@pytest.mark.parametrize(
    "host",
    [
        "127.1",
        "0x7f.0.0.1",
        "01.002.003.004",
        "-bad.example.org",
        "bad-.example.org",
        "bad..example.org",
        "a." + "x" * 64,
    ],
)
def test_nonstandard_ip_and_invalid_dns_names_are_rejected(host):
    with pytest.raises(ValueError):
        canonical_url("https://" + host + "/article")


def test_idn_and_trailing_dot_normalization():
    assert (
        canonical_url("https://BÜCHER.example.org./article#section")
        == "https://xn--bcher-kva.example.org/article"
    )


def test_bidi_control_characters_cannot_disguise_a_link():
    with pytest.raises(ValueError):
        canonical_url("https://example.org/a\u202eb")


def test_minimum_summary_length_applies_after_normalization(payload):
    with pytest.raises(ValueError):
        RecommendRequest(**(payload | {"summary": "a " + "\t" * 50 + "b"}))


def test_identifiers_cannot_become_search_keywords(payload):
    request = RecommendRequest(**(payload | {"keywords": ["private@example.org", "search"]}))
    assert request.keywords == ["search"]


def test_generic_identical_titles_do_not_hide_distinct_articles(payload):
    request = RecommendRequest(**payload)
    rows = [
        Candidate(
            "https://one.example.org/a",
            "Search overview",
            "Dense sentence embeddings compare semantic document meaning",
            1,
        ),
        Candidate(
            "https://two.example.org/b",
            "Search overview",
            "BM25 lexical retrieval scores term frequencies and ranks documents",
            2,
        ),
    ]
    results, _ = Ranker().rank(request, rows)
    assert len(results) == 2


def test_duplicate_title_and_snippet_are_collapsed_across_hosts(payload):
    rows = [
        Candidate("https://one.example.org/a", "Search overview", "Dense search embeddings", 1),
        Candidate("https://two.example.org/b", "Search overview", "Dense search embeddings", 2),
    ]
    results, _ = Ranker().rank(RecommendRequest(**payload), rows)
    assert len(results) == 1


def test_semantic_request_without_model_is_explicitly_rejected(payload):
    with TestClient(create_app()) as client:
        result = client.post("/v1/recommend", json=payload | {"ranking": "semantic"})
        assert result.status_code == 409
        assert "not configured" in result.json()["detail"]


def test_lexical_selection_does_not_execute_a_loaded_model(payload):
    class NeverEncode:
        def encode(self, *args, **kwargs):
            raise AssertionError("Lexical mode must not execute the model")

    ranker = Ranker()
    ranker.model = NeverEncode()
    with TestClient(create_app(ranker=ranker)) as client:
        result = client.post("/v1/recommend", json=payload | {"ranking": "lexical"})
        assert result.status_code == 200
        assert result.json()["ranker"] == "bm25-rrf-mmr"
        assert all(r["semantic_similarity"] is None for r in result.json()["recommendations"])
        assert "Lexical baseline selected for this request." in result.json()["warnings"]
        assert not any("not configured" in warning for warning in result.json()["warnings"])


def test_bad_model_output_fails_without_false_results(payload):
    class BadRanker(Ranker):
        def rank(self, *args, **kwargs):
            raise ValueError("private model diagnostic")

    with TestClient(create_app(ranker=BadRanker())) as client:
        result = client.post("/v1/recommend", json=payload)
        assert result.status_code == 503
        assert "private" not in result.text


def test_rate_limit_denials_do_not_prevent_expired_identity_cleanup():
    limiter = RateLimiter(1, max_subjects=2)
    assert limiter.allow("a", now=0)
    assert limiter.allow("b", now=50)
    assert not limiter.allow("a", now=59)
    assert limiter.allow("c", now=61)


def test_cache_expiry_is_enforced(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("lists_api.controls.time.monotonic", lambda: now[0])
    cache = ResultCache(5)
    cache.put("key", ["result"])
    now[0] = 106
    assert cache.get("key") is None
    assert not cache.values


def test_identity_outage_is_service_unavailability():
    settings = replace(
        Settings(),
        auth_mode="jwt",
        jwt_issuer="https://id.example.org/",
        jwt_audience="lists",
        jwt_jwks_url="https://id.example.org/keys",
    )
    auth = Authenticator(settings)

    def fail(token):
        raise jwt.PyJWKClientConnectionError("private network address")

    auth.validate = fail
    request = SimpleNamespace(headers={"authorization": "Bearer opaque-test-token"})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(auth(request))
    assert caught.value.status_code == 503
    assert "private" not in caught.value.detail


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.org/",
        "https://example.org/path",
        "http://remote.example.org",
        "https://u:p@example.org",
    ],
)
def test_web_origin_configuration_never_accepts_paths_or_insecure_remote_hosts(origin):
    with pytest.raises(ValueError):
        replace(Settings(), web_origins=(origin,)).validate()


def test_demo_environment_cannot_call_a_paid_search_provider():
    with pytest.raises(ValueError):
        replace(Settings(), environment="demo", provider="brave", brave_api_key="test").validate()


def test_web_entrypoint_serves_ui_and_real_inference(payload):
    settings = replace(
        Settings(),
        environment="demo",
        web_origins=("https://play.example.org",),
        allowed_hosts=("play.example.org",),
    )
    with TestClient(create_web_app(settings), base_url="https://play.example.org") as client:
        assert "One good read" in client.get("/").text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/favicon.svg").status_code == 200
        config = client.get("/v1/config").json()
        assert config["mode"] == "demo" and config["corpus_documents"] == 44
        response = client.post(
            "/v1/recommend", json=payload, headers={"Origin": "https://play.example.org"}
        )
        assert response.status_code == 200
        assert response.json()["recommendations"]
        assert set(response.json()["timings_ms"]) == {"ranking", "retrieval"}
        assert (
            client.post(
                "/v1/recommend", json=payload, headers={"Origin": "https://evil.example.org"}
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "update",
    [
        {"ranking": "invented"},
        {"exclude_same_host": "false"},
        {"limit": False},
        {"limit": 0},
        {"limit": -1},
    ],
)
def test_strict_options_cannot_silently_change_inference(payload, update):
    with TestClient(create_app()) as client:
        assert client.post("/v1/recommend", json=payload | update).status_code == 422


def test_invalid_json_error_does_not_echo_private_content():
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/recommend",
            content='{"private":"secret-value",',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "secret-value" not in response.text
