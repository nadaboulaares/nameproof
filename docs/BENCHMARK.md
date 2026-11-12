# Benchmark results

Generated with:

```bash
uv run nameproof bench bench/data/nameproof-bench-v1.jsonl # then paste below
```

Dataset: **nameproof-bench v1**: 6,000 labelled pairs (3,750 same person/company,
2,250 different) in 15 slices, built from Wikidata (CC0). See
[bench/README.md](../bench/README.md) for how it is built and what it contains.

**Baselines** (fixed thresholds: ≥ 0.95 → MATCH, ≥ 0.85 → CLOSE_MATCH):

- `exact`: case- and whitespace-insensitive equality
- `levenshtein`: normalised Levenshtein similarity
- `token-sort`: diacritic-folded, word-order-insensitive fuzzy ratio (rapidfuzz)

**How to read it.** For the *same* entity, a rejection (NO_MATCH / NOT_POSSIBLE) is
customer friction: the payer is told the name is wrong when it isn't. A `CLOSE_MATCH`
shows the payer the real name to confirm. For *different* entities, a `MATCH` is the
fraud risk: the payment goes through with no warning.

**Policy:** `epc-default@2` (EPC288-23 v2.0): dropped particles, legal-form variants and
reordered company names are close matches, not matches, and a clearly different word in a
person's name is no match. Compared with `epc-default@1` (0.1.0) this moves six
different-person pairs (*Béla Bartók* / *Eva Bartok*) and six same-entity pairs (four
company names without a legal form that were translated, a heavy typo and a nickname) from
close match to no match.

**Known hard cases kept in on purpose:** exonyms and stage names (*Irene Papas* /
*Ειρήνη Παπά*, *John Paul II* / *Jan Paweł II*) and company names that are
translated rather than transliterated (*International Industrial Bank* /
*Международный промышленный банк*). No spelling-based matcher can link these, which is
why the company slices have high rejection rates for every system.

**Same person/company: wrongly rejected** (NO_MATCH or NOT_POSSIBLE; n=3750, lower is better)

| slice | nameproof | exact | levenshtein | token-sort |
|---|---|---|---|---|
| greek | 7.6% | 100.0% | 100.0% | 100.0% |
| russian | 4.8% | 100.0% | 100.0% | 100.0% |
| ukrainian | 8.8% | 100.0% | 100.0% | 100.0% |
| bulgarian | 4.8% | 100.0% | 100.0% | 100.0% |
| serbian | 2.4% | 100.0% | 100.0% | 100.0% |
| arabic | 16.8% | 100.0% | 100.0% | 100.0% |
| polish | 1.2% | 71.6% | 46.0% | 23.2% |
| czech | 0.0% | 82.0% | 49.6% | 17.2% |
| hungarian | 1.6% | 81.2% | 52.4% | 18.4% |
| romanian | 0.0% | 80.8% | 48.0% | 24.0% |
| german | 0.0% | 77.6% | 52.0% | 26.0% |
| french | 0.8% | 77.6% | 52.8% | 26.0% |
| spanish | 0.0% | 76.0% | 46.8% | 22.0% |
| greek-company | 41.2% | 100.0% | 100.0% | 100.0% |
| cyrillic-company | 55.6% | 100.0% | 100.0% | 100.0% |
| **all** | 9.7% | 89.8% | 76.5% | 63.8% |

**Same person/company: auto-matched** (MATCH; n=3750, higher is better)

| slice | nameproof | exact | levenshtein | token-sort |
|---|---|---|---|---|
| greek | 38.0% | 0.0% | 0.0% | 0.0% |
| russian | 44.4% | 0.0% | 0.0% | 0.0% |
| ukrainian | 12.8% | 0.0% | 0.0% | 0.0% |
| bulgarian | 44.8% | 0.0% | 0.0% | 0.0% |
| serbian | 51.2% | 0.0% | 0.0% | 0.0% |
| arabic | 0.0% | 0.0% | 0.0% | 0.0% |
| polish | 56.4% | 28.4% | 31.6% | 58.8% |
| czech | 60.0% | 18.0% | 18.4% | 60.4% |
| hungarian | 62.0% | 18.8% | 19.6% | 62.8% |
| romanian | 47.6% | 19.2% | 21.6% | 47.6% |
| german | 53.2% | 22.4% | 25.6% | 54.0% |
| french | 51.6% | 22.4% | 23.6% | 52.8% |
| spanish | 59.6% | 24.0% | 29.2% | 56.4% |
| greek-company | 26.4% | 0.0% | 0.0% | 0.0% |
| cyrillic-company | 18.0% | 0.0% | 0.0% | 0.0% |
| **all** | 41.7% | 10.2% | 11.3% | 26.2% |

