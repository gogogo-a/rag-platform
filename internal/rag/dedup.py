"""RAG result deduplication helpers."""
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List


def normalize_text_for_deduplication(text: str) -> str:
    normalized = re.sub(r"\s+", "", text or "")
    normalized = re.sub(r"\d+", "", normalized)
    return normalized


def text_similarity(left: str, right: str) -> float:
    left_normalized = normalize_text_for_deduplication(left)
    right_normalized = normalize_text_for_deduplication(right)
    if not left_normalized or not right_normalized:
        return 0.0
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def deduplicate_results(
    results: List[Dict[str, Any]],
    score_diff_threshold: float = 0.02,
    text_similarity_threshold: float = 0.88,
    target_count: int = 5,
) -> List[Dict[str, Any]]:
    if not results:
        return []

    score_field = "rerank_score" if "rerank_score" in results[0] else "vector_score"
    sorted_results = sorted(results, key=lambda x: x.get(score_field, 0), reverse=True)
    deduplicated = []
    for current in sorted_results:
        current_text = current.get("text", "")
        if any(text_similarity(current_text, selected.get("text", "")) >= text_similarity_threshold for selected in deduplicated):
            continue
        deduplicated.append(current)
        if len(deduplicated) >= target_count:
            break

    return deduplicated
