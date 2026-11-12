# Roadmap

## Why now

Under the EU Instant Payments Regulation ((EU) 2024/886), every payment service provider
must check the payee's name before a euro credit transfer: **Verification of Payee**.

| Who | Deadline |
|---|---|
| PSPs in euro-area member states | **9 October 2025** (in force) |
| Bulgaria (euro since 1 January 2026) | **1 January 2027** |
| PSPs in non-euro member states (CZ, DK, HU, PL, RO, SE) | **9 July 2027** |

It covers all euro credit transfers (SCT and SCT Inst). The EPC standardises the
inter-PSP API ([EPC103-24 v1.1.1](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-05/EPC103-24%20v1.1.1%20VOP%20API%20Specifications.pdf))
and recommends matching rules ([EPC288-23 v2.0](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-11/EPC288-23%20v2.0%20EPC%20Recommendations%20for%20the%20Matching%20Processes%20under%20the%20VOP%20Scheme%20Rulebook.pdf), November 2026), but each responding
bank chooses and is liable for its own matching. nameproof is an open, tested,
explainable implementation of that matching.

## Done (0.1.0)

- **Matcher**: Latin with diacritics, Greek (ELOT 743), Cyrillic (ICAO 9303, BGN/PCGN,
  national systems), Arabic (consonant skeleton), names with initials, particles,
  compounds and titles, joint accounts, about 1,400 company legal forms (GLEIF ELF).
- **Policies**: `epc-default@1` follows EPC288-23 v2.0; `lenient@1` accepts a few
  documented equivalences as a match.
- **Benchmark**: nameproof-bench v1, 6,000 labelled pairs from Wikidata.
- **Service**: EPC VoP responder tested against the EPC reference test cases (EPC139-25),
  Docker image.
- **Playground**: runs in the browser.
- **Security review**: adversarial cases (false matches, name leaks, crafted input)
  are part of the test suite (`tests/test_review_regressions.py`).

## Done (0.2.0)

- **Duplicate finding**: `nameproof dedupe` and `find_duplicates()`, with cross-script
  blocking keys and parallel comparison.
- **Policies**: `epc-default@2` and `lenient@2`: a clearly different word in a person's
  name is no match.

## Next

- [ ] Records policy for non-payment use: known spelling variants (*Mohamed* / *Mohammed*,
      *Fatma* / *Fatima*) count as a match; Arabic-script comparisons still go to review
- [ ] Better Arabic: Maghreb and Gulf spellings, long vowels (*محمد* vs *Mahmoud*), and an
      Arabic slice built for duplicate finding
- [ ] Dedupe in the browser playground (paste a list, nothing uploaded)
- [ ] Optional extra fields for dedupe (date of birth) without becoming a full MDM tool

- [ ] Hebrew, Armenian and Georgian romanisation; more Arabic dialect conventions
- [ ] UK Confirmation of Payee, India and PIX presets
- [ ] Optional learned re-ranker trained on the benchmark (CPU)
- [ ] Benchmark v2: more company pairs, adversarial pairs from the review, real-world
      spelling variants contributed by users
- [ ] Java and .NET clients for the service

Ideas and contributions are welcome: open an issue.
