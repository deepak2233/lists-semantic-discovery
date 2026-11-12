from collections import Counter
from dataclasses import replace

import pytest
from lists_api.config import Settings
from lists_api.controls import RateLimiter, ResultCache
from lists_api.ranking import Ranker, bm25, make_query
from lists_api.retrieval import Candidate, DemoProvider
from lists_api.safety import canonical_url, redact
from lists_api.schemas import RecommendRequest


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:password@example.com/a",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.8/x",
        "http://[::1]/x",
        "https://intranet.internal/x",
        "https://example.com:8080/x",
        "https://example.com\\@private.local/x",
        "https://example.com/\nsecret",
    ],
)
def test_unsafe_links_rejected(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_url_canonicalization():
    assert (
        canonical_url("https://EXAMPLE.com/a?b=2&utm_source=x&a=1#f")
        == "https://example.com/a?a=1&b=2"
    )
    assert (
        canonical_url("https://example.com/a?token=private", drop_query=True)
        == "https://example.com/a"
    )


def test_redaction():
    assert "private@example.com" not in redact("Write private@example.com about retrieval")
    assert "4111111111111111" not in redact("card 4111111111111111")


def test_bm25_not_misrepresented_as_semantic():
    scores = bm25("dogs", ["A guide to dogs", "Canine care advice"])
    assert scores[0] > 0 and scores[1] == 0


def test_query_construction_does_not_send_source_url(payload):
    request = RecommendRequest(**payload)
    assert "reader.example" not in make_query(request)
    assert "private" not in request.page_url
    assert ":" not in make_query(request)


def test_ranking_dedup_source_filter_and_domain_cap(payload):
    request = RecommendRequest(**payload)
    candidates = [
        Candidate(request.page_url, "Hybrid search current page", "search embeddings", 1),
        Candidate(
            "https://a.example.org/a?utm_source=x",
            "Search ranking example one",
            "search semantic embeddings dense lexical ranking",
            2,
        ),
        Candidate(
            "https://a.example.org/a", "Duplicate tracked page", "search semantic embeddings", 3
        ),
        Candidate("https://a.example.org/b", "BM25 fusion tutorial", "search rank fusion", 4),
        Candidate("https://a.example.org/c", "Dense vectors tutorial", "search vectors", 5),
        Candidate(
            "https://b.example.org/d",
            "Sentence embeddings research",
            "sentence embeddings retrieval",
            6,
        ),
        Candidate("javascript:alert(1)", "Search unsafe", "search", 7),
    ]
    results, count = Ranker().rank(request, candidates)
    assert count == 4
    assert len(results) == 3
    assert max(Counter(r.host for r in results).values()) <= 2
    assert all(r.url != request.page_url for r in results)
    assert len({r.url for r in results}) == len(results)


def test_unrelated_results_are_not_used_as_filler(payload):
    results, _ = Ranker().rank(
        RecommendRequest(**payload),
        [
            Candidate(
                "https://food.example.org/recipe",
                "Baking sourdough bread",
                "Flour salt water yeast oven dough",
                1,
            )
        ],
    )
    assert results == []


def test_dense_adapter_path_without_model_download(payload):
    class Scores(list):
        def tolist(self):
            return list(self)

    class Rows:
        def __matmul__(self, other):
            return Scores([1.0, 0.0])

    class Vectors:
        def __getitem__(self, key):
            return Rows() if isinstance(key, slice) else [1.0, 0.0]

    class FakeEncoder:
        def encode(self, texts, **kwargs):
            return Vectors()

    ranker = Ranker()
    ranker.model = FakeEncoder()
    results, _ = ranker.rank(
        RecommendRequest(**payload),
        [
            Candidate("https://a.example.org/a", "Paraphrase", "Different wording for a topic", 1),
            Candidate("https://b.example.org/b", "Bread", "Baking sourdough flour", 2),
        ],
    )
    assert len(results) == 1 and results[0].title == "Paraphrase"


def test_rate_limiter_expiry_and_capacity():
    limiter = RateLimiter(2, max_subjects=1)
    assert limiter.allow("a", now=0)
    assert limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert not limiter.allow("b", now=2)
    assert limiter.allow("b", now=62)


def test_cache_subject_isolation_and_lru():
    cache = ResultCache(60, capacity=1)
    a, b = cache.key("user-a", "same"), cache.key("user-b", "same")
    assert a != b
    cache.put(a, ["private-a"])
    assert cache.get(b) is None
    cache.put(b, ["private-b"])
    assert cache.get(a) is None


@pytest.mark.parametrize(
    "settings",
    [
        replace(Settings(), environment="production"),
        replace(Settings(), provider="brave"),
        replace(Settings(), auth_mode="jwt"),
        replace(Settings(), allowed_hosts=("*",)),
        replace(Settings(), cache_ttl_seconds=999),
    ],
)
def test_invalid_deployment_settings_fail_closed(settings):
    with pytest.raises(ValueError):
        settings.validate()


def test_demo_inventory_is_explicit():
    assert len(DemoProvider().documents) >= 40
