import unicodedata


def source_span(content: str, message: str) -> str | None:
    """Recover original evidence despite whitespace, casing or punctuation changes."""
    if content in message:
        return content

    def canonical(text):
        chars, positions = [], []
        for i, char in enumerate(text):
            for value in unicodedata.normalize("NFKC", char).casefold():
                if not value.isspace() and not unicodedata.category(value).startswith(
                    "P"
                ):
                    chars.append(value)
                    positions.append(i)
        return "".join(chars), positions

    needle, _ = canonical(content.rstrip("。！？.!?"))
    haystack, positions = canonical(message)
    start = haystack.find(needle) if needle else -1
    if start < 0:
        return None
    return message[positions[start] : positions[start + len(needle) - 1] + 1]
