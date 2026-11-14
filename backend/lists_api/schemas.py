import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .safety import canonical_url, redact


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    page_url: str = Field(max_length=2048)
    title: str = Field(min_length=3, max_length=300)
    summary: str = Field(min_length=40, max_length=1800)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    language: Literal["en"] = "en"
    limit: int = Field(default=10, ge=1, le=10, strict=True)
    exclude_same_host: bool = Field(default=True, strict=True)
    ranking: Literal["auto", "lexical", "semantic", "fine_tuned"] = "auto"

    @field_validator("page_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        return canonical_url(value, drop_query=True)

    @field_validator("title", "summary", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Text must be a string")
        value = redact(re.sub(r"\s+", " ", value)).strip()
        if not value:
            raise ValueError("Empty text")
        return value

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values: list[str]) -> list[str]:
        if any(not isinstance(v, str) or len(v) > 60 for v in values):
            raise ValueError("Keywords must be strings up to 60 characters")
        cleaned = [redact(v).strip() for v in values]
        return list(dict.fromkeys(v for v in cleaned if v and v != "[redacted]"))


class Recommendation(BaseModel):
    id: str
    url: str
    title: str
    snippet: str
    host: str
    reason: str
    ranking_score: float
    lexical_score: float = 0.0
    semantic_similarity: float | None = None
    provider_rank: int | None = None


class RecommendResponse(BaseModel):
    request_id: str
    mode: Literal["demo", "live"]
    ranker: str
    recommendations: list[Recommendation]
    warnings: list[str]
    candidate_count: int
    cached: bool
    elapsed_ms: float
    timings_ms: dict[str, float] = Field(default_factory=dict)
    pipeline_version: str = "lists-v2"


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text_a: str = Field(min_length=3, max_length=1800)
    text_b: str = Field(min_length=3, max_length=1800)

    @field_validator("text_a", "text_b", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return RecommendRequest.clean_text(value)
