"""Romanisation of Greek, Cyrillic and Arabic names.

Every name is rendered in several ways. Official schemes are ``EXACT``: when
their output is identical to the other name it may ``MATCH``. Informal spellings
(``APPROXIMATE``) and the Arabic consonant skeleton (``SKELETON``) can at most
give ``CLOSE_MATCH``, because they are guesses rather than standards.

- Greek: ELOT 743 (used in Greek passports); informal phonetic spelling.
- Cyrillic: ICAO 9303, BGN/PCGN, the English-media convention, the Bulgarian
  and Ukrainian national systems, and Serbian Latin.
- Arabic: a consonant skeleton compared against the Latin name's skeleton,
  since Arabic usually leaves short vowels unwritten.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from itertools import islice, product

from nameproof.explain import Reason


class Mode(StrEnum):
    """How far a rendering can be trusted."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    SKELETON = "skeleton"


_SEVERITY = {Mode.EXACT: 0, Mode.APPROXIMATE: 1, Mode.SKELETON: 2}
_APPROXIMATE_REASONS: tuple[Reason, ...] = (
    Reason.TRANSLITERATED,
    Reason.APPROXIMATE_TRANSLITERATION,
)


def worst(*modes: Mode) -> Mode:
    """Return the least trustworthy of ``modes``."""
    return max(modes, key=_SEVERITY.__getitem__)


@dataclass(frozen=True, slots=True)
class Rendering:
    """One way of writing a name, with how far it can be trusted."""

    text: str
    mode: Mode
    reasons: tuple[Reason, ...] = ()


def scripts(text: str) -> frozenset[str]:
    """Return the Unicode scripts of the letters in ``text`` ("LATIN", "GREEK", ...)."""
    return frozenset(
        unicodedata.name(ch, "UNKNOWN").split(" ", 1)[0] for ch in text if ch.isalpha()
    )


def renderings(text: str) -> list[Rendering]:
    """Return ``text`` itself plus every romanisation that applies to it.

    ``text`` must already be normalised (casefolded, see ``normalize_text``).
    """
    found = scripts(text)
    options: list[list[tuple[Callable[[str], str], Mode]]] = []
    if "GREEK" in found:
        options.append([(greek_elot743, Mode.EXACT), (greek_phonetic, Mode.APPROXIMATE)])
    if "CYRILLIC" in found:
        options.append(
            [(partial(cyrillic, scheme=scheme), Mode.EXACT) for scheme in _cyrillic_schemes(text)]
        )

    result: dict[tuple[str, Mode], Rendering] = {(text, Mode.EXACT): Rendering(text, Mode.EXACT)}
    for combo in product(*options) if options else ():
        out, mode = text, Mode.EXACT
        for transliterate, scheme_mode in combo:
            out, mode = transliterate(out), worst(mode, scheme_mode)
        reasons = _APPROXIMATE_REASONS if mode is not Mode.EXACT else (Reason.TRANSLITERATED,)
        result.setdefault((out, mode), Rendering(out, mode, reasons))
    if "ARABIC" in found:
        skeleton = arabic_skeleton(text)
        if skeleton:
            result.setdefault(
                (skeleton, Mode.SKELETON),
                Rendering(skeleton, Mode.SKELETON, _APPROXIMATE_REASONS),
            )
    return list(result.values())


# --- Greek -----------------------------------------------------------------

_GREEK_SINGLE = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th",
    "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p",
    "ρ": "r", "σ": "s", "τ": "t", "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}  # fmt: skip
_PHONETIC_SINGLE = {**_GREEK_SINGLE, "υ": "i", "χ": "h"}
_GREEK_VOWELS = frozenset("αεηιουω")
# αυ/ευ/ηυ are read "v" before vowels and voiced consonants, "f" otherwise.
_UPSILON_DIPHTHONGS = {"α": "a", "ε": "e", "η": "i"}
_VOICED_NEXT = _GREEK_VOWELS | frozenset("βγδζλμνρ")
_FIXED_PAIRS = {"ου": "ou", "γγ": "ng", "γξ": "nx", "γχ": "nch"}
_PHONETIC_PAIRS = {**_FIXED_PAIRS, "αι": "e", "ει": "i", "οι": "i", "υι": "i", "τζ": "tz"}

