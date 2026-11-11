# nameproof for banks and payment institutions

Open-source, explainable payee-name matching for EU **Verification of Payee** (VoP):
fewer false "No Match" answers for your customers, no false matches for fraudsters.

> **Deadlines.** VoP has applied to euro-area PSPs since 9 October 2025. It applies to
> **Bulgarian PSPs from 1 January 2027** and to PSPs in CZ, DK, HU, PL, RO and SE from
> **9 July 2027**, for all euro credit transfers (Regulation (EU) 2024/886). The EPC
> standardises the API between banks; the *matching* is left to each responding bank,
> which carries the liability for it.

## What it does

- **Matches across scripts.** A payer types *Giorgos Papadopoulos*; the account is held as
  *Γιώργος Παπαδόπουλος*, giving a Match. Greek (ELOT 743), Cyrillic (ICAO 9303, BGN/PCGN,
  the Bulgarian and Ukrainian national systems) and Arabic are supported.
- **Handles real names.** Diacritics, initials, word order, particles, hyphenated names,
  titles, joint accounts, middle names and patronymics.
- **Handles companies.** About 1,400 legal forms from the GLEIF ISO 20275 list (GmbH,
  Sp. z o.o., ЕООД, Α.Ε., S.R.L.).
- **Follows the EPC matching recommendations** (EPC288-23 v2.0). Only names identical
  after clean-up give Match. Typos, initials and abbreviations give Close Match, with the
  real name shown to the payer.
- **Explains every answer** with stable reason codes for your audit trail. Policies are
  versioned, so the same input always gives the same answer.
- **Includes an EPC VoP responder** (EPC103-24 v1.1.1), tested against the EPC reference
  test cases (EPC139-25).

## Measured, in public

On [nameproof-bench](../bench/README.md), an open benchmark of 6,000 labelled name pairs,
against typical fuzzy-matching approaches:

| | nameproof | token-sort fuzzy | Levenshtein | exact match |
|---|---|---|---|---|
| Same person wrongly rejected (lower is better) | **9.5%** | 63.8% | 76.5% | 89.8% |
| Same person matched automatically | **41.7%** | 26.2% | 11.3% | 10.2% |
| Different people falsely matched (fraud risk) | **0.0%** | 0.0% | 0.0% | 0.0% |

The rest are Close Matches: the payer sees the real name and decides. Before release, the
code went through an adversarial security review. Every false match and name leak it found
is fixed and kept as a regression test.

## How it fits your stack

- Runs as a self-hosted Docker image or a Python library, on CPU, typically in under 1 ms
  per check.
- Sits behind your API gateway, which keeps mutual TLS (QWAC) and the EPC Directory
  Service checks.
- Plugs into your core banking through a small account-directory adapter. Alternatively,
  run it as a matching-only service behind your existing VoP gateway. See
  [SERVICE.md](SERVICE.md).

## Data protection

- No data leaves your infrastructure, and the service is stateless.
- No names, IBANs or identifiers appear in logs.
- Data minimisation: a Close Match reveals only the matching holder of a joint account.
  A surname or a generic word on its own never reveals a name.

## Design-partner pilot

I'm looking for **two or three PSPs** to pilot nameproof before their VoP deadline. They
get integration support, tuning against their own anonymised name samples (including
their current Close Match rate), and priority on the features they need. In return, I ask
for feedback, and a reference if it works for you.

Interested? Contact [the maintainer on GitHub](https://github.com/nadaboulaares) or open
an issue.

---

**Try it:** [the playground](https://nadaboulaares.github.io/nameproof/) runs in your browser
and sends nothing · `pip install nameproof` · `docker pull ghcr.io/nadaboulaares/nameproof`

Apache-2.0. nameproof is a matching tool, not legal or compliance advice; the responding
PSP remains responsible for its VoP answers.
