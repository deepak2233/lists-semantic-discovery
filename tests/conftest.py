import pytest


@pytest.fixture
def payload():
    return {
        "page_url": "https://reader.example.org/articles/hybrid-search?private=remove#section",
        "title": "Hybrid semantic search and reranking",
        "summary": "A search application retrieves documents using BM25 and sentence embeddings. "
        "Reciprocal rank fusion combines lexical and dense retrieval. "
        "A cross encoder can rerank the candidate passages for relevance.",
        "keywords": ["retrieval", "embeddings", "ranking", "BM25"],
        "limit": 10,
    }
