# Changelog

All notable changes to nameproof are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Policies are versioned separately
(`epc-default@1`): a policy change never alters an existing policy id.

## [Unreleased]

### Playground
- Shareable example links: `#p=<provided name>&a=<account names>` pre-fills the page.
  The part after `#` never leaves the browser.
- Clearer explanation for `missing_name_part`; demo GIF in the README.

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

[Unreleased]: https://github.com/nadaboulaares/nameproof/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nadaboulaares/nameproof/releases/tag/v0.1.0