**Different people/companies: false MATCH** (n=2250, lower is better)

| slice | nameproof | exact | levenshtein | token-sort |
|---|---|---|---|---|
| greek | 0.0% | 0.0% | 0.0% | 0.0% |
| russian | 0.0% | 0.0% | 0.0% | 0.0% |
| ukrainian | 0.0% | 0.0% | 0.0% | 0.0% |
| bulgarian | 0.0% | 0.0% | 0.0% | 0.0% |
| serbian | 0.0% | 0.0% | 0.0% | 0.0% |
| arabic | 0.0% | 0.0% | 0.0% | 0.0% |
| polish | 0.0% | 0.0% | 0.0% | 0.0% |
| czech | 0.0% | 0.0% | 0.0% | 0.0% |
| hungarian | 0.0% | 0.0% | 0.0% | 0.0% |
| romanian | 0.0% | 0.0% | 0.0% | 0.0% |
| german | 0.0% | 0.0% | 0.0% | 0.0% |
| french | 0.0% | 0.0% | 0.0% | 0.0% |
| spanish | 0.0% | 0.0% | 0.0% | 0.0% |
| greek-company | 0.0% | 0.0% | 0.0% | 0.0% |
| cyrillic-company | 0.0% | 0.0% | 0.0% | 0.0% |
| **all** | 0.0% | 0.0% | 0.0% | 0.0% |

**Different people/companies: shown the other's name** (CLOSE_MATCH; n=2250, lower is better)

| slice | nameproof | exact | levenshtein | token-sort |
|---|---|---|---|---|
| greek | 0.7% | 0.0% | 0.0% | 0.0% |
| russian | 0.7% | 0.0% | 0.0% | 0.0% |
| ukrainian | 1.3% | 0.0% | 0.0% | 0.0% |
| bulgarian | 0.7% | 0.0% | 0.0% | 0.0% |
| serbian | 2.0% | 0.0% | 0.0% | 0.0% |
| arabic | 2.0% | 0.0% | 0.0% | 0.0% |
| polish | 0.7% | 0.0% | 0.0% | 0.7% |
| czech | 1.3% | 0.0% | 0.7% | 0.7% |
| hungarian | 0.7% | 0.0% | 0.0% | 0.7% |
| romanian | 0.7% | 0.0% | 0.0% | 0.7% |
| german | 0.7% | 0.0% | 0.0% | 0.0% |
| french | 1.3% | 0.0% | 0.0% | 0.0% |
| spanish | 0.7% | 0.0% | 0.0% | 0.0% |
| greek-company | 0.0% | 0.0% | 0.0% | 0.0% |
| cyrillic-company | 0.7% | 0.0% | 0.0% | 0.0% |
| **all** | 0.9% | 0.0% | 0.0% | 0.2% |

**Why nameproof shows more close matches for different people than the baselines:** the
baselines reject almost every cross-script name, so they rarely show any name at all. A
nameproof close match on a different person is mostly a relative or namesake with one
similar word; the payer sees the real name and can stop.

**nameproof by variation** (share of each verdict)

| label | variation | n | MATCH | CLOSE | NO | NOT POSSIBLE |
|---|---|---|---|---|---|---|
| same | uppercase | 824 | 72.3% | 18.6% | 9.1% | 0.0% |
| same | typo | 789 | 0.1% | 86.4% | 13.4% | 0.0% |
| same | reordered | 729 | 73.0% | 18.4% | 8.6% | 0.0% |
| same | native_script | 455 | 46.8% | 35.4% | 17.8% | 0.0% |
| same | initial | 669 | 0.0% | 96.4% | 3.6% | 0.0% |
| same | english_label | 75 | 56.0% | 32.0% | 12.0% | 0.0% |
| same | dropped_middle | 52 | 46.2% | 42.3% | 11.5% | 0.0% |
| same | ascii_typed | 157 | 100.0% | 0.0% | 0.0% | 0.0% |
| different | same_surname | 640 | 0.0% | 3.3% | 96.7% | 0.0% |
| different | different_person | 1610 | 0.0% | 0.0% | 100.0% | 0.0% |

nameproof latency: p50 0.33 ms, p95 0.82 ms (measured on an idle machine)
