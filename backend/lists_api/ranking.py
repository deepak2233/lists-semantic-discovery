"""BM25 + optional local bi-encoder + RRF + MMR, over a bounded candidate pool."""

import hashlib
import math
import re
from collections import Counter

from .retrieval import Candidate
from .safety import canonical_url, host_of, page_identity
from .schemas import Recommendation, RecommendRequest

STOP = set(
    "a an and are as at be been by can for from has have how i if in into is it its "
    "of on or our that the their these this to use using was we were what when which "
    "will with you your page website read learn more guide introduction".split()
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9+#.-]{1,39}", text.lower()) if t not in STOP]


def make_query(request: RecommendRequest) -> str:
    # Never copy search operators or the source URL into the provider query.
    words = tokens(" ".join([request.title, *request.keywords]))
    if len(words) < 4:
        words += [w for w, _ in Counter(tokens(request.summary)).most_common(8)]
    return " ".join(dict.fromkeys(words))[:350]


def bm25(query: str, texts: list[str]) -> list[float]:
    docs = [Counter(tokens(t)) for t in texts]
    avgdl = sum(sum(d.values()) for d in docs) / max(1, len(docs)) or 1
    df = Counter(w for d in docs for w in d)
    result = []
    for d in docs:
        score = 0.0
        for w in set(tokens(query)):
            idf = math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
            f = d[w]
            score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * sum(d.values()) / avgdl))
        result.append(score)
    return result


def jaccard(a: str, b: str) -> float:
    left, right = set(tokens(a)), set(tokens(b))
    return len(left & right) / max(1, len(left | right))


class Ranker:
    def __init__(self, model_path: str = "") -> None:
        self.model = None
        if model_path:
            from .semantic import MiniLMEncoder

            self.model = MiniLMEncoder(model_path)
        self.name = "bm25-minilm-rrf-mmr" if self.model else "bm25-rrf-mmr"

    def rank(
        self,
        request: RecommendRequest,
        candidates: list[Candidate],
        *,
        use_provider_rank: bool = True,
    ) -> tuple[list[Recommendation], int]:
        filtered, seen = [], set()
        source = page_identity(request.page_url)
        for candidate in candidates[:100]:
            try:
                url = canonical_url(candidate.url)
                identity = page_identity(url)
            except ValueError:
                continue
            # Source query keys are removed on the request; compare path-only identities too.
            if identity.split("?", 1)[0] == source.split("?", 1)[0] or identity in seen:
                continue
            if request.exclude_same_host and host_of(url) == host_of(request.page_url):
                continue
            if any(jaccard(candidate.title, c.title) > 0.9 for c in filtered):
                continue
            seen.add(identity)
            filtered.append(
                Candidate(url, candidate.title, candidate.snippet, candidate.provider_rank)
            )
        if not filtered:
            return [], 0
        texts = [f"{d.title} {d.title} {d.snippet}" for d in filtered]
        context = f"{request.title} {request.summary} {' '.join(request.keywords)}"
        lexical = bm25(context, texts)
        similarities = None
        if self.model:
            # Bounded summaries: avoid silently encoding only the title of a long source page.
            query = f"{request.title[:200]}. {request.summary[:850]}"
            vectors = self.model.encode(
                [query, *texts], normalize_embeddings=True, show_progress_bar=False, batch_size=32
            )
            similarities = (vectors[1:] @ vectors[0]).tolist()
        # No zero-overlap filler in lexical mode. Dense mode has a tunable, uncalibrated floor.
        eligible = [
            i
            for i in range(len(filtered))
            if lexical[i] > 0 or (similarities is not None and similarities[i] >= 0.25)
        ]
        rankings = [sorted(eligible, key=lambda i: (-lexical[i], filtered[i].url))]
        if use_provider_rank:
            rankings.append(sorted(eligible, key=lambda i: filtered[i].provider_rank))
        if similarities is not None:
            rankings.append(sorted(eligible, key=lambda i: -similarities[i]))
        fusion = {i: 0.0 for i in eligible}
        for ranking in rankings:
            for rank, i in enumerate(ranking, 1):
                fusion[i] += 1 / (60 + rank)
        top_score = max(fusion.values(), default=1)
        relevance = {i: v / top_score for i, v in fusion.items()}
        selected, counts = [], Counter()
        while len(selected) < request.limit:
            available = [
                i for i in eligible if i not in selected and counts[host_of(filtered[i].url)] < 2
            ]
            if not available:
                break

            def utility(i: int) -> float:
                redundancy = max((jaccard(texts[i], texts[j]) for j in selected), default=0)
                return 0.8 * relevance[i] - 0.2 * redundancy

            best = max(available, key=lambda i: (utility(i), relevance[i], -i))
            selected.append(best)
            counts[host_of(filtered[best].url)] += 1
        output = []
        for i in selected:
            d = filtered[i]
            common = sorted(set(tokens(context)) & set(tokens(texts[i])))[:3]
            reason = (
                "Shared topics: " + ", ".join(common) if common else "Semantic topic similarity"
            )
            output.append(
                Recommendation(
                    id=hashlib.sha256(d.url.encode()).hexdigest()[:16],
                    url=d.url,
                    title=d.title,
                    snippet=d.snippet,
                    host=host_of(d.url),
                    reason=reason,
                    ranking_score=round(relevance[i], 5),
                )
            )
        return output, len(filtered)
