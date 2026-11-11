r"""Build src/nameproof/data/legal_forms.json from the GLEIF ELF code list.

    curl -L -o bench/cache/elf-v1.6.csv \\
      https://www.gleif.org/lei-data/code-lists/iso-20275-entity-legal-forms-code-list/2026-02-19-elf-code-list-v1.6.csv
    uv run python tools/build_legal_forms.py bench/cache/elf-v1.6.csv

The ELF code list (ISO 20275) is maintained by GLEIF and published under CC0 1.0
(GLEIF LEI Data Terms of Use). nameproof is not affiliated with or endorsed by GLEIF.

Every legal form of a SEPA country becomes a set of normalised spellings (local
name, transliterated name, abbreviations), keyed by its ELF code. A spelling used
by several forms ("S.A." in France, Spain and Poland) maps to all of them, and two
names have the same legal form when their candidate forms overlap. One-token
abbreviations of up to three letters are dropped unless nameproof's curated list
already has them, because many are also names ("Per", "Son", "Ong").
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from nameproof.legal_forms import CURATED_FORMS
from nameproof.normalize import fold_variants, normalize_text
from nameproof.translit import Mode, renderings, scripts

OUT = Path(__file__).resolve().parent.parent / "src" / "nameproof" / "data" / "legal_forms.json"

# SEPA scheme countries (EU, EEA, CH, GB, and other SEPA participants).
SEPA = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
        "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS",
        "LI", "NO", "CH", "GB", "MC", "SM", "VA", "AD", "AL", "MD", "ME", "MK", "RS", "GI",
        "JE", "GG", "IM",
    }
)  # fmt: skip
_DROP_TOKENS = frozenset({"&", "+"})
# One-word ELF entries that are also surnames or generic words, not legal forms.
_NOT_FORMS = frozenset(
    {"lipa", "kraj", "obec", "bund", "ente", "fond", "fondo", "fonds", "fondy", "fund",
     "fundo", "kunta", "sklad", "trust", "ustav", "coop", "mutua", "orgen", "prst"}
)  # fmt: skip


def spellings(text: str) -> set[str]:
    """Normalised ASCII spellings of one legal-form name or abbreviation."""
    results: set[str] = set()
    for rendering in renderings(normalize_text(text)):
        if rendering.mode is not Mode.EXACT:
            continue
        for folded, _ in fold_variants(rendering.text):
            for hyphen in (" ", ""):
                tokens = [t for t in folded.replace("-", hyphen).split() if t not in _DROP_TOKENS]
                spelling = " ".join(tokens)
                if spelling and not scripts(spelling) - {"LATIN"} and spelling.isascii():
                    results.add(spelling)
    return results


def _keep(spelling: str, curated: set[str]) -> bool:
    tokens = spelling.split()
    if spelling in curated:
        return True
    if spelling in _NOT_FORMS:
        return False
    if len(tokens) == 1 and len(tokens[0]) <= 3:
        # "per", "son", "ong", "teo" are also first names or surnames; short forms
        # that matter (Ltd, Inc, SRL, Kft...) are in the curated list.
        return False
    return not any(token.isdigit() for token in tokens)


def build(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """Map each ELF code to its spellings (forms stay separate; overlap is resolved later)."""
    curated = {spelling for forms in CURATED_FORMS.values() for spelling in forms}
    out: dict[str, set[str]] = {}
    for row in rows:
        if row["Country Code (ISO 3166-1)"] not in SEPA:
            continue
        names = [
            row["Entity Legal Form name Local name"],
            row["Entity Legal Form name Transliterated name (per ISO 01-140-10)"],
            *row["Abbreviations Local language"].split(";"),
            *row["Abbreviations transliterated"].split(";"),
        ]
        found = {s for name in names if name.strip() for s in spellings(name)}
        found = {s for s in found if _keep(s, curated)}
        if found:
            out.setdefault(row["ELF Code"], set()).update(found)
    return {code: sorted(found) for code, found in sorted(out.items())}


def main() -> int:
    """Read the ELF CSV given on the command line and write the JSON data file."""
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    forms = build(rows)
    payload = {
        "source": "GLEIF ISO 20275 Entity Legal Forms code list v1.6 (CC0 1.0), SEPA countries",
        "forms": forms,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = len({spelling for spellings in forms.values() for spelling in spellings})
    print(f"wrote {OUT}: {len(forms)} legal forms, {total} distinct spellings, {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
