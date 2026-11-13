"""Build arabic-dedupe-v1: a held-out duplicate-finding set of real name spellings.

Each record is one real Wikidata label (CC0) of a deceased person from an
Arabic-speaking country: the Arabic label, the English label and the French label
(French labels carry Maghreb spellings: "Hocine", "Larbi"). Records of the same
person are duplicates; nothing is generated. People who appear in nameproof-bench
are excluded, because nameproof was tuned on that benchmark.

    uv run python bench/compare/build_dedupe_set.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from nameproof.translit import scripts

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "nameproof-bench/1 (https://github.com/nadaboulaares/nameproof)"
HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
CACHE = BENCH / "cache" / "dedupe"
OUT = BENCH / "data" / "arabic-dedupe-v1.jsonl"
PER_COUNTRY = 700

COUNTRIES = {
    "tunisia": "Q948", "algeria": "Q262", "morocco": "Q1028", "libya": "Q1016",
    "egypt": "Q79", "lebanon": "Q822", "syria": "Q858", "iraq": "Q796",
    "jordan": "Q810", "saudi-arabia": "Q851",
}  # fmt: skip

QUERY = """
SELECT ?person ?ar ?en ?fr WHERE {
  ?person wdt:P31 wd:Q5 ; wdt:P27 wd:%s ; wdt:P570 ?died ;
          rdfs:label ?ar . FILTER(LANG(?ar) = "ar")
  OPTIONAL { ?person rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?person rdfs:label ?fr . FILTER(LANG(?fr) = "fr") }
} LIMIT %d
"""

_CLEAN = re.compile(r"[\d()\[\]{}/,]|\b(?:I{1,3}|IV|VI{0,3})\b")


def fetch(country: str, qid: str) -> list[dict[str, str]]:
    """Query one country, caching the raw result.

    Wikidata stops long queries after 60 seconds and may return a cut-off answer,
    so a failed query is retried with a smaller limit.
    """
    cache = CACHE / f"{country}.json"
    if cache.exists():
        cached: list[dict[str, str]] = json.loads(cache.read_text(encoding="utf-8"))
        return cached
    for limit in (PER_COUNTRY * 3, PER_COUNTRY * 2, PER_COUNTRY):
        url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': QUERY % (qid, limit)})}"
        request = urllib.request.Request(  # noqa: S310 - fixed https endpoint
            url, headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
                bindings = json.load(response)["results"]["bindings"]
        except (OSError, ValueError) as error:  # timeouts, cut-off JSON
            print(f"{country}: limit {limit} failed ({type(error).__name__}), retrying smaller")
            time.sleep(5)
            continue
        rows = [{key: value["value"] for key, value in row.items()} for row in bindings]
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        time.sleep(2)  # be polite to the public endpoint
        return rows
    msg = f"could not query {country}"
    raise RuntimeError(msg)


def usable(name: str, script: str) -> bool:
    """Keep real names of two or more words in the expected script, without numbers."""
    return (
        len(name.split()) >= 2
        and not _CLEAN.search(name)
        and scripts(name) == {script}
        and len(name) <= 60
    )


def benchmark_people() -> set[str]:
    """Wikidata ids already used in nameproof-bench (excluded here)."""
    found: set[str] = set()
    for line in (BENCH / "data" / "nameproof-bench-v1.jsonl").read_text("utf-8").splitlines():
        found.update(re.findall(r"Q\d+", json.loads(line)["source"]))
    return found


def main() -> None:
    """Build the dataset file."""
    excluded = benchmark_people()
    records: list[dict[str, str]] = []
    seen_people: set[str] = set()
    for country, qid in COUNTRIES.items():
        people: dict[str, dict[str, str]] = {}
        for row in fetch(country, qid):
            person = row["person"].rsplit("/", 1)[-1]
            if person in excluded or person in seen_people:
                continue
            labels = people.setdefault(person, {})
            for lang in ("ar", "en", "fr"):
                if lang in row:
                    labels.setdefault(lang, row[lang])
        kept = 0
        for person, labels in sorted(people.items(), key=lambda item: int(item[0][1:])):
            names = {
                lang: labels[lang]
                for lang, script in (("ar", "ARABIC"), ("en", "LATIN"), ("fr", "LATIN"))
                if lang in labels and usable(labels[lang], script)
            }
            if "ar" not in names or not {"en", "fr"} & set(names):
                continue
            if names.get("en") == names.get("fr"):
                names.pop("fr", None)
            for lang, name in names.items():
                records.append({"person": person, "lang": lang, "country": country, "name": name})
            seen_people.add(person)
            kept += 1
            if kept == PER_COUNTRY:
                break
        print(f"{country:13} {kept:4} people")
    OUT.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(f"wrote {len(records)} records of {len(seen_people)} people to {OUT}")


if __name__ == "__main__":
    main()
