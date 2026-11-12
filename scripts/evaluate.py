"""Authored fixture regression only. Not an independent relevance or production benchmark."""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from lists_api.ranking import Ranker
from lists_api.retrieval import Candidate, DemoProvider
from lists_api.schemas import RecommendRequest

ROOT = Path(__file__).resolve().parents[1]


def ndcg(grades: list[int], ideal: list[int], k: int) -> float:
    def dcg(values):
        return sum((2**value - 1) / math.log2(i + 2) for i, value in enumerate(values[:k]))

    return dcg(grades) / max(1e-9, dcg(sorted(ideal, reverse=True)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="")
    parser.add_argument("--output", default="evaluation/results.json")
    args = parser.parse_args()
    corpus = DemoProvider().documents
    queries = json.loads((ROOT / "evaluation/queries.json").read_text())
    candidates = [
        Candidate(d["url"], d["title"], d["snippet"], i + 1) for i, d in enumerate(corpus)
    ]
    ranker = Ranker(args.model_path)
    rows = []
    for query in queries:
        payload = RecommendRequest(
            page_url="https://source.example.org/article/" + query["id"],
            title=query["title"],
            summary=query["summary"],
            keywords=query["keywords"],
            limit=10,
        )
        labels = {corpus[int(i)]["url"]: grade for i, grade in query["judgments"].items()}
        started = time.perf_counter()
        results, _ = ranker.rank(payload, candidates, use_provider_rank=False)
        duration = (time.perf_counter() - started) * 1000
        grades = [labels.get(r.url, 0) for r in results]
        relevant_total = sum(g > 0 for g in labels.values())
        recall = sum(g > 0 for g in grades[:10]) / relevant_total
        rows.append(
            {
                "query": query["id"],
                "ndcg_at_10": round(ndcg(grades, list(labels.values()), 10), 4),
                "recall_at_10": round(recall, 4),
                "precision_at_5": sum(g > 0 for g in grades[:5]) / 5,
                "unique_hosts_at_10": len({r.host for r in results[:10]}),
                "elapsed_ms": round(duration, 2),
                "result_count": len(results),
                "urls": [r.url for r in results],
            }
        )
    data = {
        "label": "AUTHORED_FIXTURE_REGRESSION_NOT_INDEPENDENT_BENCHMARK",
        "ranker": ranker.name,
        "corpus_documents": len(corpus),
        "queries": len(queries),
        "corpus_sha256": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        "model_revision": None,
        "mean_ndcg_at_10": round(sum(r["ndcg_at_10"] for r in rows) / len(rows), 4),
        "mean_recall_at_10": round(sum(r["recall_at_10"] for r in rows) / len(rows), 4),
        "results": rows,
    }
    if args.model_path:
        data["model_revision"] = json.loads((Path(args.model_path) / "manifest.json").read_text())[
            "revision"
        ]
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({k: v for k, v in data.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
