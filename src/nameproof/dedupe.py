"""Find likely duplicates in a list of names (``nameproof dedupe``).

Comparing every pair in a list of 10,000 names means 50 million checks, so
names are first grouped by *keys*: one consonant key per name word, shared
across scripts (*Mohamed*, *Muhammad* and *محمد* all get the key ``md``). Only
names that share a key are compared, with the same rules as
:func:`nameproof.match`. A key that is too common
("Mohamed") is narrowed by a second word or an initial, so no comparison group
grows beyond ``max_group`` names. Identical names are grouped without being
compared at all.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations

from nameproof._types import MatchResult
from nameproof.explain import Reason
from nameproof.matcher import (
    _NOT_NAME_WORDS,
    _Form,
    _judge,
    _prepare_account,
    _prepare_provided,
    _usable_tokens,
)
from nameproof.policy import Policy, load_policy
from nameproof.translit import Mode, latin_readings, latin_skeleton, scripts

DEDUPE_POLICY = "records@1"
"""Default policy for duplicates: known spellings of one name ("Youssef", "Yusuf") match."""

MAX_GROUP = 64
"""Default largest comparison group; bigger key groups are narrowed first."""

_DUPLICATE = frozenset({MatchResult.MATCH, MatchResult.CLOSE_MATCH})
_ARTICLES = frozenset({"al", "el", "ul", "ar", "as", "ash", "at", "ad", "az", "an"})


@dataclass(frozen=True, slots=True)
class DuplicatePair:
    """Two names that look like the same person or organisation.

    ``first`` and ``second`` are positions in the input list (``first < second``).
    """

    first: int
    second: int
    result: MatchResult
    score: float
    explanation: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view with a stable key order."""
        return {
            "first": self.first,
            "second": self.second,
            "result": self.result.value,
            "score": self.score,
            "explanation": list(self.explanation),
        }


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Names linked by duplicate pairs; ``needs_review`` unless every link is a MATCH."""

    members: tuple[int, ...]
    needs_review: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view with a stable key order."""
        return {"members": list(self.members), "needs_review": self.needs_review}


