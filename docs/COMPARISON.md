# Finding duplicates: nameproof vs fuzzy matching vs Splink

**Question:** given a list of names in which the same person appears in Arabic script and in
Latin letters (English or French spellings), which tool groups the records of each person?

## The data: arabic-dedupe-v1

[`bench/data/arabic-dedupe-v1.jsonl`](../bench/data/arabic-dedupe-v1.jsonl): **13,417
names of 6,235 people**, 8,129 true duplicate pairs. Every record is a real Wikidata label
(CC0) of a deceased person from Tunisia, Algeria, Morocco, Libya, Egypt, Lebanon, Syria,
Iraq, Jordan or Saudi Arabia: the Arabic label, the English label and, when it differs,
the French label. Nothing is generated, for example:

| Arabic | English | French |
|---|---|---|
| ليلى بعلبكي | Layla Balabakki | Leïla Baalbaki |
| محمد بن عزيزة | Mohammed Benaziza | Mohamed Benaziza |
| لؤي الأتاسي | Luai al-Atassi | Louai al-Atassi |

People who appear in [nameproof-bench](BENCHMARK.md) are excluded, because nameproof
was tuned on that benchmark: this set is held out. Build it with
`uv run python bench/compare/build_dedupe_set.py`.

## The rules of the comparison

- Every system gets the same 13,417 names and must put the records of one person in one
  group. Every pair of records in one group is a predicted duplicate; **precision** is
  the share of predicted pairs that are right, **recall** the share of true pairs found.
- nameproof runs **with its defaults** (`nameproof dedupe`, policy `records@1`).
- The baselines get every advantage nameproof doesn't: Arabic is transliterated to Latin
  letters first (anyascii), since they can't compare scripts, and their **threshold and
  grouping method are tuned on the answers** (the best F1 they can reach).

## Results

| system | precision | recall | **F1** | Arabic ↔ Latin found | Latin ↔ Latin found | time |
|---|---|---|---|---|---|---|
| **nameproof** (defaults, `records@1`) | **76.5%** | **79.5%** | **78.0%** | **79.3%** | **80.8%** | 75 s (8 cores) |
| fuzzy matching (token-sort, threshold 80, tuned) | 16.9% | 8.3% | 11.2% | 1.1% | 63.5% | 270 s |
| Splink 5.0 (name comparisons, threshold 0.5, tuned) | 27.6% | 5.2% | 8.8% | 0.0% | 44.8% | 9 s |

nameproof also reports which of its groups are certain: groups linked only by full matches
(`MATCH`, no review needed) are 68.8% precise and hold 3.8% of the duplicates; everything
else is a group to review.

Splink was trained without labels, as in real use (u values by random sampling, m values
by expectation maximisation on three blocking rules), on the full name and its first and
last word. It is built for records with several fields (date of birth, address); on
names alone, and with Arabic reduced to consonant strings by transliteration, it has
little to work with. This comparison is about names, not about Splink in general.

**How dedupe groups names.** This comparison found that joining every chain of links
(A~B, B~C, C~D...) put 4,750 different people into one group (precision 0.1%). Since
0.3.1 groups use complete linkage: every two names in a group are linked. The baselines
were given whichever grouping scored better for them.

## What this shows, and what it doesn't

- **Arabic ↔ Latin is where nameproof is different.** Transliterating Arabic letter by
  letter gives consonant strings (*محمد* → "mhmd") that no fuzzy score links to
  *Mohamed*; nameproof compares consonant skeletons with Maghreb and French readings and
  knows common given names.
- **Names alone can't separate namesakes.** In this set, only 45% of identical names
  belong to the same person: Wikidata has many people called *محمد العماري*. No
  name-only tool can tell them apart; for real records, confirm with a date of birth,
  phone or ID number. That limits every system's precision here.
- **Full matches are rare by design.** `records@1` gives a full match only for the same
  script and a known spelling; Arabic against Latin is always a close match to review.
- This is one data set, built from public figures. Real registration lists have other
  errors (typos, swapped first and family names, missing grandfather's names), and we'd
  welcome an anonymised evaluation on one.

Reproduce:

```bash
uv venv /tmp/cmp && VIRTUAL_ENV=/tmp/cmp uv pip install splink anyascii rapidfuzz pandas -e .
/tmp/cmp/bin/python bench/compare/compare_dedupe.py
```
