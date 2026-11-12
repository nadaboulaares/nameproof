"""Token similarity and best one-to-one alignment between two names."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
from itertools import permutations

from nameproof.arabic_names import different_known, same_name

try:
    from rapidfuzz.distance import JaroWinkler, Levenshtein

    _jaro_winkler: Callable[[str, str], float] = JaroWinkler.normalized_similarity
    _levenshtein: Callable[[str, str], float] = Levenshtein.normalized_similarity
except ImportError:  # pragma: no cover - e.g. in the browser (Pyodide)
    from nameproof._similarity import jaro_winkler as _jaro_winkler
    from nameproof._similarity import levenshtein as _levenshtein

# Similarity credited when an initial agrees with a full token ("J" ~ "John"),
# or a word is abbreviated to its first letters ("Corp" ~ "Corporation").
INITIAL_SIMILARITY = 0.9
ABBREVIATION_SIMILARITY = 0.9
KNOWN_VARIANT_SIMILARITY = 0.9
# Two known names of different Arabic names ("Mohammed", "Mahmoud") look alike but
# are different names: their similarity is capped below any close-match bar.
KNOWN_DIFFERENT_SIMILARITY = 0.5
MIN_ABBREVIATION = 3

# Informal romanisations and Arabic skeletons are guesses: identical output is
# credited this much, which clears the close-match bar but never counts as exact.
APPROXIMATE_FACTOR = 0.92

# Up to this many tokens on the longer side, try every assignment (5! = 120);
# beyond it, fall back to greedy so crafted inputs can't blow up the runtime.
BRUTE_FORCE_LIMIT = 5


class PairKind(StrEnum):
    """How two aligned tokens relate."""

    EXACT = "exact"
    INITIAL = "initial"
    ABBREVIATION = "abbreviation"
    VARIANT = "variant"  # known spellings of one Arabic name ("Hussein", "Hocine")
    FUZZY = "fuzzy"


@lru_cache(maxsize=8192)
def token_similarity(left: str, right: str) -> tuple[float, PairKind]:
    """Score two normalised tokens in ``[0, 1]`` and say how they relate.

    Known spellings of one Arabic name ("Youssef", "Yusuf") are a variant.
    Fuzzy similarity averages Jaro-Winkler (forgiving of typos late in the word)
    with normalised Levenshtein (strict on short words), so "Maria" vs "Mario"
    stays well below an exact match.
    """
    if left == right:
        return 1.0, PairKind.EXACT
    if len(left) == 1 or len(right) == 1:
        if left[0] == right[0]:
            return INITIAL_SIMILARITY, PairKind.INITIAL
        return 0.0, PairKind.FUZZY
    if same_name(left, right):
        return KNOWN_VARIANT_SIMILARITY, PairKind.VARIANT
    different = different_known(left, right)  # "Samir" is not short for "Samira"
    short, long = sorted((left, right), key=len)
    if not different and len(short) >= MIN_ABBREVIATION and long.startswith(short):
        return ABBREVIATION_SIMILARITY, PairKind.ABBREVIATION
    jaro_winkler = _jaro_winkler(left, right)
    levenshtein = _levenshtein(left, right)
    similarity = (jaro_winkler + levenshtein) / 2
    if different:
        similarity = min(similarity, KNOWN_DIFFERENT_SIMILARITY)
    return similarity, PairKind.FUZZY


@dataclass(frozen=True, slots=True)
class Pair:
    """One aligned token pair (indices into the left and right token lists)."""

    left: int
    right: int
    similarity: float
    kind: PairKind


@dataclass(frozen=True, slots=True)
class Alignment:
    """Best assignment of the shorter name's tokens onto the longer name's tokens."""

    pairs: tuple[Pair, ...]
    unmatched: int

    @property
    def reordered(self) -> bool:
        """Whether the tokens were matched in a different order ("Smith John")."""
        rights = [pair.right for pair in sorted(self.pairs, key=lambda pair: pair.left)]
        return rights != sorted(rights)

    def score(self, missing_token_penalty: float) -> float:
        """Mean pair similarity, reduced for every token left without a partner."""
        if not self.pairs:
            return 0.0
        mean = sum(pair.similarity for pair in self.pairs) / len(self.pairs)
        return max(0.0, mean * (1.0 - missing_token_penalty * self.unmatched))


def align(left: tuple[str, ...], right: tuple[str, ...]) -> Alignment:
    """Align two token lists, maximising total similarity regardless of order."""
    swapped = len(left) > len(right)
    short, long = (right, left) if swapped else (left, right)
    sims = [[token_similarity(s, t) for t in long] for s in short]
    if len(long) <= BRUTE_FORCE_LIMIT:
        assignment = _best_assignment(sims, len(long))
    else:
        assignment = _greedy_assignment(sims)
    pairs = tuple(
        Pair(
            left=long_index if swapped else short_index,
            right=short_index if swapped else long_index,
            similarity=sims[short_index][long_index][0],
            kind=sims[short_index][long_index][1],
        )
        for short_index, long_index in enumerate(assignment)
    )
    return Alignment(pairs=pairs, unmatched=len(long) - len(short))


def approximate(alignment: Alignment, factor: float = APPROXIMATE_FACTOR) -> Alignment:
    """Scale an alignment built from approximate spellings so nothing in it is exact."""
    pairs = tuple(
        replace(
            pair,
            similarity=pair.similarity * factor,
            kind=pair.kind if pair.kind is not PairKind.EXACT else PairKind.FUZZY,
        )
        for pair in alignment.pairs
    )
    return replace(alignment, pairs=pairs)


def _best_assignment(sims: list[list[tuple[float, PairKind]]], width: int) -> tuple[int, ...]:
    def key(perm: tuple[int, ...]) -> tuple[float, int, bool]:
        total = sum(sims[i][j][0] for i, j in enumerate(perm))
        exact = sum(sims[i][j][1] is PairKind.EXACT for i, j in enumerate(perm))
        return round(total, 9), exact, list(perm) == sorted(perm)

    return max(permutations(range(width), len(sims)), key=key)


def _greedy_assignment(sims: list[list[tuple[float, PairKind]]]) -> tuple[int, ...]:
    candidates = sorted(
        ((sim[0], i, j) for i, row in enumerate(sims) for j, sim in enumerate(row)),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    chosen: dict[int, int] = {}
    used: set[int] = set()
    for _, i, j in candidates:
        if i not in chosen and j not in used:
            chosen[i] = j
            used.add(j)
    return tuple(chosen[i] for i in range(len(sims)))
