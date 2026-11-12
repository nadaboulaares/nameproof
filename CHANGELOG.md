# Changelog

All notable changes to nameproof are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Policies are versioned separately
(`epc-default@1`): a policy change never alters an existing policy id.

## [Unreleased]

### Fixed
- Duplicate groups no longer chain: a group now holds names that are all linked to each
  other (complete linkage, strongest links first). Joining every chain of close matches
  put 4,750 different people into one group on a held-out set (precision 0.1%); now 76.5%
  precision at 79.5% recall. Only links inside a group are listed with it.

### Benchmark
- `arabic-dedupe-v1`: 13,417 real Arabic, English and French Wikidata spellings of 6,235
  people from ten Arab countries, held out from nameproof-bench
  (`bench/compare/build_dedupe_set.py`).
- `bench/compare/compare_dedupe.py` and `docs/COMPARISON.md`: nameproof F1 78.0% vs fuzzy
  matching 11.2% and Splink 8.8% (baselines tuned on the answers); Arabic ↔ Latin
  duplicates found 79.3% vs 1.1% and 0.0%.

## [0.3.0] - 2026-11-12

### Arabic names
- A hand-written list of about 170 common Arabic given names and their usual Latin
  spellings (`nameproof.arabic_names`, `data/arabic_given_names.tsv`). Known spellings of
  one name are a `known_variant` (*Hussein* = *Hocine*, *Abdelkader* = *Abdul Qadir*);
  known names that don't correspond are `different_given_name`, no match, even when they
  share a consonant skeleton (*Mahmoud* vs *محمد*, *محمد* vs *محمود*) or a prefix (*Samir*
  vs *Samira*). It only applies when both names are on the list.
- Maghreb and French romanisations of Arabic script: soft c (*Hocine* = حسين), the article
  glued on (*Larbi* = العربي, *Elnadi* = النادي), a dropped first vowel (*Brahim* =
  إبراهيم, *M'hamed* = امحمد), g for qaf (*Belgacem* = بلقاسم, *Guettaf* = قطاف), and a
  final h that is a real consonant (*Salah* = صلاح; it was no match before).
- New policy `records@1` for lists of people: `lenient@2` plus known spellings of one name
  as a match. It is the default for `nameproof dedupe` and `find_duplicates`.
- Benchmark: Arabic same-person pairs wrongly rejected 12.8% (was 16.8%); all scripts
  9.4% (was 9.7%); different people shown the other's name 0.8% (was 0.9%). Verdicts for
  `epc-default@2` change accordingly: policies pin thresholds and switches, the package
  version pins the matching rules.

### Playground
- Find duplicates in the browser (`dedupe.html`): paste names or open a CSV or text file,
  see the groups with a reason for every link, download them as a CSV that Excel opens
  with Arabic, Greek and Cyrillic intact. Runs in a background worker with a progress
  bar; the list never leaves the computer (3,000 names take about 20 seconds).
- The name column is guessed from titles such as "Full name", "Nom" or "الاسم".

### Changed
- `find_duplicates(..., progress=callback)` reports `(done, total)` comparisons.

## [0.2.0] - 2026-11-12

nameproof is now positioned as general explainable name matching across scripts (charities
and aid organisations, health records, HR, travel, payments); Verification of Payee is one
use case.

### Duplicate finding
- `nameproof dedupe FILE` (CSV with a header row, or one name per line) and
  `nameproof.dedupe.find_duplicates(names)`: groups of likely duplicates across scripts
  and spellings, each link with its verdict and reason codes; a group needs review when a
  link is a close match. `--output` writes the duplicate rows with `group` and `review`
  columns; `--json` prints the full report.
- Names are only compared when they share a coarse cross-script consonant key, so a list
  of 10,000 names takes seconds to minutes instead of 50 million comparisons; on the
  benchmark's 9,624 names it keeps 98% of the same-person pairs `match` finds. `--jobs`
  compares in parallel.

### Matching
- New default policy `epc-default@2` (and `lenient@2`): in a person's name, a clearly
  different word (similarity below 0.65, `distinct_word_threshold`) rules out a close
  match, however many other words agree. *Mohamed Ben Ali* vs *Mahmoud Ben Ali* and
  *Béla Bartók* vs *Eva Bartok* were close matches and revealed a relative's name; they are
  now no match. Company names are unaffected. `epc-default@1` and `lenient@1` are
  unchanged.
- Benchmark: same entity wrongly rejected 9.7% (was 9.5%); different people shown the other
  name 0.9% (was 1.2%), a new table in `docs/BENCHMARK.md`.

### Playground
- Shareable example links: `#p=<provided name>&a=<account names>` pre-fills the page.
  The part after `#` never leaves the browser.
- Clearer explanation for `missing_name_part`; demo GIF in the README.

### Docs
- `docs/FOR-BANKS.md`: a one-page overview for banks and payment institutions.

## [0.1.0] - 2026-11-11

First public release.

### Matching
- `match(provided, account_names, policy=...)` returns an explainable `Verdict`:
  `MATCH`, `CLOSE_MATCH`, `NO_MATCH` or `NOT_POSSIBLE`, with name-free reason codes.
- Default policy `epc-default@1` follows the EPC Recommendations for the Matching
  Processes under the VOP Scheme Rulebook (EPC288-23 v2.0, November 2026); `lenient@1`
  also accepts dropped particles, legal-form variants and reordered company names.
- Latin script: case, punctuation, diacritics (*José*, *Wałęsa*), letter expansions
  (*Müller* = *Mueller*, *Søren* = *Soeren*, *Đoković* = *Djokovic*), titles,
  generational suffixes, surname particles, compound and hyphenated names, word
  order, joint accounts, middle names and trailing female patronymics.
- Greek (ELOT 743), Cyrillic (ICAO 9303, BGN/PCGN, English-media convention,
  Bulgarian 2009, Ukrainian 2010, Serbian Latin) and Arabic (consonant skeleton).
  Official romanisations can `MATCH`; informal ones and Arabic give at most
  `CLOSE_MATCH`.
- About 1,400 company legal forms from the GLEIF ISO 20275 ELF list (CC0), plus a
  hand-checked list; forms are compared by overlap (S.A. in France = S.A. in Poland =
  Greek A.E.; GmbH ≠ AG).
- Safety: the checks look at the name before titles, legal forms, particles or other
  joint holders are stripped; a close match needs a real name word, so a surname alone
  or a generic word never reveals the account name; names are capped at 140 characters
  and 10 words after Unicode normalisation, with bounded work per name.
- Runs without compiled dependencies (pure-Python fallback when rapidfuzz isn't
  installed), so it works in the browser.

### Benchmark
- nameproof-bench v1: 6,000 labelled pairs from Wikidata (CC0, deceased people only)
  in 15 slices, plus `nameproof bench`. Same person wrongly rejected 9.5% (token-sort
  baseline 63.8%), auto-matched 41.7% (26.2%), different people falsely matched 0.0%.

### Service
- `nameproof[service]`: EPC Verification of Payee responder (EPC103-24 v1.1.1),
  tested against the EPC139-25 v1.2 reference test cases; account directory plugins;
  opt-in `/v1/match`; Docker image built from `uv.lock` with hash checking.

### Security
- A pre-release review found false matches (e.g. *Siemens AG* vs *Siemens Energy AG*),
  name leaks through generic words, and slow crafted inputs; all are fixed and kept as
  regression tests (`tests/test_review_regressions.py`).

[Unreleased]: https://github.com/nadaboulaares/nameproof/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/nadaboulaares/nameproof/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/nadaboulaares/nameproof/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nadaboulaares/nameproof/releases/tag/v0.1.0
