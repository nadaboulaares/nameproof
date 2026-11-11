# nameproof service: EPC Verification of Payee responder

An HTTP service that answers Verification of Payee requests in the format of the
**EPC VOP Inter-PSP API Specifications (EPC103-24 v1.1.1)**, using nameproof to match
names across scripts.

```bash
pip install "nameproof[service]"
NAMEPROOF_DIRECTORY=json:examples/accounts.json nameproof serve --host 0.0.0.0 --port 8080
```

or with Docker:

```bash
docker build -t nameproof .
docker run -p 8080:8080 -e NAMEPROOF_DIRECTORY=json:/data/accounts.json \
  -v "$PWD/examples:/data:ro" nameproof
```

## Endpoints

| Method & path | Purpose |
|---|---|
| `POST /vop/v1/payee-verifications` | EPC VoP responder: name + IBAN, or identification code + IBAN |
| `POST /v1/match` | Matching only: `{"provided": "...", "accountNames": ["..."]}` → nameproof verdict. **Off by default** (`NAMEPROOF_MATCH_ENDPOINT=1`) |
| `GET /health` | Liveness: version, policy, whether the VoP responder is enabled |
| `GET /docs`, `GET /openapi.json` | OpenAPI UI and document (disable with `NAMEPROOF_DOCS=0`) |

`/v1/match` is for banks whose VoP gateway already speaks the EPC protocol and only
needs a matcher: look up the holder names yourself, then ask nameproof. It accepts
arbitrary account names, so it is off by default; enable it only behind authentication.

### Example

```http
POST /vop/v1/payee-verifications
Content-Type: application/json
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Request-Timestamp: 2026-11-10T13:52:14.77Z

{"party": {"name": "Yorgos Papadopoulos"},
 "partyAccount": {"iban": "GR1601101250000000012300695"},
 "partyAgent": {"financialInstitutionId": {"bicfi": "ABCDBEBBXXX"}},
 "requestingAgent": {"financialInstitutionId": {"bicfi": "ABCDBEB0XXX"}}}
```

```http
HTTP/1.1 200 OK
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Response-Timestamp: 2026-11-10T13:52:15.008Z

{"partyNameMatch": "CMTC", "matchedName": "Giorgos Papadopoulos"}
```

The account holder is stored as *Γιώργος Παπαδόπουλος*. The payer's *Yorgos* is an
informal spelling, so the answer is a close match, with the real name shown in SEPA
Latin.

## Verdicts

| nameproof | `partyNameMatch` | Notes |
|---|---|---|
| `MATCH` | `MTCH` | |
| `CLOSE_MATCH` | `CMTC` + `matchedName` | `matchedName` is sent **only** with `CMTC` (§4.1.3.3) |
| `NO_MATCH` | `NMTC` | |
| `NOT_POSSIBLE` | `NOAP` | also for unknown accounts |

Identification checks (`lei`, `anyBIC`, `others[]` with `schemeNameCode` or
`schemeNameProprietary`) compare the code with the account's identifiers, ignoring case
and spaces: `MTCH` / `NMTC`, or `NOAP` when the account has no identifier of that scheme
(§4.2.6). They never return `CMTC`.

## Configuration

All settings are environment variables; every one has a safe default.

| Variable | Default | Meaning |
|---|---|---|
| `NAMEPROOF_DIRECTORY` | *(none)* | `json:<path>` or `plugin:<module>:<factory>`. Without it only `/v1/match` is served |
| `NAMEPROOF_POLICY` | `epc-default@1` | nameproof decision policy |
| `NAMEPROOF_ALLOWED_REQUESTING_BICS` | *(any)* | comma-separated BIC11s; others get `401 CLIENT_INVALID` |
| `NAMEPROOF_CLIENT_BIC_HEADER` | *(off)* | header in which your TLS gateway passes the BIC it verified; must equal `requestingAgent`, else `401 CLIENT_INCONSISTENT` |
| `NAMEPROOF_MAX_REQUEST_AGE_S` | `300` | older `X-Request-Timestamp` → `TIMESTAMP_INVALID` |
| `NAMEPROOF_MAX_CLOCK_SKEW_S` | `30` | timestamps further in the future → `TIMESTAMP_INVALID` |
| `NAMEPROOF_MAX_BODY_BYTES` | `16384` | larger bodies → `400 FORMAT_ERROR` |
| `NAMEPROOF_MAX_HOLDER_NAMES` | `10` | names compared per account, 1–20 (bounds the work per request) |
| `NAMEPROOF_REQUEST_CHARSET` | `latin` | characters accepted in `name` / remittance info: `latin` (basic set + Latin diacritics), `sepa-basic`, or `any` |
| `NAMEPROOF_LATIN_MATCHED_NAME` | `true` | write `matchedName` in the SEPA basic Latin set (§3.1) |
| `NAMEPROOF_MATCH_ENDPOINT` | `false` | serve `POST /v1/match` |
| `NAMEPROOF_DOCS` | `true` | serve `/docs` and `/openapi.json` |

## Account directory

The responder needs to know who holds an IBAN. Give it a JSON file for demos:

```json
{"GR1601101250000000012300695": {"names": ["Γιώργος Παπαδόπουλος"]},
 "BG80BNBG96611020345678": {"names": ["Енерго ЕООД"], "identifiers": {"LEI": "529900T8BM49AURSDO55"}}}
```

In production, write a plugin that queries your core banking system:

