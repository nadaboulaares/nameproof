"""Text normalisation: Unicode cleanup, casefolding and diacritic folding."""

from __future__ import annotations

import unicodedata

from nameproof.explain import Reason

# ' plus look-alikes people type or paste: left/right quotes, modifier apostrophe, `, acute.
_APOSTROPHES = frozenset("'\u2018\u2019\u02bc`\u00b4")
_KEPT_SYMBOLS = frozenset("&+")
_HYPHENS = frozenset("-\u2010")

# Letters that do not decompose under NFD but have a conventional plain form
# (U+0131 is the Turkish dotless i).
_SPECIAL_FOLDS = str.maketrans(
    {
        "æ": "ae", "ø": "o", "œ": "oe", "ł": "l", "đ": "d",
        "ð": "d", "þ": "th", "ħ": "h", "\u0131": "i",
    }
)  # fmt: skip

# Spellings that replace a letter with two: German/Nordic ("Müller" -> "Mueller")
# and South Slavic ("Đoković" -> "Djokovic").
_EXPANSIONS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "å": "aa", "ø": "oe", "æ": "ae", "đ": "dj"}
)


def normalize_text(text: str) -> str:
    """Casefold ``text`` and reduce punctuation to single spaces.

    Apostrophes are removed so "O'Brien" and "OBrien" agree; "&" and "+" are kept
    as separate tokens because they mark joint accounts; a hyphen inside a word is
    kept ("hans-joachim") because a compound name is one name. Idempotent.
    """
    text = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    chars: list[str] = []
    for index, ch in enumerate(text):
        if ch in _APOSTROPHES:
            continue
        if ch in _KEPT_SYMBOLS:
            chars.append(f" {ch} ")
        elif _is_word(ch):
            chars.append(ch)
        elif (
            ch in _HYPHENS
            and chars
            and _is_word(chars[-1][-1])
            and index + 1 < len(text)
            and _is_word(text[index + 1])
        ):
            chars.append("-")
        else:
            chars.append(" ")
    return " ".join("".join(chars).split())


def _is_word(ch: str) -> bool:
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.translate(_SPECIAL_FOLDS))
    stripped = "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))
    return unicodedata.normalize("NFC", stripped)


def fold_variants(text: str) -> tuple[tuple[str, tuple[Reason, ...]], ...]:
    """Return the plain spellings of normalised ``text`` and the reasons behind each.

    Always yields the diacritic-free form; adds the expanded German/Nordic form
    ("ü" -> "ue", "đ" -> "dj") when it differs.
    """
    plain = _strip_marks(text)
    variants: dict[str, tuple[Reason, ...]] = {
        plain: () if plain == text else (Reason.DIACRITICS_FOLDED,)
    }
    expanded = _strip_marks(text.translate(_EXPANSIONS))
    variants.setdefault(expanded, (Reason.LETTER_EXPANSION,))
    return tuple(variants.items())
