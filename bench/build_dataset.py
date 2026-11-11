"""Build the nameproof benchmark from Wikidata (CC0) plus seeded variations.

    uv run python bench/build_dataset.py            # uses bench/cache/ when present
    uv run python bench/build_dataset.py --refresh  # re-query Wikidata

Privacy: only deceased people (Wikidata P570 set) are used, so no living
person's name enters the dataset. Companies are organisations, not people.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from nameproof.translit import scripts

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "nameproof-bench/1 (https://github.com/nadaboulaares/nameproof)"
HERE = Path(__file__).parent
CACHE = HERE / "cache"
DEFAULT_OUT = HERE / "data" / "nameproof-bench-v1.jsonl"
SEED = 20261110

POSITIVES_PER_SLICE = 250
NEGATIVES_PER_SLICE = 150


@dataclass(frozen=True, slots=True)
class Source:
    """One benchmark slice: people (or companies) from some countries."""

    slice: str
    lang: str
    countries: tuple[str, ...]
    script: str
    kind: str = "person"


SOURCES = [
    Source("greek", "el", ("Q41", "Q229"), "GREEK"),
    Source("russian", "ru", ("Q159", "Q15180"), "CYRILLIC"),
    Source("ukrainian", "uk", ("Q212",), "CYRILLIC"),
    Source("bulgarian", "bg", ("Q219",), "CYRILLIC"),
    Source("serbian", "sr", ("Q403", "Q83286"), "CYRILLIC"),
    Source(
        "arabic",
        "ar",
        ("Q79", "Q1028", "Q262", "Q948", "Q796", "Q858", "Q822", "Q810", "Q851"),
        "ARABIC",
    ),
    Source("polish", "pl", ("Q36",), "LATIN"),
    Source("czech", "cs", ("Q213",), "LATIN"),
    Source("hungarian", "hu", ("Q28",), "LATIN"),
    Source("romanian", "ro", ("Q218",), "LATIN"),
    Source("german", "de", ("Q183",), "LATIN"),
    Source("french", "fr", ("Q142",), "LATIN"),
    Source("spanish", "es", ("Q29",), "LATIN"),
    Source("greek-company", "el", ("Q41", "Q229"), "GREEK", kind="company"),
    Source("cyrillic-company", "ru", ("Q159", "Q212", "Q219"), "CYRILLIC", kind="company"),
]

_PERSON_QUERY = """
SELECT ?item ?en ?native WHERE {{
  VALUES ?country {{ {countries} }}
  ?item wdt:P27 ?country; wdt:P31 wd:Q5; wdt:P570 ?died; wdt:P569 ?born;
        wikibase:sitelinks ?links .
  FILTER(?links >= 8 && YEAR(?born) >= 1880)
  ?item rdfs:label ?en . FILTER(LANG(?en) = "en")
  ?item rdfs:label ?native . FILTER(LANG(?native) = "{lang}")
}} LIMIT 900
"""

_COMPANY_QUERY = """
SELECT ?item ?en ?native WHERE {{
  VALUES ?country {{ {countries} }}
  VALUES ?type {{ wd:Q4830453 wd:Q891723 wd:Q6881511 }}
  ?item wdt:P17 ?country; wdt:P31 ?type .
  ?item rdfs:label ?en . FILTER(LANG(?en) = "en")
  ?item rdfs:label ?native . FILTER(LANG(?native) = "{lang}")
}} LIMIT 900
"""

# English labels that are descriptions or styles rather than names.
_NOT_A_NAME = frozenset(
    {
        "of", "the", "saint", "st", "pope", "king", "queen", "prince", "princess",
        "emperor", "empress", "sultan", "sheikh", "elder", "father", "patriarch",
        "archbishop", "bishop", "metropolitan", "tsar", "grand", "duke", "count",
    }
)  # fmt: skip
_BAD_CHARACTERS = frozenset('()[],;:/\\"0123456789\u0374\u0384')  # incl. Greek numeral signs


@dataclass(frozen=True, slots=True)
class Entity:
    """A Wikidata item with its English and native-language labels."""

    qid: str
    en: str
    native: str


# --- fetching ----------------------------------------------------------------


def _query(source: Source) -> str:
    template = _COMPANY_QUERY if source.kind == "company" else _PERSON_QUERY
    countries = " ".join(f"wd:{qid}" for qid in source.countries)
    return template.format(countries=countries, lang=source.lang)


def fetch(source: Source, *, refresh: bool) -> list[dict[str, str]]:
    """Return raw rows for ``source``, from the cache unless ``refresh``."""
    cached = CACHE / f"{source.slice}.json"
    if cached.exists() and not refresh:
        rows: list[dict[str, str]] = json.loads(cached.read_text(encoding="utf-8"))
        return rows
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': _query(source)})}"
    request = urllib.request.Request(  # noqa: S310 - fixed https endpoint
        url, headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        payload = json.load(response)
    rows = [
        {
            "qid": binding["item"]["value"].rsplit("/", 1)[1],
            "en": binding["en"]["value"],
            "native": binding["native"]["value"],
        }
        for binding in payload["results"]["bindings"]
    ]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    time.sleep(2)  # be polite to the public endpoint
    return rows


# --- filtering ---------------------------------------------------------------


def is_clean_name(en: str, native: str, script: str, *, kind: str = "person") -> bool:
    """Keep labels that look like real names in the expected scripts."""
    if any(ch in _BAD_CHARACTERS for ch in en + native):
        return False
    en_tokens, native_tokens = en.split(), native.split()
    if kind == "person" and not (2 <= len(en_tokens) <= 4 and 2 <= len(native_tokens) <= 5):
        return False
    if not en_tokens or not native_tokens or len(en_tokens) > 6:
        return False
    if any(token.casefold().strip(".") in _NOT_A_NAME for token in en_tokens):
        return False
    return scripts(en) == {"LATIN"} and scripts(native) == {script}


def entities(rows: Iterable[dict[str, str]], source: Source) -> list[Entity]:
    """Deduplicate, filter and sort rows into entities (stable order)."""
    seen: dict[str, Entity] = {}
    for row in rows:
        if row["qid"] in seen:
            continue
        if is_clean_name(row["en"], row["native"], source.script, kind=source.kind):
            seen[row["qid"]] = Entity(row["qid"], row["en"], row["native"])
    return sorted(seen.values(), key=lambda entity: int(entity.qid[1:]))


# --- variations --------------------------------------------------------------


def strip_diacritics(text: str) -> str:
    """Write a Latin name the way it is typed on an ASCII keyboard."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))


