# nameproof-bench

A public benchmark for **payee name matching across scripts**: does a matcher accept
the same person written differently, and reject different people?

- `data/nameproof-bench-v1.jsonl`: 6,000 labelled pairs, 15 slices
- `build_dataset.py`: rebuilds the file from Wikidata (deterministic, seeded)
- Results: [docs/BENCHMARK.md](../docs/BENCHMARK.md)

```bash
uv run nameproof bench bench/data/nameproof-bench-v1.jsonl          # Markdown tables
uv run nameproof bench bench/data/nameproof-bench-v1.jsonl --json   # rates as JSON
uv run python bench/build_dataset.py [--refresh]                     # rebuild the data
```

## Format

One JSON object per line:

```json
{"id": "greek-0001", "slice": "greek", "variation": "native_script", "label": "same",
 "provided": "Giorgos Rallis", "account": "Γεώργιος Ράλλης", "source": "wikidata:Q252657"}
```

`provided` is what a payer types; `account` is the name the bank holds. `label` is
`same` (same person or company) or `different`.

## Slices

| Slice | Account names in | Source |
|---|---|---|
| greek | Greek | people with Greek or Cypriot citizenship |
| russian, ukrainian, bulgarian, serbian | Cyrillic | people of those countries (Russia incl. USSR, Serbia incl. Yugoslavia) |
| arabic | Arabic | people from Egypt, Morocco, Algeria, Tunisia, Iraq, Syria, Lebanon, Jordan, Saudi Arabia |
| polish, czech, hungarian, romanian, german, french, spanish | Latin with diacritics | people of those countries |
| greek-company, cyrillic-company | Greek / Cyrillic | companies in Greece/Cyprus; Russia/Ukraine/Bulgaria |

## Variations

**Same** (`label: same`). The account holds the native-language name; the payer types:

| Variation | Payer types | Ideal verdict |
|---|---|---|
| `native_script` | the English (Latin) name | MATCH if it is a standard romanisation, else CLOSE |
| `english_label` | the English name of a Latin-script person, where it differs | MATCH or CLOSE |
| `ascii_typed` | the name without diacritics (*Lech Walesa*) | MATCH |
| `uppercase` | the name in capitals | MATCH |
| `reordered` | surname first | MATCH |
| `dropped_middle` | the name without a middle name | MATCH |
| `typo` | one wrong letter (never the first) | CLOSE |
| `initial` | the first name as an initial (*M. Callas*) | CLOSE |

**Different** (`label: different`): `same_surname` pairs two different people who share
a surname (the hard case); `different_person` pairs two unrelated people.

## How it was built

1. One SPARQL query per slice against the public Wikidata endpoint: entities with an
   English label and a label in the slice's language.
2. **People are deceased only** (Wikidata P570 set), born 1880 or later and with at least
   8 Wikipedia sitelinks, so **no living person's name is in the dataset**.
3. Labels are filtered to plausible names: right scripts, 2–4 words (people), and no
   titles, regnal numbers, parentheses or descriptions (*George I of Greece*,
   *Elder Paisios*).
4. Variations and negative pairs are generated with a fixed seed; rebuilding from the
   cached query results produces a byte-identical file.

Labels are not corrected by hand. Some "same" pairs are exonyms, stage names or
translated company names that no spelling-based matcher can link. They are kept,
because removing them would flatter whichever matcher the filter was tuned on.

## Licence

Names come from Wikidata and are available under **CC0 1.0**. The generated pairs in
`data/` are released under CC0 1.0 as well. The builder code is Apache-2.0, like the
rest of the repository.