_GreekLetter = tuple[str, bool]  # (base letter, has dialytika)


def _greek_letters(word: str) -> list[_GreekLetter]:
    letters: list[_GreekLetter] = []
    for ch in word:
        if "GREEK" not in unicodedata.name(ch, ""):
            letters.append((ch, False))
            continue
        decomposed = unicodedata.normalize("NFD", ch)
        base = "σ" if decomposed[0] == "ς" else decomposed[0]
        letters.append((base, "\u0308" in decomposed))  # combining diaeresis
    return letters


def _positional_pair(pair: str, index: int, length: int, *, phonetic: bool) -> str | None:
    """Digraphs whose reading depends on where they sit in the word."""
    edge = index == 0 or index + 2 == length
    if pair == "μπ":
        return "b" if edge or phonetic else "mp"
    if pair == "ντ":
        return "d" if edge or phonetic else "nt"
    if pair == "γκ":
        return "g" if index == 0 else "ng"
    return None


def _greek_word(word: str, *, phonetic: bool) -> str:
    letters = _greek_letters(word)
    singles = _PHONETIC_SINGLE if phonetic else _GREEK_SINGLE
    pairs = _PHONETIC_PAIRS if phonetic else _FIXED_PAIRS
    out: list[str] = []
    index, length = 0, len(letters)
    while index < length:
        letter = letters[index][0]
        follower, follower_dialytika = letters[index + 1] if index + 1 < length else ("", True)
        third = letters[index + 2][0] if index + 2 < length else ""
        pair = "" if follower_dialytika else letter + follower
        if letter in _UPSILON_DIPHTHONGS and pair.endswith("υ"):
            sound = "v" if third in _VOICED_NEXT else "f"
            out.append(_UPSILON_DIPHTHONGS[letter] + sound)
            index += 2
        elif (reading := _positional_pair(pair, index, length, phonetic=phonetic)) is not None:
            out.append(reading)
            index += 2
        elif pair in pairs:
            out.append(pairs[pair])
            index += 2
        elif phonetic and letter == "γ" and follower == "ι" and third in _GREEK_VOWELS:
            out.append("y")  # "Γιάννης" -> "Yannis"
            index += 2
        elif phonetic and letter == "γ" and follower in "εηι":
            out.append("y")
            index += 1
        else:
            out.append(singles.get(letter, letter))
            index += 1
    return "".join(out)


def greek_elot743(text: str) -> str:
    """Romanise Greek letters with ELOT 743 (ISO 843 type 2, used in passports)."""
    return " ".join(_greek_word(word, phonetic=False) for word in text.split(" "))


def greek_phonetic(text: str) -> str:
    """Romanise Greek letters the informal way people often write them."""
    return " ".join(_greek_word(word, phonetic=True) for word in text.split(" "))


# --- Cyrillic --------------------------------------------------------------

_CYRILLIC_VOWELS = frozenset("аеёиоуыэюяєії")
_SOFTENERS = frozenset("ъьй")


@dataclass(frozen=True, slots=True)
class CyrillicScheme:
    """A Cyrillic romanisation table with its positional rules."""

    name: str
    table: dict[str, str]
    initial: dict[str, str] = field(default_factory=dict)
    after_vowel: dict[str, str] = field(default_factory=dict)
    clusters: dict[str, str] = field(default_factory=dict)
    endings: dict[str, str] = field(default_factory=dict)


_ICAO_TABLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "ie", "ы": "y", "ь": "", "э": "e", "ю": "iu",
    "я": "ia", "є": "ie", "і": "i", "ї": "i", "ґ": "g", "ў": "u", "ђ": "d", "ј": "j",
    "љ": "lj", "њ": "nj", "ћ": "c", "џ": "dz", "ѓ": "g", "ќ": "k", "ѕ": "dz",
}  # fmt: skip

ICAO_9303 = CyrillicScheme("icao-9303", _ICAO_TABLE)

BGN_PCGN = CyrillicScheme(
    "bgn-pcgn",
    {**_ICAO_TABLE, "й": "y", "ъ": "", "ю": "yu", "я": "ya"},
    initial={"е": "ye", "ё": "yo"},
    after_vowel={"е": "ye", "ё": "yo"},
)