def typo(text: str, rng: random.Random) -> str | None:
    """Replace one interior letter of the longest word (never the first letter)."""
    words = text.split()
    index = max(range(len(words)), key=lambda i: len(words[i]))
    word = words[index]
    if len(word) < 5:
        return None
    position = rng.randrange(1, len(word) - 1)
    letter = rng.choice([ch for ch in "abcdefghijklmnopqrstuvwxyz" if ch != word[position]])
    words[index] = word[:position] + letter + word[position + 1 :]
    return " ".join(words)


def initial(text: str) -> str | None:
    """Abbreviate the first given name: "Maria Callas" -> "M. Callas"."""
    words = text.split()
    if len(words) < 2:
        return None
    return " ".join([f"{words[0][0]}.", *words[1:]])


def reordered(text: str) -> str | None:
    """Surname first: "Maria Callas" -> "Callas Maria"."""
    words = text.split()
    return " ".join([words[-1], *words[:-1]]) if len(words) >= 2 else None


def dropped_middle(text: str) -> str | None:
    """Drop a middle name: "Anna Maria Kowalska" -> "Anna Kowalska"."""
    words = text.split()
    return " ".join([words[0], words[-1]]) if len(words) >= 3 else None


def _positive_variants(
    entity: Entity, source: Source, rng: random.Random
) -> Iterator[tuple[str, str, str]]:
    """Yield (variation, provided, account) for the same person or company."""
    account = entity.native
    if source.script == "LATIN":
        base = entity.native
        if entity.en != entity.native:
            yield "english_label", entity.en, account
        if strip_diacritics(base) != base:
            yield "ascii_typed", strip_diacritics(base), account
    else:
        base = entity.en
        yield "native_script", entity.en, account
    generated = {
        "uppercase": base.upper(),
        "reordered": reordered(base),
        "typo": typo(base, rng),
        "initial": initial(base) if source.kind == "person" else None,
        "dropped_middle": dropped_middle(base) if source.kind == "person" else None,
    }
    for variation, provided in generated.items():
        if provided and provided != account:
            yield variation, provided, account


def _surname(entity: Entity) -> str:
    return strip_diacritics(entity.en.split()[-1]).casefold()


def _negatives(pool: list[Entity], rng: random.Random) -> Iterator[tuple[str, Entity, Entity]]:
    """Yield (variation, provided entity, account entity) for different people."""
    by_surname: dict[str, list[Entity]] = defaultdict(list)
    for entity in pool:
        by_surname[_surname(entity)].append(entity)
    shared = [group for group in by_surname.values() if len(group) > 1]
    rng.shuffle(shared)
    for group in shared:
        first, second = rng.sample(group, 2)
        if first.en.split()[0].casefold() != second.en.split()[0].casefold():
            yield "same_surname", first, second
    while True:
        first, second = rng.sample(pool, 2)
        if _surname(first) != _surname(second):
            yield "different_person", first, second


def build_slice(source: Source, pool: list[Entity]) -> list[dict[str, str]]:
    """Return labelled pairs for one slice, deterministic for a given pool."""
    rng = random.Random(f"{SEED}:{source.slice}")
    positives = [
        {"variation": variation, "label": "same", "provided": provided, "account": account,
         "source": f"wikidata:{entity.qid}"}
        for entity in pool
        for variation, provided, account in _positive_variants(entity, source, rng)
    ]  # fmt: skip
    rng.shuffle(positives)
    cases = positives[:POSITIVES_PER_SLICE]
    if len(pool) >= 2:
        negatives = _negatives(pool, rng)
        same_surname_cap = NEGATIVES_PER_SLICE // 2
        taken = 0
        for variation, first, second in negatives:
            if taken >= NEGATIVES_PER_SLICE:
                break
            if variation == "same_surname" and taken >= same_surname_cap:
                continue
            cases.append(
                {"variation": variation, "label": "different", "provided": first.en,
                 "account": second.native, "source": f"wikidata:{first.qid}|{second.qid}"}
            )  # fmt: skip
            taken += 1
    for index, case in enumerate(cases):
        case["id"] = f"{source.slice}-{index:04d}"
        case["slice"] = source.slice
    return cases


def main() -> None:
    """Build the benchmark file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-query Wikidata")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    lines: list[str] = []
    for source in SOURCES:
        pool = entities(fetch(source, refresh=args.refresh), source)
        cases = build_slice(source, pool)
        print(f"{source.slice:18} {len(pool):4} entities -> {len(cases):4} pairs")
        keys = ("id", "slice", "variation", "label", "provided", "account", "source")
        lines.extend(
            json.dumps({key: case[key] for key in keys}, ensure_ascii=False) for case in cases
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} pairs to {args.out}")


if __name__ == "__main__":
    main()