@dataclass(frozen=True, slots=True)
class DedupeReport:
    """Everything :func:`find_duplicates` found, and what it could not check.

    ``compared`` counts the candidate pairs that were checked. ``unchecked``
    lists names that could not be compared (empty, too long, or in an
    unsupported script). ``crowded_keys`` counts keys so common that even after
    narrowing some of their names were not compared with each other; raise
    ``max_group`` if it is not zero.
    """

    pairs: tuple[DuplicatePair, ...]
    groups: tuple[DuplicateGroup, ...]
    compared: int
    unchecked: tuple[int, ...]
    crowded_keys: int
    policy_version: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view with a stable key order."""
        return {
            "policy_version": self.policy_version,
            "compared": self.compared,
            "crowded_keys": self.crowded_keys,
            "unchecked": list(self.unchecked),
            "groups": [group.to_dict() for group in self.groups],
            "pairs": [pair.to_dict() for pair in self.pairs],
        }


@dataclass(frozen=True, slots=True)
class _Prepared:
    index: int
    name: str
    provided: list[_Form]
    account: list[_Form]
    keys: frozenset[str]
    repeated: frozenset[str]  # keys shared by two words of the name ("Ivan Ivanov")
    initials: frozenset[str]


def find_duplicates(
    names: Sequence[str],
    *,
    policy: str | Policy = DEDUPE_POLICY,
    max_group: int = MAX_GROUP,
    jobs: int = 1,
    progress: Callable[[int, int], object] | None = None,
) -> DedupeReport:
    """Find names in ``names`` that likely belong to the same person or organisation.

    Every reported pair carries what :func:`nameproof.match` answers for the
    two names, checked once (on 20,000 benchmark pairs it gave the same answer
    in both directions). A ``CLOSE_MATCH`` pair should be reviewed by a person
    before records are merged. ``jobs`` spreads the comparisons over that many
    processes (worth it from a few thousand names); like any multiprocessing
    code, call it under ``if __name__ == "__main__":`` in a script.
    ``progress``, if given, is called with ``(done, total)`` comparisons as they finish.

    Raises:
        TypeError: if ``names`` is a single string instead of a sequence.
        ValueError: if ``max_group`` is below 2, ``jobs`` below 1, or ``policy`` is unknown.

    """
    if isinstance(names, str):
        msg = "names must be a sequence of names, not a single string"
        raise TypeError(msg)
    if max_group < 2:
        msg = "max_group must be at least 2"
        raise ValueError(msg)
    if jobs < 1:
        msg = "jobs must be at least 1"
        raise ValueError(msg)
    active = load_policy(policy)

    unchecked: list[int] = []
    identical: dict[str, list[int]] = defaultdict(list)
    prepared: list[_Prepared] = []
    for index, name in enumerate(names):
        entry = _prepare(index, name)
        if entry is None:
            unchecked.append(index)
            continue
        same = identical[" ".join(_usable_tokens(name) or ())]
        same.append(index)
        if len(same) == 1:  # later copies of the same name are never compared again
            prepared.append(entry)

    pairs = [
        DuplicatePair(copies[0], copy, MatchResult.MATCH, 1.0, ())
        for copies in identical.values()
        for copy in copies[1:]
    ]
    candidates, crowded = _candidates(prepared, max_group)
    pairs.extend(_compare_all(prepared, sorted(candidates), active, jobs, progress))
    pairs.sort(key=lambda pair: (pair.first, pair.second))
    return DedupeReport(
        pairs=tuple(pairs),
        groups=_groups(pairs),
        compared=len(candidates),
        unchecked=tuple(unchecked),
        crowded_keys=crowded,
        policy_version=active.id,
    )


def _prepare(index: int, name: str) -> _Prepared | None:
    provided = _prepare_provided(name)
    account = _prepare_account(name)
    if isinstance(provided, Reason) or not account:
        return None
    keys: set[str] = set()
    repeated: set[str] = set()
    initials: set[str] = set()
    for form in account:
        seen: set[str] = set()
        for token in form.tokens:
            skeleton = form.mode is Mode.SKELETON
            if len(token) == 1 and not skeleton:
                initials.add(_initial_key(token))
                continue
            if not skeleton and (
                not _latin(token) or token in _NOT_NAME_WORDS or token in _ARTICLES
            ):
                continue
            word = {key for key in word_keys(token, skeleton=skeleton) if len(key) > 1}
            if skeleton:
                word -= _SKELETON_STOP_KEYS
            repeated |= seen & word
            seen |= word
        keys |= seen
    if not keys and not initials:
        return None  # e.g. an unsupported script: nothing to compare it on
    return _Prepared(
        index, name, provided, account, frozenset(keys), frozenset(repeated), frozenset(initials)
    )


def word_key(word: str, *, skeleton: bool = False) -> str:
    """Return the blocking key of one normalised name word.

    The key is a deliberately coarse consonant skeleton, so spellings that may
    be the same name share it: inner *h* is dropped ("mohamed", "muhammad" and
    the Arabic skeleton "mhmd" all give ``md``), *g*/*j*/*h* and *b*/*v* are
    merged (Cyrillic *ghe* is *g* or *h*, Greek *beta* is *v*), and repeats collapse.
    A word too short to keep two consonants keeps its own spelling ("titov").
    ``skeleton`` marks a word that already is a consonant skeleton (Arabic).
    Keys only choose which names are compared; they never decide a verdict.
    """
    letters = word if skeleton else latin_skeleton(word)
    letters = letters[:1] + letters[1:].replace("h", "")
    letters = "".join(
        ch for index, ch in enumerate(letters) if index == 0 or ch != letters[index - 1]
    )
    key = letters.translate(_KEY_LETTERS)  # after collapsing, so "wb" (Waheeb) stays two letters
    return key if len(key) > 1 or skeleton else word


def word_keys(word: str, *, skeleton: bool = False) -> set[str]:
    """Keys of one word, with the readings a romanised word may hide.

    "ch" may be *k* or *sh*, so it gets both. Arabic names written as one Latin
    word also get the key of their second part: "Abdelmalek" is عبد المالك
    ("abd" + "malek") and "Benhabyles" is بن حبيلس ("ben" + "habyles").
    """
    keys = {word_key(word, skeleton=skeleton)}
    if skeleton:
        return keys
    keys.update(word_key(reading) for reading in latin_readings(word))  # "Guettaf" is قطاف
    if "ch" in word:
        keys.add(word_key(word.replace("ch", "kh")))
    glued = _GLUED_PREFIX.match(word)
    if glued:
        keys.add(word_key(glued.group("rest")))
    return keys


# "abd" + a vowel + the article ("el", or doubled sun letter: "abderrahmane"), or ben/bin/bou.
_GLUED_PREFIX = re.compile(
    r"^(?:abd[aeiou]?(?:l|(?=(?P<sun>[a-z])(?P=sun)))|ben|bin|bou)(?P<rest>[a-z]{3,})$"
)


def _initial_key(letter: str) -> str:
    """Key letter of an initial, consistent with :func:`word_key` ("v" -> "b", "e" -> "a")."""
    return (latin_skeleton(letter).translate(_KEY_LETTERS) or letter)[0]


_KEY_LETTERS = str.maketrans({"G": "j", "g": "j", "h": "j", "K": "k", "S": "s", "w": "b"})


# Arabic particles as skeletons: "bn" (بن), "abn" (ابن), "bnt" (بنت), "ab" (أبو).
_SKELETON_STOP_KEYS = frozenset(word_key(word) for word in ("bin", "ibn", "bint", "abu"))


def _latin(token: str) -> bool:
    return scripts(token) <= {"LATIN"}


def _candidates(prepared: list[_Prepared], max_group: int) -> tuple[set[tuple[int, int]], int]:
    """Pairs of positions in ``prepared`` worth comparing, and the crowded-key count."""
    by_key: dict[str, list[int]] = defaultdict(list)
    for position, entry in enumerate(prepared):
        for key in entry.keys:
            by_key[key].append(position)
    pairs: set[tuple[int, int]] = set()
    crowded = 0
    for key, members in by_key.items():
        if len(members) <= max_group:
            pairs.update(combinations(members, 2))
            continue
        narrowed: dict[str, list[int]] = defaultdict(list)
        for position in members:
            for sub_key in _narrowing_keys(prepared[position], key):
                narrowed[sub_key].append(position)
        overflow = False
        for group in narrowed.values():
            if len(group) <= max_group:
                pairs.update(combinations(group, 2))
            else:
                overflow = True
        crowded += overflow
    return pairs, crowded


def _narrowing_keys(entry: _Prepared, key: str) -> set[str]:
    """Second keys inside a crowded key: other words, their first letters, initials."""
    others = set(entry.keys - {key}) | (entry.repeated & {key})
    if not others and not entry.initials:
        return {""}  # a one-word name: compare it with the other one-word names
    return others | {"." + other[0] for other in others} | {"." + ch for ch in entry.initials}


_PARALLEL_MIN = 2_000  # fewer comparisons than this are faster in one process
_PROGRESS_STEP = 500  # comparisons between progress reports in one process
_worker: tuple[list[_Prepared], Policy] | None = None


def _compare_all(
    prepared: list[_Prepared],
    candidates: list[tuple[int, int]],
    policy: Policy,
    jobs: int,
    progress: Callable[[int, int], object] | None,
) -> list[DuplicatePair]:
    total = len(candidates)
    parallel = jobs > 1 and total >= _PARALLEL_MIN
    size = -(-total // (jobs * 4)) if parallel else _PROGRESS_STEP
    chunks = [candidates[start : start + size] for start in range(0, total, size)]
    found: list[DuplicatePair] = []
    done = 0
    if progress is not None:
        progress(0, total)
    if parallel:
        with ProcessPoolExecutor(
            jobs, initializer=_start_worker, initargs=(prepared, policy)
        ) as pool:
            results = pool.map(_worker_chunk, chunks)
            for chunk, chunk_found in zip(chunks, results, strict=True):
                found.extend(chunk_found)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        return found
    for chunk in chunks:
        found.extend(_compare_chunk(chunk, prepared, policy))
        done += len(chunk)
        if progress is not None:
            progress(done, total)
    return found


def _start_worker(prepared: list[_Prepared], policy: Policy) -> None:
    global _worker  # noqa: PLW0603 - per-process state, set once by the pool initializer
    _worker = (prepared, policy)


def _worker_chunk(chunk: list[tuple[int, int]]) -> list[DuplicatePair]:
    assert _worker is not None  # noqa: S101 - set by _start_worker
    return _compare_chunk(chunk, *_worker)


def _compare_chunk(
    chunk: list[tuple[int, int]], prepared: list[_Prepared], policy: Policy
) -> list[DuplicatePair]:
    found: list[DuplicatePair] = []
    for left, right in chunk:
        first, second = prepared[left], prepared[right]
        verdict = _judge(first.provided, [(second.name, second.account)], policy)
        if verdict.result in _DUPLICATE:
            found.append(
                DuplicatePair(
                    first.index, second.index, verdict.result, verdict.score, verdict.explanation
                )
            )
    return found


def _groups(pairs: list[DuplicatePair]) -> tuple[DuplicateGroup, ...]:
    """Join linked names into groups; a group needs review if any link is a CLOSE_MATCH."""
    parent: dict[int, int] = {}

    def root(item: int) -> int:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for pair in pairs:
        first, second = root(pair.first), root(pair.second)
        if first != second:
            parent[max(first, second)] = min(first, second)
    members: dict[int, list[int]] = defaultdict(list)
    for item in sorted(parent):
        members[root(item)].append(item)
    review = {root(pair.first) for pair in pairs if pair.result is not MatchResult.MATCH}
    return tuple(
        DuplicateGroup(tuple(items), needs_review=head in review)
        for head, items in sorted(members.items())
    )
