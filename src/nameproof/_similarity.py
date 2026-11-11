"""Pure-Python string similarity, used when rapidfuzz isn't installed.

rapidfuzz is much faster and is used whenever it is available. This fallback lets
nameproof run where compiled extensions can't, such as in the browser (Pyodide).
Results equal rapidfuzz's ``normalized_similarity`` (tested).
"""

from __future__ import annotations

_PREFIX_WEIGHT = 0.1
_MAX_PREFIX = 4
_BOOST_THRESHOLD = 0.7


def levenshtein(left: str, right: str) -> float:
    """Return ``1 - edit distance / longer length``, in ``[0, 1]``."""
    if left == right:
        return 1.0
    longest = max(len(left), len(right))
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return 1.0 - previous[-1] / longest


def jaro(left: str, right: str) -> float:
    """Return the Jaro similarity of two strings, in ``[0, 1]``."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    window = max(max(len(left), len(right)) // 2 - 1, 0)
    left_hits = [False] * len(left)
    right_hits = [False] * len(right)
    matches = 0
    for i, a in enumerate(left):
        for j in range(max(0, i - window), min(len(right), i + window + 1)):
            if not right_hits[j] and right[j] == a:
                left_hits[i] = right_hits[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    mismatched = 0
    j = 0
    for i, a in enumerate(left):
        if left_hits[i]:
            while not right_hits[j]:
                j += 1
            mismatched += a != right[j]
            j += 1
    transpositions = mismatched // 2
    return (matches / len(left) + matches / len(right) + (matches - transpositions) / matches) / 3


def jaro_winkler(left: str, right: str) -> float:
    """Return Jaro similarity boosted for a shared prefix (up to 4 characters)."""
    similarity = jaro(left, right)
    if similarity <= _BOOST_THRESHOLD:
        return similarity
    prefix = 0
    for a, b in zip(left[:_MAX_PREFIX], right[:_MAX_PREFIX], strict=False):
        if a != b:
            break
        prefix += 1
    return similarity + prefix * _PREFIX_WEIGHT * (1.0 - similarity)
