"""Stable explanation codes attached to every verdict.

Codes never contain name fragments, so a verdict can be logged or returned to
the payer's bank without leaking the account holder's name.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Reason(StrEnum):
    """Why a verdict came out the way it did. Values are a stable public contract."""

    DIACRITICS_FOLDED = "diacritics_folded"
    LETTER_EXPANSION = "letter_expansion"
    TRANSLITERATED = "transliterated"
    APPROXIMATE_TRANSLITERATION = "approximate_transliteration"
    TITLE_REMOVED = "title_removed"
    LEGAL_FORM_MATCHED = "legal_form_matched"
    LEGAL_FORM_MISSING = "legal_form_missing"
    LEGAL_FORM_CONFLICT = "legal_form_conflict"
    PARTICLE_DROPPED = "particle_dropped"
    PARTICLE_JOINED = "particle_joined"
    PARTICLE_CONFLICT = "particle_conflict"
    COMPOUND_JOINED = "compound_joined"
    JOINT_ACCOUNT_HOLDER = "joint_account_holder"
    SHARED_SURNAME = "shared_surname"
    TOKEN_REORDER = "token_reorder"
    INITIAL = "initial"
    INITIALS_ONLY = "initials_only"
    ABBREVIATION = "abbreviation"
    FUZZY_TOKEN = "fuzzy_token"
    MISMATCHED_TOKEN = "mismatched_token"
    MISSING_TOKENS = "missing_tokens"
    MISSING_NAME_PART = "missing_name_part"
    SINGLE_TOKEN = "single_token"
    SUFFIX_CONFLICT = "suffix_conflict"
    UNSUPPORTED_SCRIPT = "unsupported_script"
    EMPTY_NAME = "empty_name"
    NAME_TOO_LONG = "name_too_long"


_ORDER = {reason: index for index, reason in enumerate(Reason)}


def ordered(reasons: Iterable[Reason]) -> tuple[Reason, ...]:
    """Return unique reasons in declaration order, so output is deterministic."""
    return tuple(sorted(set(reasons), key=_ORDER.__getitem__))
