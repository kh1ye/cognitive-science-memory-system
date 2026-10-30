"""Rank evidence, not serialization metadata; preserve bounded source context."""
from collections import Counter
import math
import re

from .lexical import token_counter

STOP_WORDS = frozenset("a an the i me my we our you your it its is are was were be been do did does have has had of to in on at for from with and or that this what which how when where say said please can could would should".split())


def terms(text):
    # Punctuation differences (including hyphenated words) must not hide evidence.
    text = re.sub(r"[-_./]", " ", str(text))
    tokens = token_counter(text)
    result = Counter()
    for token, count in tokens.items():
        if token.startswith("w:"):
            word = token[2:]
            if word in STOP_WORDS:
                continue
            if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
                token = "w:" + word[:-1]
        result[token] += count
    return result


def rank(query, documents):
    """BM25 scores over the visible candidate corpus (no model or gold labels)."""
    corpus = [terms(text) for text in documents]
    q = terms(query)
    if not corpus or not q:
        return [0.0] * len(corpus)
    average = sum(sum(c.values()) for c in corpus) / len(corpus) or 1
    frequencies = Counter(token for doc in corpus for token in doc)
    scores = []
    for doc in corpus:
        length = sum(doc.values())
        score = 0.0
        for token in q:
            tf = doc.get(token, 0)
            if tf:
                idf = math.log(1 + (len(corpus) - frequencies[token] + .5) / (frequencies[token] + .5))
                score += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * length / average))
        scores.append(score)
    return scores
