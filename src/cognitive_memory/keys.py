from __future__ import annotations

import re


_KEY_ALIASES = {
    # Beverage preferences are one topic even when a model chooses a synonym.
    "beverage_preference": "preferred_beverage",
    "drink_preference": "preferred_beverage",
    "favorite_beverage": "preferred_beverage",
    "favorite_beverage_type": "preferred_beverage",
    "favorite_drink": "preferred_beverage",
    "favorite_drink_type": "preferred_beverage",
    "favourite_beverage": "preferred_beverage",
    "favourite_drink": "preferred_beverage",
    "preferred_beverage": "preferred_beverage",
    "preferred_drink": "preferred_beverage",
    "coffee_preference": "preferred_beverage",
    "milk_preference": "preferred_beverage",
    "tea_preference": "preferred_beverage",
    "water_preference": "preferred_beverage",
    "饮品偏好": "preferred_beverage",
    "饮料偏好": "preferred_beverage",
    # Keep the other commonly demonstrated preference stable as well.
    "coding_language": "preferred_programming_language",
    "primary_programming_language": "preferred_programming_language",
    "preferred_coding_language": "preferred_programming_language",
    "preferred_programming_language": "preferred_programming_language",
    "programming_language": "preferred_programming_language",
}


def canonicalize_memory_key(value: str | None) -> str | None:
    """Return a stable topic key for known model-generated aliases.

    Unknown keys are preserved after conservative snake-case normalization so
    the memory engine remains extensible instead of collapsing unrelated topics.
    """

    if value is None:
        return None
    normalized = re.sub(r"[^\w]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        return None
    return _KEY_ALIASES.get(normalized, normalized)


def canonicalize_memory_value(
    memory_key: str | None,
    value: str | None,
    content: str = "",
) -> str | None:
    """Normalize values only for controlled topics with known vocabularies."""

    raw_value = (value or "").strip()
    sources = (raw_value, content)
    if memory_key == "preferred_beverage":
        for source in sources:
            matches = [
                beverage
                for beverage in ("咖啡", "牛奶", "茶", "水")
                if beverage in source
            ]
            if len(matches) == 1:
                return matches[0]
    if memory_key == "preferred_programming_language":
        patterns = (
            (r"javascript", "JavaScript"),
            (r"python", "Python"),
            (r"rust", "Rust"),
            (r"java", "Java"),
            (r"(?:^|\W)go(?:$|\W)", "Go"),
        )
        for source in sources:
            matches = [
                canonical
                for pattern, canonical in patterns
                if re.search(pattern, source, flags=re.IGNORECASE)
            ]
            # "JavaScript" also contains "Java"; keep the more specific match.
            if "JavaScript" in matches and "Java" in matches:
                matches.remove("Java")
            if len(matches) == 1:
                return matches[0]
    return raw_value or None
