"""Field formats from EPC103-24 (VOP Inter-PSP API Specifications v1.1.1)."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

from nameproof.normalize import normalize_text
from nameproof.translit import Mode, renderings, scripts

# BIC11 only: the EPC reference test cases reject 8-character BICs (RSR_043-045).
BIC_PATTERN = re.compile(r"[A-Z]{6}[A-Z0-9]{2}[A-Z0-9]{3}")
IBAN_PATTERN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}")
# ISODateTime per section 4.2.9: milliseconds without trailing zeroes, then Z or an offset.
TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}(\.[0-9]{0,2}[1-9])?(Z|[-+][0-9]{2}:[0-9]{2})"
)

# Characters every PSP must accept (section 3.1), plus the space.
SEPA_BASIC = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-?:().,'+ ")
# Section 3.1 conversions for characters that are reserved in JSON/XML.
_SEPA_REPLACEMENTS = str.maketrans({'"': ".", "&": "+", "<": ".", ">": ".", "@": ".", "_": "-"})
_LETTER_FOLDS = str.maketrans(
    {
        "ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O", "œ": "oe", "Œ": "OE",
        "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "TH",
        "\u0131": "i", "ħ": "h", "Ħ": "H",
    }
)  # fmt: skip


# ISO 20022 ExternalOrganisationIdentification1Code (external code set).
ORGANISATION_SCHEMES = frozenset(
    {"BANK", "BDID", "BOID", "CBID", "CHID", "CINC", "COID", "CUST", "DUNS", "EMPL",
     "GS1G", "SREN", "SRET", "TXID"}
)  # fmt: skip

_SEPA_PUNCTUATION = frozenset("/-?:().,'+ ")


def in_charset(text: str, charset: str) -> bool:
    """Whether ``text`` uses only the request character set (section 3.1).

    ``"sepa-basic"``: the basic set every PSP accepts. ``"latin"``: the basic set
    plus Latin letters with diacritics (*José*, *Wałęsa*), as agreed in most
    communities. ``"any"``: no restriction.
    """
    if charset == "any":
        return True
    if charset == "sepa-basic":
        return all(ch in SEPA_BASIC for ch in text)
    return all(
        ch in SEPA_BASIC
        or ch in _SEPA_PUNCTUATION
        or unicodedata.category(ch).startswith("M")
        or (ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN"))
        for ch in text
    )


def parse_timestamp(value: str) -> datetime | None:
    """Parse an EPC ISODateTime; ``None`` if it doesn't follow section 4.2.9."""
    if TIMESTAMP_PATTERN.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_timestamp(moment: datetime) -> str:
    """Format a UTC ISODateTime with milliseconds and no trailing zeroes."""
    moment = moment.astimezone(UTC)
    millis = f"{moment.microsecond // 1000:03d}".rstrip("0")
    fraction = f".{millis}" if millis else ""
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + fraction + "Z"


def to_sepa_latin(name: str) -> str | None:
    """Write ``name`` in the SEPA basic Latin character set, or ``None`` if impossible.

    Greek and Cyrillic are romanised with their official scheme (ELOT 743, ICAO
    9303...); diacritics are folded; reserved characters are converted as in
    section 3.1. Scripts without an official romanisation (Arabic, CJK, ...)
    can't be shown faithfully, so they return ``None``.
    """
    if scripts(name) - {"LATIN"}:
        official = [
            r
            for r in renderings(normalize_text(name))
            if r.mode is Mode.EXACT and r.reasons and not scripts(r.text) - {"LATIN"}
        ]
        if not official:
            return None
        romanised = official[0].text
        name = romanised.upper() if name.isupper() else romanised.title()
    decomposed = unicodedata.normalize("NFD", name.translate(_LETTER_FOLDS))
    folded = "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))
    converted = "".join(
        ch if ch in SEPA_BASIC else " " for ch in folded.translate(_SEPA_REPLACEMENTS)
    )
    result = " ".join(converted.split())
    return result[:140] or None
