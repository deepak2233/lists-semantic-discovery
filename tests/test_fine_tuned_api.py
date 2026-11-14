from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from lists_api.config import Settings
from lists_api.main import create_app
from lists_api.ranking import Ranker


class PairEncoder:
    def __init__(self, cosine):
        self.cosine = cosine

    def encode(self, texts):
        assert len(texts) == 2
        return np.array([[1.0, 0], [self.cosine, np.sqrt(1 - self.cosine**2)]])


def test_compare_uses_both_models_without_storing_or_echoing_inputs():
    baseline = SimpleNamespace(model=PairEncoder(0.6), name="baseline")
    tuned = SimpleNamespace(model=PairEncoder(0.8), name="snli-lora-v1")
    with TestClient(create_app(ranker=baseline, fine_tuned_ranker=tuned)) as client:
        response = client.post(
            "/v1/compare", json={"text_a": "First public text", "text_b": "Second public text"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["baseline_cosine"] == 0.6
        assert data["fine_tuned_cosine"] == 0.8
        assert data["difference"] == 0.2
        assert data["fine_tuned_model"] == "snli-lora-v1"
        assert "First public text" not in response.text
        assert not client.app.state.cache.values


def test_compare_missing_model_is_explicit_and_not_a_baseline_substitute():
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/compare", json={"text_a": "One sentence", "text_b": "Another sentence"}
        )
        assert response.status_code == 409
        assert client.get("/v1/config").json()["fine_tuned_available"] is False


def test_fine_tuned_ranking_selection_is_not_silently_downgraded(payload):
    with TestClient(create_app()) as client:
        assert (
            client.post("/v1/recommend", json=payload | {"ranking": "fine_tuned"}).status_code
            == 409
        )


def test_recommend_selects_requested_trained_ranker(payload):
    called = []

    class SelectedRanker:
        model = object()
        name = "bm25-minilm-snli-lora-v1-rrf-mmr"

        def rank(self, request, candidates, **kwargs):
            called.append(request.ranking)
            return Ranker().rank(request, candidates, use_semantic=False)

    with TestClient(create_app(fine_tuned_ranker=SelectedRanker())) as client:
        response = client.post("/v1/recommend", json=payload | {"ranking": "fine_tuned"})
        assert response.status_code == 200
        assert response.json()["ranker"] == SelectedRanker.name
        assert called == ["fine_tuned"]


@pytest.mark.parametrize(
    "body",
    [
        {"text_a": "x", "text_b": "Valid text"},
        {"text_a": "   ", "text_b": "Valid text"},
        {"text_a": "x" * 1801, "text_b": "Valid text"},
        {"text_a": "Valid text", "text_b": "Valid text", "extra": "private"},
    ],
)
def test_compare_rejects_invalid_input_without_echoing_it(body):
    with TestClient(create_app()) as client:
        response = client.post("/v1/compare", json=body)
        assert response.status_code == 422
        assert "private" not in response.text


def test_compare_obeys_origin_checks_and_shared_admission():
    settings = replace(Settings(), requests_per_minute=1)
    ranker = SimpleNamespace(model=PairEncoder(0.5), name="baseline")
    adapted = SimpleNamespace(model=PairEncoder(0.6), name="adapted")
    with TestClient(create_app(settings, ranker=ranker, fine_tuned_ranker=adapted)) as client:
        body = {"text_a": "First sentence", "text_b": "Second sentence"}
        assert (
            client.post(
                "/v1/compare", json=body, headers={"Origin": "https://evil.example.org"}
            ).status_code
            == 403
        )
        assert client.post("/v1/compare", json=body).status_code == 200
        assert client.post("/v1/compare", json=body).status_code == 429
