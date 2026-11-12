"""Common Arabic given names and their usual Latin spellings.

Arabic script leaves short vowels unwritten, so a consonant skeleton cannot tell
*Mohamed* (محمد) from *Mahmoud* (محمود): both are m-h-m-d. A list of known names
settles the common cases: *Hussein* and *Hocine* are the same name, *Mahmoud* and
*محمد* are not. Names that are not in the list are left to the skeleton rules.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from importlib.resources import files

_DATA = files("nameproof") / "data" / "arabic_given_names.tsv"
_LONGEST = 3  # words a known name can span ("abd el kader")
# One spelling per letter: alef with hamza or madda, alef maqsura, ta marbuta, hamza
# seats, and the tatweel stretching character.
_ARABIC_FOLDS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه",  # noqa: RUF001
                               "ؤ": "و", "ئ": "ي", "ـ": None})  # fmt: skip


def arabic_key(text: str) -> str:
    """Normalise Arabic for lookups: no vowel marks, one alef, no article, no spaces."""
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("M"))
    text = text.translate(_ARABIC_FOLDS).replace(" ", "")
    return text[2:] if text.startswith("ال") and len(text) > 3 else text


def latin_key(text: str) -> str:
    """Normalise a Latin spelling for lookups: lower case letters only, no accents."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if "a" <= ch <= "z")


@lru_cache(maxsize=1)
def _tables() -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    by_arabic: dict[str, set[str]] = {}
    by_latin: dict[str, set[str]] = {}
    for line in _DATA.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        arabic, spellings = line.split("\t")
        key = arabic_key(arabic)
        for spelling in spellings.split(","):
            by_arabic.setdefault(key, set()).add(spelling)
            by_latin.setdefault(spelling, set()).add(key)
    return (
        {key: frozenset(value) for key, value in by_arabic.items()},
        {key: frozenset(value) for key, value in by_latin.items()},
    )


def arabic_spellings(spelling: str) -> frozenset[str]:
    """Arabic names (as :func:`arabic_key`) that ``spelling`` is a known spelling of."""
    return _tables()[1].get(latin_key(spelling), frozenset())


def same_name(left: str, right: str) -> bool:
    """Whether two different Latin spellings are known spellings of one Arabic name."""
    left_key, right_key = latin_key(left), latin_key(right)
    if left_key == right_key:
        return False
    by_latin = _tables()[1]
    return bool(by_latin.get(left_key, frozenset()) & by_latin.get(right_key, frozenset()))


def different_known(left: str, right: str) -> bool:
    """Whether two words are known names of different Arabic names.

    Works for Latin spellings ("Mohammed" vs "Mahmoud") and Arabic script (محمد
    vs محمود), which look alike but are different names.
    """
    left_names, right_names = _known(left), _known(right)
    return bool(left_names) and bool(right_names) and not left_names & right_names


def _known(word: str) -> frozenset[str]:
    by_arabic, by_latin = _tables()
    names = by_latin.get(latin_key(word))
    if names:
        return names
    key = arabic_key(word)
    return frozenset({key}) if key in by_arabic else frozenset()


def latin_names(tokens: Sequence[str]) -> list[frozenset[str]]:
    """Known names in a Latin name, as the Arabic names each may stand for."""
    by_latin = _tables()[1]
    return [by_latin[key] for key in _scan(tokens, latin_key, by_latin)]


def arabic_names(tokens: Sequence[str]) -> list[str]:
    """Known names in an Arabic-script name (as :func:`arabic_key`)."""
    return _scan(tokens, arabic_key, _tables()[0])


def different_names(left: Sequence[str], right: Sequence[str]) -> bool:
    """Whether two names hold known given names that don't correspond.

    Each side may be Latin or Arabic script. True only when *both* sides have a
    known name with no counterpart on the other ("Mahmoud Ali" vs "محمد علي").
    A name missing from the list never triggers it, nor does a name present on
    one side only, a name that an initial on the other side may stand for ("A."
    for أحمد), or a short form of a compound name ("Hamid" for عبد الحميد).
    """
    left_names, right_names = known_names(left), known_names(right)
    if not left_names or not right_names:
        return False

    def paired(name: frozenset[str], others: list[frozenset[str]], tokens: Sequence[str]) -> bool:
        initials = {key for key in map(latin_key, tokens) if len(key) == 1}
        by_arabic = _tables()[0]
        if any(spelling[0] in initials for option in name for spelling in by_arabic[option]):
            return True
        return any(_parts(name) & other or _parts(other) & name for other in others)

    return any(not paired(name, right_names, right) for name in left_names) and any(
        not paired(name, left_names, left) for name in right_names
    )


def known_names(tokens: Sequence[str]) -> list[frozenset[str]]:
    """Known given names in a name, each as the Arabic names it may stand for."""
    found = latin_names(tokens)
    found.extend(frozenset({name}) for name in arabic_names(tokens))
    return found


def _parts(names: frozenset[str]) -> set[str]:
    """Names and the short forms they go by ("Hamid" for عبد الحميد, "Nour" for نور الدين)."""
    parts = set(names)
    for name in names:
        if name.startswith("عبد") and len(name) > 5:
            parts.add(arabic_key(name[3:]))
        if name.endswith("الدين") and len(name) > 6:
            parts.add(name[:-5])
    return parts


def _scan(
    tokens: Sequence[str], normalise: Callable[[str], str], table: Mapping[str, frozenset[str]]
) -> list[str]:
    """Longest-first scan for known names, which may span up to three words."""
    found: list[str] = []
    index = 0
    while index < len(tokens):
        for size in range(min(_LONGEST, len(tokens) - index), 0, -1):
            candidate = normalise("".join(tokens[index : index + size]))
            if candidate in table:
                found.append(candidate)
                index += size
                break
        else:
            index += 1
    return found
