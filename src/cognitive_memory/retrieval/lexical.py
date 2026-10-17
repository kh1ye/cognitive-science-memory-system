from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _latin_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_+#.-]+", text.lower())


def _cjk_chars(text: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]", text)


def token_counter(text: str) -> Counter[str]:
    """Return a deterministic bilingual lexical representation.

    Character unigrams/bigrams make Chinese retrieval useful without a model;
    Latin words preserve common technical terms.  This is deliberately a
    replaceable local baseline rather than a semantic embedding.
    """

    normalized = normalize_text(text)
    words = _latin_words(normalized)
    chars = _cjk_chars(normalized)
    tokens: list[str] = [f"w:{word}" for word in words]
    tokens.extend(f"c:{char}" for char in chars)
    tokens.extend(f"g:{chars[i]}{chars[i + 1]}" for i in range(len(chars) - 1))
    return Counter(tokens)


def cosine_similarity(left: str, right: str) -> float:
    a = token_counter(left)
    b = token_counter(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