BULGARIAN = CyrillicScheme(
    "bulgarian-2009",
    {**_ICAO_TABLE, "й": "y", "х": "h", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya"},
    endings={"ия": "ia"},
)

UKRAINIAN = CyrillicScheme(
    "ukrainian-2010",
    {**_ICAO_TABLE, "г": "h", "и": "y"},
    initial={"є": "ye", "ї": "yi", "й": "y", "ю": "yu", "я": "ya"},
    clusters={"зг": "zgh"},
)

SERBIAN_LATIN = CyrillicScheme(
    "serbian-latin",
    {
        **_ICAO_TABLE,
        "ђ": "đ", "ж": "ž", "х": "h", "ц": "c", "ч": "č", "ћ": "ć", "џ": "dž", "ш": "š",
        "ѓ": "ǵ", "ќ": "ḱ",
    },
)  # fmt: skip

# The convention of English-language media and Wikipedia ("Pyotr", "Fyodor",
# "Dmitry", "Yury"): BGN/PCGN simplified, with ё -> yo and final -ий -> y.
ENGLISH_COMMON = CyrillicScheme(
    "english-common",
    {**_ICAO_TABLE, "й": "y", "ё": "yo", "ъ": "", "ю": "yu", "я": "ya"},
    initial={"е": "ye"},
    after_vowel={"е": "ye"},
    clusters={
        "ье": "ye", "ья": "ya", "ью": "yu", "ьи": "yi", "ьё": "yo",
        "жё": "zho", "чё": "cho", "шё": "sho", "щё": "shcho",
    },
    endings={"ий": "y", "ый": "y"},
)  # fmt: skip

_SERBIAN_ONLY = frozenset("ђјљњћџѓќѕ")
_UKRAINIAN_ONLY = frozenset("іїєґ")


def _cyrillic_schemes(text: str) -> list[CyrillicScheme]:
    if any(ch in _SERBIAN_ONLY for ch in text):
        return [SERBIAN_LATIN, ICAO_9303]
    if any(ch in _UKRAINIAN_ONLY for ch in text):
        return [UKRAINIAN, ICAO_9303]
    return [ICAO_9303, BGN_PCGN, ENGLISH_COMMON, BULGARIAN, UKRAINIAN]


def _cyrillic_letter(word: str, index: int, scheme: CyrillicScheme) -> str:
    letter = word[index]
    previous = word[index - 1] if index else ""
    if index == 0 and letter in scheme.initial:
        return scheme.initial[letter]
    if (previous in _CYRILLIC_VOWELS or previous in _SOFTENERS) and letter in scheme.after_vowel:
        return scheme.after_vowel[letter]
    return scheme.table.get(letter, letter)


def _cyrillic_word(word: str, scheme: CyrillicScheme) -> str:
    out: list[str] = []
    index = 0
    while index < len(word):
        rest = word[index:]
        if rest in scheme.endings:
            out.append(scheme.endings[rest])
            break
        if rest[:2] in scheme.clusters:
            out.append(scheme.clusters[rest[:2]])
            index += 2
            continue
        out.append(_cyrillic_letter(word, index, scheme))
        index += 1
    return "".join(out)


def cyrillic(text: str, scheme: CyrillicScheme = ICAO_9303) -> str:
    """Romanise Cyrillic letters in ``text`` with ``scheme``."""
    return " ".join(_cyrillic_word(word, scheme) for word in text.split(" "))


# --- Arabic consonant skeleton ---------------------------------------------
# Capital letters stand for sounds written with two Latin letters:
# K = kh, G = gh, S = sh/ch.

_ARABIC_CONSONANTS = {
    "ب": "b", "ت": "t", "ث": "t", "ج": "j", "ح": "h", "خ": "K", "د": "d", "ذ": "d",
    "ر": "r", "ز": "z", "س": "s", "ش": "S", "ص": "s", "ض": "d", "ط": "t", "ظ": "z",
    "غ": "G", "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h",
    "پ": "b", "چ": "S", "ژ": "j", "گ": "j", "ک": "k",
}  # fmt: skip
_ALEF_OR_AIN = frozenset("اأإآٱع")
_SILENT = frozenset("ءؤئىة")
_ARABIC_GLIDES = {"و": "w", "ي": "y", "ی": "y"}
_ARABIC_ARTICLE = "ال"
_TATWEEL = "ـ"


def _arabic_word(word: str) -> str:
    word = "".join(
        ch for ch in word if ch != _TATWEEL and not unicodedata.category(ch).startswith("M")
    )
    if word.startswith(_ARABIC_ARTICLE) and len(word) > len(_ARABIC_ARTICLE):
        word = word[len(_ARABIC_ARTICLE) :]
    out: list[str] = []
    last = len(word) - 1
    for index, ch in enumerate(word):
        if ch in _ALEF_OR_AIN:
            out.append("a" if index == 0 else "")
        elif ch in _ARABIC_GLIDES:
            out.append(_ARABIC_GLIDES[ch] if index == 0 else "")
        elif ch in _SILENT or (ch == "ه" and 0 < index == last):
            continue
        else:
            out.append(_ARABIC_CONSONANTS.get(ch, ch))
    return _collapse("".join(out))


def arabic_skeleton(text: str) -> str:
    """Reduce a name to consonants, keeping a marker for a word-initial vowel.

    Arabic words go through the Arabic table; Latin words through
    :func:`latin_skeleton`, so mixed names still compare.
    """
    words = (
        _arabic_word(word) if "ARABIC" in scripts(word) else latin_skeleton(word)
        for word in text.replace("-", " ").split()
    )
    return " ".join(word for word in words if word)


_LATIN_CLUSTERS = {
    "sch": "S", "kh": "K", "gh": "G", "sh": "S", "ch": "S", "th": "t", "dh": "d",
    "dj": "j", "ph": "f", "ck": "k",
}  # fmt: skip
_LATIN_SINGLE = {"q": "k", "c": "k", "g": "j", "p": "b", "x": "ks", "v": "w"}
_LATIN_VOWELS = frozenset("aeiou")
_LATIN_GLIDES = frozenset("yw")
_LATIN_ARTICLES = frozenset({"al", "el", "ul", "ar", "as", "ash", "at", "ad", "az", "an"})


def latin_skeleton(word: str) -> str:
    """Reduce a romanised Arabic word to its consonant skeleton ("mohammed" -> "mhmd")."""
    if len(word) > 2 and word[-1] == "h" and word[-2] in _LATIN_VOWELS:
        word = word[:-1]  # "Fatimah" and "Fatima" are the same name
    out: list[str] = []
    index = 0
    while index < len(word):
        cluster = next(
            (
                word[index : index + size]
                for size in (3, 2)
                if word[index : index + size] in _LATIN_CLUSTERS
            ),
            None,
        )
        if cluster is not None:
            out.append(_LATIN_CLUSTERS[cluster])
            index += len(cluster)
            continue
        letter = _LATIN_SINGLE.get(word[index], word[index])
        if letter in _LATIN_VOWELS:
            out.append("a" if index == 0 else "")
        elif letter in _LATIN_GLIDES:
            out.append(letter if index == 0 else "")
        else:
            out.append(letter)
        index += 1
    return _collapse("".join(out))


def latin_skeleton_variants(tokens: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Return skeleton spellings of a Latin name for comparison with Arabic script.

    Articles ("al", "el", "ar"...) before another word are dropped, and words
    fused with the article ("Abdel", "Abdul") also get the bare "abd" form.
    """
    kept = [
        token
        for index, token in enumerate(tokens)
        if not (token in _LATIN_ARTICLES and index < len(tokens) - 1)
    ]
    options: list[list[str]] = []
    for token in kept:
        skeleton = latin_skeleton(token)
        alternatives = [skeleton]
        if skeleton.startswith("abdl"):
            alternatives.append("abd" + skeleton[4:])
        options.append(alternatives)
    return [tuple(part for part in combo if part) for combo in islice(product(*options), 8)]


def _collapse(text: str) -> str:
    """Merge repeated letters ("mhmmd" -> "mhmd"); Arabic writes doubles once."""
    return "".join(ch for index, ch in enumerate(text) if index == 0 or ch != text[index - 1])
