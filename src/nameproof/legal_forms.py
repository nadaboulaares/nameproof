"""Company legal forms ("GmbH", "Sp. z o.o.", "Ltd", ...).

A curated subset of the abbreviations and full names in the ISO 20275 Entity
Legal Forms list (GLEIF ELF), written as normalised ASCII tokens. Forms that
are equivalent across languages share one canonical code; different codes
(e.g. GmbH vs AG) are different kinds of entity. Greek and Bulgarian forms
appear in their ELOT 743 / Bulgarian romanisation (AE, EPE, OOD, EOOD...).

The full list of SEPA-country forms comes from the GLEIF ELF code list (CC0 1.0),
compiled into ``data/legal_forms.json`` by ``tools/build_legal_forms.py``;
nameproof is not affiliated with or endorsed by GLEIF.
"""

from __future__ import annotations

import json
from importlib.resources import files

CURATED_FORMS: dict[str, tuple[str, ...]] = {
    # German-speaking
    "gmbh": ("gmbh", "gesmbh", "ges m b h", "gesellschaft mit beschrankter haftung"),
    "gmbh-co-kg": ("gmbh co kg", "gmbh und co kg"),
    "ag": ("ag", "aktiengesellschaft"),
    "kg": ("kg", "kommanditgesellschaft"),
    "ohg": ("ohg", "offene handelsgesellschaft"),
    "ug": ("ug", "ug haftungsbeschrankt", "unternehmergesellschaft"),
    "ev": ("e v", "eingetragener verein"),
    "ek": ("e k", "e kfm", "eingetragener kaufmann"),
    "se": ("se", "societas europaea"),
    # English-speaking
    "ltd": ("ltd", "limited"),
    "plc": ("plc", "public limited company"),
    "llp": ("llp", "limited liability partnership"),
    "llc": ("llc", "limited liability company"),
    "inc": ("inc", "incorporated"),
    "corp": ("corp", "corporation"),
    # French, Spanish, Portuguese, Italian, Romanian, Polish (S.A.)
    # Greek A.E. (anonymi etaireia) is the same kind of company as S.A.
    "sa": (
        "s a",
        "societe anonyme",
        "sociedad anonima",
        "spolka akcyjna",
        "societate pe actiuni",
        "a e",
        "anonymi etaireia",
    ),
    "sas": ("s a s", "societe par actions simplifiee"),
    "sasu": ("sasu",),
    "sarl": ("s a r l", "societe a responsabilite limitee"),
    "eurl": ("eurl",),
    "snc": ("s n c",),
    "spa": ("s p a", "societa per azioni"),
    "srl": ("s r l", "societa a responsabilita limitata", "societate cu raspundere limitata"),
    "srls": ("srls",),
    "sapa": ("s a p a",),
    "sl": ("s l", "sociedad limitada", "sociedad de responsabilidad limitada"),
    "slu": ("s l u",),
    "lda": ("lda", "limitada"),
    "pfa": ("pfa",),
    # Benelux
    "bv": ("b v", "besloten vennootschap"),
    "nv": ("n v", "naamloze vennootschap"),
    "vof": ("v o f", "vennootschap onder firma"),
    # Central / Eastern Europe
    "sp-zoo": ("sp z o o", "spzoo", "sp zoo", "spolka z ograniczona odpowiedzialnoscia"),
    "sp-j": ("sp j", "spolka jawna"),
    "sp-k": ("sp k", "spolka komandytowa"),
    "sro": ("s r o", "spol s r o", "spolecnost s rucenim omezenym"),
    "as": ("a s", "akciova spolecnost", "aktieselskab", "aksjeselskap", "aktsiaselts"),
    "vos": ("v o s",),
    "kft": ("kft", "korlatolt felelossegu tarsasag"),
    "zrt": ("zrt",),
    "nyrt": ("nyrt",),
    "bt": ("bt",),
    "kkt": ("kkt",),
    "doo": ("d o o",),
    "dd": ("d d",),
    # Nordics and Baltics
    "ab": ("ab", "aktiebolag"),
    "hb": ("hb", "handelsbolag"),
    "kb": ("kb", "kommanditbolag"),
    "aps": ("aps", "anpartsselskab"),
    "ivs": ("ivs",),
    "oy": ("oy", "osakeyhtio"),
    "oyj": ("oyj",),
    "sia": ("sia",),
    "uab": ("uab",),
    # Greece and Bulgaria (romanised)
    "gbr": ("gbr", "gesellschaft burgerlichen rechts"),
    "asa": ("asa", "allmennaksjeselskap"),
    "ehf": ("ehf", "einkahlutafelag"),
    "vzw": ("vzw", "vereniging zonder winstoogmerk"),
    "epe": ("e p e",),
    "ike": ("i k e",),
    "ood": ("ood",),
    "eood": ("eood",),
    "ead": ("ead",),
}


def _spellings(spelling: str) -> list[tuple[str, ...]]:
    tokens = tuple(spelling.split())
    if len(tokens) > 1 and all(len(token) == 1 for token in tokens):
        return [tokens, ("".join(tokens),)]  # "s a" is also written "sa"
    return [tokens]


def _load_elf() -> dict[str, list[str]]:
    resource = files("nameproof") / "data" / "legal_forms.json"
    if not resource.is_file():  # pragma: no cover - the file ships with the package
        return {}
    forms: dict[str, list[str]] = json.loads(resource.read_text(encoding="utf-8"))["forms"]
    return forms


def _index() -> dict[tuple[str, ...], frozenset[str]]:
    codes: dict[tuple[str, ...], set[str]] = {}
    for code, spellings in _load_elf().items():
        for spelling in spellings:
            for tokens in _spellings(spelling):
                codes.setdefault(tokens, set()).add(f"elf:{code}")
    # Curated forms were checked by hand against name collisions; they also merge
    # the ELF codes they share a spelling with, so "Ltd" == "Limited" everywhere.
    for code, curated in CURATED_FORMS.items():
        keys = [tokens for spelling in curated for tokens in _spellings(spelling)]
        group = {f"curated:{code}"}.union(*(codes.get(tokens, set()) for tokens in keys))
        for tokens in keys:
            codes[tokens] = codes.get(tokens, set()) | group
    return {tokens: frozenset(found) for tokens, found in codes.items()}


_INDEX = _index()
_LONGEST = max(len(tokens) for tokens in _INDEX)

#: Words that only ever stand for a legal form ("gmbh", "ltd", "gesellschaft", ...):
#: one-word forms, plus the words of the hand-checked multi-word forms. Words
#: inside long ELF names are left out, because some are also surnames.
LEGAL_FORM_WORDS: frozenset[str] = frozenset(
    {tokens[0] for tokens in _INDEX if len(tokens) == 1 and len(tokens[0]) > 1}
    | {
        token
        for spellings in CURATED_FORMS.values()
        for spelling in spellings
        for token in spelling.split()
        if len(token) > 2
    }
)

LegalForm = frozenset[str]
"""The legal forms a trailing phrase may stand for (ELF and curated codes)."""


def same_legal_form(left: LegalForm, right: LegalForm) -> bool:
    """Whether two detected legal forms can be the same kind of entity."""
    return not left.isdisjoint(right)


def split_legal_form(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], LegalForm | None]:
    """Detach a trailing legal form and return the remaining name with its codes.

    The longest known form wins; a name is never reduced to nothing.
    """
    for size in range(min(_LONGEST, len(tokens) - 1), 0, -1):
        code = _INDEX.get(tokens[-size:])
        if code is not None:
            return tokens[:-size], code
    return tokens, None
