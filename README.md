# nameproof

[![CI](https://github.com/nadaboulaares/nameproof/actions/workflows/ci.yml/badge.svg)](https://github.com/nadaboulaares/nameproof/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nameproof.svg)](https://pypi.org/project/nameproof/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](pyproject.toml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Open-source, explainable name matching across scripts for payments.**

Is *"Γιώργος Παπαδόπουλος"* the same payee as *"Giorgos Papadopoulos"* or *"G. Papadopoulos"*?
`nameproof` answers **Match / Close match / No match** for EU **Verification of Payee (VoP)**,
UK Confirmation of Payee and KYC, and explains every decision.

**[▶ Try it in your browser](https://nadaboulaares.github.io/nameproof/)**: nothing you type leaves the page.

<a href="https://nadaboulaares.github.io/nameproof/"><img src="docs/assets/playground-demo.gif" width="760" alt="nameproof playground: a Greek name matches its romanisation, an Arabic name is a close match, a typo is a close match, Siemens AG vs Siemens Energy AG is a close match, and Ahmed vs Hamid is no match."></a>

```bash
pip install nameproof
```

- **Latin script** with diacritics (*José García*, *Wałęsa*, *Müller* = *Mueller*, *Đoković* = *Djokovic*)
- **Greek, Cyrillic and Arabic**: official romanisations (ELOT 743, ICAO 9303, national systems)
- **Real names**: initials, word order, particles (*van der*, *al-*), compound names, titles, joint accounts
- **Companies**: about 1,400 legal forms (GmbH, Sp. z o.o., S.R.L., ΑΕ, ЕООД, …) from the GLEIF ISO 20275 list
- **Safe by design**: follows the EPC matching recommendations (EPC288-23 v2.0): only names identical after
  clean-up match; the real name is only revealed on a close match, never to a probe like a surname alone
- **Deterministic and fast**: versioned policies, CPU-only, typically under 1 ms per check, bounded work
  for crafted input, no data leaves your servers
- **EPC VoP responder** included, tested against the EPC reference test cases

## Benchmark

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/benchmark-dark.svg">
  <img alt="Same person wrongly rejected: nameproof 9.5%, token-sort 63.8%, Levenshtein 76.5%, exact match 89.8%. Same person auto-matched: nameproof 41.7%, token-sort 26.2%, Levenshtein 11.3%, exact match 10.2%. Different people falsely matched: 0.0% for every system." src="docs/assets/benchmark-light.svg">
</picture>

On [nameproof-bench](bench/README.md), 6,000 labelled name pairs across Greek, Cyrillic,
Arabic and Latin scripts built from Wikidata, against typical fuzzy-matching baselines:

| | nameproof | token-sort | Levenshtein | exact |
|---|---|---|---|---|
| Same person **wrongly rejected** (lower is better) | **9.5%** | 63.8% | 76.5% | 89.8% |
| Same person **auto-matched** (higher is better) | **41.7%** | 26.2% | 11.3% | 10.2% |
| Different people **falsely matched** (fraud risk) | **0.0%** | 0.0% | 0.0% | 0.0% |

Everything nameproof doesn't auto-match or reject is a `CLOSE_MATCH`: the payer is shown
the real name and decides. Typos and initials land there by design. Full per-script and
per-variation results: [docs/BENCHMARK.md](docs/BENCHMARK.md).

```bash
uv run nameproof bench bench/data/nameproof-bench-v1.jsonl
```

## Verification of Payee service

`nameproof` also ships an HTTP responder that speaks the **EPC VoP Inter-PSP API**
(EPC103-24 v1.1.1) and is tested against the EPC reference test cases (EPC139-25 v1.2):

```bash
pip install "nameproof[service]"
NAMEPROOF_DIRECTORY=json:examples/accounts.json nameproof serve
```

```console
$ curl -X POST localhost:8080/vop/v1/payee-verifications -H 'Content-Type: application/json' \
    -H "X-Request-ID: $(uuidgen)" -H "X-Request-Timestamp: $(date -u +%FT%TZ)" \
    -d '{"party": {"name": "Yorgos Papadopoulos"}, "partyAccount": {"iban": "GR1601101250000000012300695"},
         "partyAgent": {"financialInstitutionId": {"bicfi": "ABCDBEBBXXX"}},
         "requestingAgent": {"financialInstitutionId": {"bicfi": "ABCDBEB0XXX"}}}'
{"partyNameMatch":"CMTC","matchedName":"Giorgos Papadopoulos"}
```

Docker image, configuration, account-directory plugins and the conformance table:
[docs/SERVICE.md](docs/SERVICE.md).

## Quickstart

```python
from nameproof import match

match("Jon Smyth", ["John Smith"])
# Verdict(result=CLOSE_MATCH, score=0.8442, suggested_name='John Smith', explanation=('fuzzy_token',), ...)

match("Mueller Anna", ["Anna Müller"]).result  # MATCH  (letter_expansion, token_reorder)
match("Maria Garcia", ["Mario Garcia"]).result  # CLOSE_MATCH, never MATCH: spellings differ
match("John Smith", ["John and Mary Smith"]).result  # MATCH  (joint_account_holder, shared_surname)
```

```console
$ nameproof match "Jon Smyth" "John Smith"
CLOSE_MATCH  score=0.8442  policy=epc-default@1
  suggested name: John Smith
  why: fuzzy_token
```

**How verdicts work** (default policy `epc-default@1`, following
[EPC288-23 v2.0](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-11/EPC288-23%20v2.0%20EPC%20Recommendations%20for%20the%20Matching%20Processes%20under%20the%20VOP%20Scheme%20Rulebook.pdf)):

| Result | When |
|---|---|
| `MATCH` | identical after clean-up: case, diacritics, punctuation, titles, word order of a person's name, official romanisation of the stored name. A person's extra middle names or a trailing female patronymic are allowed (first and last name exact) |
| `CLOSE_MATCH` | small differences: a typo, swapped letters, an initial, an abbreviation, a dropped particle (*van*), a legal form spelled differently or missing, company words in another order. The real name is returned so the payer can decide |
| `NO_MATCH` | a different person or company, or too little to go on (a surname alone, initials alone, a generic word like *GmbH*) |
| `NOT_POSSIBLE` | nothing to compare: empty, longer than 140 characters or 10 words, or a script nameproof can't romanise yet |

Banks that accept dropped particles, legal-form variants and reordered company names as
a match can use the `lenient@1` policy.

Every verdict lists stable explanation codes (`Reason`) that never contain name fragments,
and the account holder's name is only ever exposed on `CLOSE_MATCH`.

## Data sources

- Company legal forms: the [ISO 20275 Entity Legal Forms code list](https://www.gleif.org/en/lei-data/code-lists/iso-20275-entity-legal-forms-code-list)
  v1.6, published by GLEIF under CC0 1.0. nameproof is not affiliated with or endorsed by GLEIF.
- Benchmark names: [Wikidata](https://www.wikidata.org/) (CC0 1.0), deceased people only.
- Romanisation tables are written from the public standards (ELOT 743, ICAO 9303, BGN/PCGN,
  the Bulgarian and Ukrainian national systems).

## Development

```bash
uv sync
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues privately — see [SECURITY.md](SECURITY.md).

Licensed under [Apache-2.0](LICENSE).