```python
# my_bank/vop.py  →  NAMEPROOF_DIRECTORY=plugin:my_bank.vop:directory
from nameproof.service import AccountRecord


class CoreBankingDirectory:
    def lookup(self, iban: str) -> AccountRecord | None:
        account = core_banking.find(iban)  # your code
        if account is None or account.closed:
            return None  # -> NOAP
        return AccountRecord(
            names=tuple(holder.full_name for holder in account.holders),
            identifiers={"LEI": account.lei} if account.lei else {},
        )


def directory() -> CoreBankingDirectory:
    return CoreBankingDirectory()
```

List each holder of a joint account as a separate name: a close match then reveals
only the matching holder (data minimisation).

## Deployment

The EPC trust model has two parts, and both belong to the bank's **API gateway** in
front of this service:

1. **Mutual TLS** with the requester's PSD2 QWAC (§2.4.1).
2. **The EPC Directory Service (EDS) check**: the certificate's NAN and the
   `requestingAgent` BIC must be registered together (§2.4.2).

Pass the BIC your gateway verified in a header and set `NAMEPROOF_CLIENT_BIC_HEADER`,
so a mismatch is answered with `CLIENT_INCONSISTENT`. Rate limiting also belongs to the
gateway.

**Privacy.** The service is stateless and keeps no data. Its log lines record method, path,
status, latency and the result code (e.g. `verification partyNameMatch=CMTC`), but **never
names, IBANs or identifiers**. uvicorn's access log adds the client address; route logs
to your own pipeline as usual.

**Load.** Matching runs in a worker thread. Names are capped at 140 characters and 10
words (checked after Unicode normalisation), and each name is expanded into a bounded
number of spellings, so a crafted request costs at most a few hundred milliseconds of
CPU. Rate-limit at the gateway.

## Errors

Errors are RFC 7807 `application/problem+json` bodies (§4.4):

```json
{"type": "https://github.com/nadaboulaares/nameproof/blob/main/docs/SERVICE.md#errors",
 "code": "FORMAT_ERROR", "title": "Bad Request", "status": 400,
 "detail": "/partyAccount/bban: Extra inputs are not permitted",
 "instance": "/partyAccount/bban"}
```

| `code` | HTTP | When |
|---|---|---|
| `FORMAT_ERROR` | 400 | malformed JSON, missing/unknown/mutually exclusive fields, bad IBAN/BIC/LEI format, bad headers, characters outside the agreed set, body too large |
| `TIMESTAMP_INVALID` | 400 | `X-Request-Timestamp` missing, malformed (incl. trailing zero milliseconds), too old or in the future |
| `CLIENT_INVALID` | 401 | requesting BIC not in `NAMEPROOF_ALLOWED_REQUESTING_BICS` |
| `CLIENT_INCONSISTENT` | 401 | requesting BIC differs from the one the gateway authenticated |
| `INTERNAL_ERROR` | 500 | unexpected failure (details are logged, not returned) |

## Conformance

Tests in [`tests/test_service.py`](../tests/test_service.py) are named after the
reference cases of the **EPC VOP API Reference Toolbox (EPC139-25 v1.2)**.

| Reference cases | Status |
|---|---|
| Positive name checks `_000`–`_003`, `_010`–`_013`, `_100`–`_103`, `_110`–`_113` | ✅ tested (`RES_002`: *J. Smith* → `CMTC` "John Smith"; `RES_102`: *Corp. ABC SA* → `CMTC` "Corporation ABC s.a.") |
| Positive identification checks: LEI `_2xx`, BIC `_3xx`, TXID `_4xx`, proprietary `_5xx` | ✅ tested |
| Negative responding side `RSR_001`–`RSR_032`, `RSR_035`–`RSR_050` | ✅ tested |
| `RSR_033`, `RSR_034` (invalid / revoked certificate) | ↗ API gateway (mutual TLS) |

### Interpretations, stated openly

- **`partyIdMatch` for identification checks.** EPC139-25 lists `"partyNameMatch"` as the
  expected field for LEI/BIC cases, but the API specification (§4.1.3.3, §5.2) defines
  `partyIdMatch` for them. The service follows the API specification.
- **BIC11 only.** The API spec's BICFI pattern allows 8-character BICs, but the reference
  tests `RSR_043`–`RSR_045` require rejecting them.
- **IBAN format, not checksum.** IBANs are validated with the spec's pattern (§4.2.7). An
  IBAN with wrong check digits can't be in the directory, so it gets `NOAP`. The spec's own
  example IBAN `BE12345678901234` has invalid check digits.
- **Unknown or closed account → `NOAP`.**
- **A close match that can't be written in Latin → `NOAP`.** If the holder's name only
  exists in a script with no official romanisation (e.g. Arabic) and `matchedName` must be
  in the SEPA Latin set, the close match can't be shown, so verification is not possible.
  Set `NAMEPROOF_LATIN_MATCHED_NAME=false` if your scheme community agreed to exchange
  other characters.
- **Name matching rules.** The default policy `epc-default@1` follows the EPC
  Recommendations for the Matching Processes (EPC288-23 v2.0, November 2026): `MATCH`
  only when first and last name (or the company name) are identical after data clean-up;
  spelling mistakes, swapped letters, an initial instead of the first name, abbreviations,
  and company words out of order are close matches (`RES_002`, `RES_102`). nameproof's
  clean-up also applies official romanisations of the stored name (the EPC asks for the
  stored name to be converted to Latin) and German/Nordic letter expansions
  (*Müller* = *Mueller*). A surname alone, initials alone or a generic word never yields
  a close match, so the service can't be used to look up an account holder's name.
