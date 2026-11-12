"""EPC VoP responder: conformance with EPC103-24 v1.1.1 and the EPC139-25 v1.2 test cases.

Test names carry the EPC reference (``test_rsr_001...`` for "RSR_001" negative
responding-side cases, ``test_res_000...`` for positive cases), so coverage of
the official test list can be audited. Names and IBANs are synthetic or
published examples.
"""

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nameproof.service import AccountRecord, InMemoryDirectory, Settings
from nameproof.service.app import VOP_PATH, create_app
from nameproof.service.formats import TIMESTAMP_PATTERN, format_timestamp

REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"
REQUESTER, RESPONDER = "ABCDBEB0XXX", "ABCDBEBBXXX"
IBAN_PERSON = "BE68539007547034"
IBAN_COMPANY = "DE89370400440532013000"
IBAN_GREEK = "GR1601101250000000012300695"
IBAN_ARABIC = "FR1420041010050500013M02606"
IBAN_UNKNOWN = "ES9121000418450200051332"
LEI = "529900T8BM49AURSDO55"
TXID = {"identification": "1", "schemeNameCode": "TXID"}

DIRECTORY = InMemoryDirectory(
    {
        IBAN_PERSON: AccountRecord(("John Smith",)),
        IBAN_COMPANY: AccountRecord(
            ("Corporation ABC s.a.",),
            {"LEI": LEI, "BIC": "CORPDEFFXXX", "TXID": "DE123456789", "INTERNAL": "C-42"},
        ),
        IBAN_GREEK: AccountRecord(("Γιώργος Παπαδόπουλος",)),
        IBAN_ARABIC: AccountRecord(("محمد علي",)),
    }
)


def now() -> str:
    return format_timestamp(datetime.now(UTC))


def headers(**overrides: str | None) -> dict[str, str]:
    base: dict[str, str | None] = {
        "X-Request-ID": REQUEST_ID,
        "X-Request-Timestamp": now(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def body(
    party: dict[str, Any] | None = None, iban: str | None = IBAN_PERSON, **extra: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "party": party if party is not None else {"name": "John Smith"},
        "partyAccount": {"iban": iban},
        "partyAgent": {"financialInstitutionId": {"bicfi": RESPONDER}},
        "requestingAgent": {"financialInstitutionId": {"bicfi": REQUESTER}},
    }
    if iban is None:
        del payload["partyAccount"]
    payload.update(extra)
    return payload


def org(**identifier: Any) -> dict[str, Any]:
    return {"identification": {"organisationId": identifier}}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(), DIRECTORY)) as test_client:
        yield test_client


def post(client: TestClient, payload: Any, **header_overrides: str | None) -> Any:
    return client.post(VOP_PATH, json=payload, headers=headers(**header_overrides))


def assert_error(response: Any, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["code"] == code
    assert problem["status"] == status
    assert problem["type"].startswith("https://")


# --- positive cases (EPC139-25 chapter 2) -------------------------------------


@pytest.mark.parametrize(
    ("ref", "party", "iban", "expected"),
    [
        ("RES_000", {"name": "John Smith"}, IBAN_PERSON, {"partyNameMatch": "MTCH"}),
        ("RES_001", {"name": "Peter Brown"}, IBAN_PERSON, {"partyNameMatch": "NMTC"}),
        ("RES_002", {"name": "J. Smith"}, IBAN_PERSON,
         {"partyNameMatch": "CMTC", "matchedName": "John Smith"}),
        ("RES_003", {"name": "John Smith"}, IBAN_UNKNOWN, {"partyNameMatch": "NOAP"}),
        ("RES_100", {"name": "Corporation ABC SA"}, IBAN_COMPANY, {"partyNameMatch": "MTCH"}),
        ("RES_101", {"name": "Globex GmbH"}, IBAN_COMPANY, {"partyNameMatch": "NMTC"}),
        ("RES_102", {"name": "Corp. ABC SA"}, IBAN_COMPANY,
         {"partyNameMatch": "CMTC", "matchedName": "Corporation ABC s.a."}),
        ("RES_103", {"name": "Corp. ABC SA"}, IBAN_UNKNOWN, {"partyNameMatch": "NOAP"}),
        ("RES_200", org(lei=LEI), IBAN_COMPANY, {"partyIdMatch": "MTCH"}),
        ("RES_201", org(lei="5493001KJTIIGC8Y1R12"), IBAN_COMPANY, {"partyIdMatch": "NMTC"}),
        ("RES_203", org(lei=LEI), IBAN_PERSON, {"partyIdMatch": "NOAP"}),
        ("RES_300", org(anyBIC="CORPDEFFXXX"), IBAN_COMPANY, {"partyIdMatch": "MTCH"}),
        ("RES_301", org(anyBIC="OTHRDEFFXXX"), IBAN_COMPANY, {"partyIdMatch": "NMTC"}),
        ("RES_303", org(anyBIC="CORPDEFFXXX"), IBAN_UNKNOWN, {"partyIdMatch": "NOAP"}),
        ("RES_400", org(others=[{"identification": "DE 123456789", "schemeNameCode": "TXID"}]),
         IBAN_COMPANY, {"partyIdMatch": "MTCH"}),
        ("RES_401", org(others=[{"identification": "DE999", "schemeNameCode": "TXID"}]),
         IBAN_COMPANY, {"partyIdMatch": "NMTC"}),
        ("RES_403", org(others=[{"identification": "X1", "schemeNameCode": "DUNS"}]),
         IBAN_COMPANY, {"partyIdMatch": "NOAP"}),
        ("RES_500", org(others=[{"identification": "C-42", "schemeNameProprietary": "internal"}]),
         IBAN_COMPANY, {"partyIdMatch": "MTCH"}),
    ],
)  # fmt: skip
def test_positive_cases(
    client: TestClient, ref: str, party: dict[str, Any], iban: str, expected: dict[str, str]
) -> None:
    response = post(client, body(party, iban))
    assert response.status_code == 200, f"{ref}: {response.text}"
    assert response.headers["content-type"] == "application/json"
    assert response.json() == expected, ref


@pytest.mark.parametrize("ref", ["RES_010", "RES_110", "RES_210"])
def test_additional_information_on_account_is_accepted(client: TestClient, ref: str) -> None:
    party = {"name": "John Smith"} if ref != "RES_210" else org(lei=LEI)
    iban = IBAN_PERSON if ref == "RES_010" else IBAN_COMPANY
    if ref == "RES_110":
        party = {"name": "Corporation ABC SA"}
    response = post(client, body(party, iban, unstructuredRemittanceInformation=["sub-account 7"]))
    assert response.status_code == 200
    assert set(response.json().values()) == {"MTCH"}


def test_response_headers(client: TestClient) -> None:
    response = post(client, body())
    assert response.headers["X-Request-ID"] == REQUEST_ID
    stamp = response.headers["X-Response-Timestamp"]
    assert TIMESTAMP_PATTERN.fullmatch(stamp), stamp  # no trailing zeroes (4.2.9)


def test_error_responses_carry_vop_headers(client: TestClient) -> None:
    response = post(client, body(iban="nope"))
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert TIMESTAMP_PATTERN.fullmatch(response.headers["X-Response-Timestamp"])


def test_close_match_on_greek_account_is_shown_in_sepa_latin(client: TestClient) -> None:
    response = post(client, body({"name": "Yorgos Papadopoulos"}, IBAN_GREEK))
    assert response.json() == {"partyNameMatch": "CMTC", "matchedName": "Giorgos Papadopoulos"}


def test_cross_script_exact_match(client: TestClient) -> None:
    response = post(client, body({"name": "Giorgos Papadopoulos"}, IBAN_GREEK))
    assert response.json() == {"partyNameMatch": "MTCH"}


def test_close_match_that_cannot_be_shown_in_latin_is_not_possible(client: TestClient) -> None:
    response = post(client, body({"name": "Mohammed Ali"}, IBAN_ARABIC))
    assert response.json() == {"partyNameMatch": "NOAP"}


def test_original_script_matched_name_when_latin_is_disabled() -> None:
    app = create_app(Settings(latin_matched_name=False), DIRECTORY)
    with TestClient(app) as client:
        response = post(client, body({"name": "Mohammed Ali"}, IBAN_ARABIC))
    assert response.json() == {"partyNameMatch": "CMTC", "matchedName": "محمد علي"}


# --- negative cases on the responding side (EPC139-25 section 3.2) -------------


def test_rsr_001_missing_request_id(client: TestClient) -> None:
    assert_error(post(client, body(), **{"X-Request-ID": None}), 400, "FORMAT_ERROR")


def test_rsr_002_missing_iban(client: TestClient) -> None:
    assert_error(post(client, body(iban=None)), 400, "FORMAT_ERROR")


def test_rsr_003_missing_name_and_identification(client: TestClient) -> None:
    assert_error(post(client, body({})), 400, "FORMAT_ERROR")


@pytest.mark.parametrize(
    ("ref", "generic"),
    [
        ("RSR_004", {"schemeNameCode": "TXID"}),
        ("RSR_005", {"schemeNameProprietary": "internal"}),
        ("RSR_006", {"issuer": "someone"}),
    ],
)
def test_rsr_004_006_missing_identification(
    client: TestClient, ref: str, generic: dict[str, str]
) -> None:
    assert_error(post(client, body(org(others=[generic]), IBAN_COMPANY)), 400, "FORMAT_ERROR")


@pytest.mark.parametrize("agent", ["partyAgent", "requestingAgent"])
def test_rsr_007_008_missing_bicfi(client: TestClient, agent: str) -> None:
    payload = body()
    payload[agent] = {"financialInstitutionId": {}}
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


def test_rsr_009_missing_timestamp(client: TestClient) -> None:
    assert_error(post(client, body(), **{"X-Request-Timestamp": None}), 400, "TIMESTAMP_INVALID")


def test_rsr_010_invalid_iban(client: TestClient) -> None:
    assert_error(post(client, body(iban="BE68 5390 0754")), 400, "FORMAT_ERROR")


@pytest.mark.parametrize("agent", ["partyAgent", "requestingAgent"])
def test_rsr_011_012_invalid_bicfi(client: TestClient, agent: str) -> None:
    payload = body()
    payload[agent] = {"financialInstitutionId": {"bicfi": "abc-def"}}
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


def test_rsr_013_invalid_request_id(client: TestClient) -> None:
    assert_error(post(client, body(), **{"X-Request-ID": "not-a-uuid"}), 400, "FORMAT_ERROR")


def test_rsr_014_name_too_long(client: TestClient) -> None:
    assert_error(post(client, body({"name": "A" * 141})), 400, "FORMAT_ERROR")


def test_rsr_015_invalid_lei(client: TestClient) -> None:
    assert_error(post(client, body(org(lei="TOO-SHORT"), IBAN_COMPANY)), 400, "FORMAT_ERROR")


def test_rsr_016_invalid_payee_bic(client: TestClient) -> None:
    assert_error(post(client, body(org(anyBIC="nope"), IBAN_COMPANY)), 400, "FORMAT_ERROR")


@pytest.mark.parametrize(
    ("ref", "generic"),
    [
        ("RSR_017", {"identification": "X" * 257, "schemeNameCode": "TXID"}),
        ("RSR_018", {"identification": "X1", "schemeNameCode": "ZZZZ"}),
        ("RSR_019", {"identification": "X1", "schemeNameProprietary": "P" * 36}),
        ("RSR_020", {"identification": "X1", "schemeNameCode": "TXID", "issuer": "I" * 36}),
    ],
)
def test_rsr_017_020_invalid_generic_identification(
    client: TestClient, ref: str, generic: dict[str, str]
) -> None:
    assert_error(post(client, body(org(others=[generic]), IBAN_COMPANY)), 400, "FORMAT_ERROR")


def test_rsr_021_remittance_information_too_long(client: TestClient) -> None:
    payload = body(unstructuredRemittanceInformation=["x" * 141])
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


@pytest.mark.parametrize(
    ("ref", "stamp"),
    [
        ("RSR_022", "12/08/2024 15:19"),
        ("RSR_023", format_timestamp(datetime.now(UTC) - timedelta(days=1))),
        ("RSR_024", format_timestamp(datetime.now(UTC) + timedelta(hours=1))),
        ("RSR_041", "2025-07-10T14:36:25.460Z"),
    ],
)
def test_rsr_022_024_041_invalid_timestamps(client: TestClient, ref: str, stamp: str) -> None:
    assert_error(post(client, body(), **{"X-Request-Timestamp": stamp}), 400, "TIMESTAMP_INVALID")


@pytest.mark.parametrize(
    ("ref", "party"),
    [
        ("RSR_025", {"name": "John Smith", **org(lei=LEI)}),
        ("RSR_026", {"name": "John Smith", **org(anyBIC="CORPDEFFXXX")}),
        ("RSR_027", {"name": "John Smith", **org(others=[TXID])}),
        ("RSR_028", org(lei=LEI, anyBIC="CORPDEFFXXX")),
        ("RSR_029", org(anyBIC="CORPDEFFXXX", others=[TXID])),
        ("RSR_030", org(lei=LEI, others=[TXID])),
        ("RSR_031", org(others=[{**TXID, "schemeNameProprietary": "p"}])),
    ],
)  # fmt: skip
def test_rsr_025_031_mutually_exclusive_fields(
    client: TestClient, ref: str, party: dict[str, Any]
) -> None:
    assert_error(post(client, body(party, IBAN_COMPANY)), 400, "FORMAT_ERROR")


def test_rsr_032_unknown_requester() -> None:
    app = create_app(Settings(allowed_requesting_bics=frozenset({"OTHRBEBBXXX"})), DIRECTORY)
    with TestClient(app) as client:
        assert_error(post(client, body()), 401, "CLIENT_INVALID")


def test_rsr_035_certificate_does_not_match_bic() -> None:
    app = create_app(Settings(client_bic_header="X-Client-BIC"), DIRECTORY)
    with TestClient(app) as client:
        assert_error(
            post(client, body(), **{"X-Client-BIC": "OTHRBEBBXXX"}), 401, "CLIENT_INCONSISTENT"
        )
        assert post(client, body(), **{"X-Client-BIC": REQUESTER}).status_code == 200


def test_rsr_036_malformed_request(client: TestClient) -> None:
    response = client.post(VOP_PATH, content=b'{"party": ', headers=headers())
    assert_error(response, 400, "FORMAT_ERROR")


def test_rsr_036_non_utf8_request(client: TestClient) -> None:
    response = client.post(VOP_PATH, content=b"\xff\xfe", headers=headers())
    assert_error(response, 400, "FORMAT_ERROR")


def test_rsr_037_unrecognized_field(client: TestClient) -> None:
    assert_error(post(client, body(surprise=True)), 400, "FORMAT_ERROR")
    nested = body()
    nested["partyAccount"]["bban"] = "123"
    response = post(client, nested)
    assert_error(response, 400, "FORMAT_ERROR")
    assert response.json()["instance"] == "/partyAccount/bban"


def test_rsr_038_invalid_content_type(client: TestClient) -> None:
    assert_error(post(client, body(), **{"Content-Type": "text/plain"}), 400, "FORMAT_ERROR")


def test_rsr_039_invalid_accept(client: TestClient) -> None:
    assert_error(post(client, body(), Accept="text/html"), 400, "FORMAT_ERROR")
    assert post(client, body(), Accept="application/json; q=0.9, */*").status_code == 200


def test_rsr_040_duplicated_remittance_information(client: TestClient) -> None:
    payload = body(unstructuredRemittanceInformation=["one", "two"])
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


def test_rsr_042_two_digit_milliseconds_are_accepted(client: TestClient) -> None:
    stamp = format_timestamp(datetime.now(UTC).replace(microsecond=460_000))
    assert stamp.endswith(".46Z")
    response = post(client, body(), **{"X-Request-Timestamp": stamp})
    assert response.json() == {"partyNameMatch": "MTCH"}


@pytest.mark.parametrize(
    ("ref", "where"),
    [("RSR_043", "partyAgent"), ("RSR_044", "requestingAgent"), ("RSR_045", "payee")],
)
def test_rsr_043_045_bic8_is_rejected(client: TestClient, ref: str, where: str) -> None:
    payload = body(org(anyBIC="CORPDEFF"), IBAN_COMPANY) if where == "payee" else body()
    if where != "payee":
        payload[where] = {"financialInstitutionId": {"bicfi": "ABCDBEBB"}}
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


def test_rsr_046_empty_remittance_information(client: TestClient) -> None:
    assert_error(post(client, body(unstructuredRemittanceInformation=[""])), 400, "FORMAT_ERROR")
    assert_error(post(client, body(unstructuredRemittanceInformation=[])), 400, "FORMAT_ERROR")


def test_rsr_047_non_latin_remittance_information(client: TestClient) -> None:
    payload = body(unstructuredRemittanceInformation=["Λογαριασμός 7"])
    response = post(client, payload)
    assert_error(response, 400, "FORMAT_ERROR")
    assert response.json()["instance"] == "/unstructuredRemittanceInformation/0"


def test_rsr_048_non_latin_name(client: TestClient) -> None:
    response = post(client, body({"name": "Γιώργος Παπαδόπουλος"}, IBAN_GREEK))
    assert_error(response, 400, "FORMAT_ERROR")
    assert response.json()["instance"] == "/party/name"


def test_latin_diacritics_are_accepted_by_default(client: TestClient) -> None:
    assert post(client, body({"name": "Jöhn Smíth"})).status_code == 200


def test_sepa_basic_charset_rejects_diacritics() -> None:
    with TestClient(create_app(Settings(request_charset="sepa-basic"), DIRECTORY)) as client:
        assert_error(post(client, body({"name": "Jöhn Smith"})), 400, "FORMAT_ERROR")


@pytest.mark.parametrize("ref", ["RSR_049", "RSR_050"])
def test_rsr_049_050_leading_whitespace(client: TestClient, ref: str) -> None:
    payload = (
        body(unstructuredRemittanceInformation=["  sub-account"])
        if ref == "RSR_049"
        else body({"name": "  John Smith"})
    )
    assert_error(post(client, payload), 400, "FORMAT_ERROR")


# --- operations ----------------------------------------------------------------


def test_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post(VOP_PATH, content=b" " * 20_000, headers=headers())
    assert_error(response, 400, "FORMAT_ERROR")
    assert "exceeds" in response.json()["detail"]


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "version": "0.3.0",
        "policy": "epc-default@2",
        "verification_of_payee": True,
        "match_endpoint": False,
    }


def test_openapi_documents_the_vop_request(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert VOP_PATH in spec["paths"]
    assert "VopRequest" in spec["components"]["schemas"]
    assert "partyAccount" in spec["components"]["schemas"]["VopRequest"]["properties"]


def test_docs_can_be_disabled() -> None:
    with TestClient(create_app(Settings(docs=False), DIRECTORY)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_without_directory_only_matching_is_served() -> None:
    with TestClient(create_app(Settings())) as client:
        assert client.post(VOP_PATH, json=body(), headers=headers()).status_code == 404
        assert client.get("/health").json()["verification_of_payee"] is False


def test_directory_from_settings(tmp_path: Path) -> None:
    accounts = tmp_path / "accounts.json"
    accounts.write_text('{"BE68539007547034": {"names": ["John Smith"]}}')
    with TestClient(create_app(Settings(directory=f"json:{accounts}"))) as client:
        assert post(client, body()).json() == {"partyNameMatch": "MTCH"}


def test_logs_never_contain_names_or_ibans(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="nameproof.service")
    post(client, body({"name": "J. Smith"}))
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "verification partyNameMatch=CMTC" in logged
    assert "POST /vop/v1/payee-verifications 200" in logged
    assert "Smith" not in logged
    assert IBAN_PERSON not in logged


# --- /v1/match (opt-in) -------------------------------------------------------------


@pytest.fixture
def match_client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(match_endpoint=True))) as test_client:
        yield test_client


def test_match_endpoint_is_off_by_default(client: TestClient) -> None:
    response = client.post("/v1/match", json={"provided": "x", "accountNames": ["y"]})
    assert response.status_code == 404


def test_match_endpoint(match_client: TestClient) -> None:
    response = match_client.post(
        "/v1/match", json={"provided": "Jon Smyth", "accountNames": ["John Smith"]}
    )
    assert response.status_code == 200
    verdict = response.json()
    assert verdict["result"] == "CLOSE_MATCH"
    assert verdict["suggested_name"] == "John Smith"
    assert "MatchRequest" in match_client.get("/openapi.json").json()["components"]["schemas"]


def test_match_endpoint_validation(match_client: TestClient) -> None:
    response = match_client.post("/v1/match", json={"provided": "x", "accountNames": []})
    assert_error(response, 400, "FORMAT_ERROR")
    assert response.json()["instance"] == "/accountNames"
    unknown = match_client.post(
        "/v1/match", json={"provided": "x", "accountNames": ["y"], "policy": "nope@1"}
    )
    assert_error(unknown, 400, "FORMAT_ERROR")


def test_match_endpoint_errors_are_problem_json(match_client: TestClient) -> None:
    # Review finding 13: oversized and malformed bodies used FastAPI's own format.
    assert_error(match_client.post("/v1/match", content=b"{" * 20_000), 400, "FORMAT_ERROR")
    assert_error(match_client.post("/v1/match", content=b"{nope"), 400, "FORMAT_ERROR")


# --- review findings 11, 12, 15 -------------------------------------------------------


def test_internal_errors_carry_vop_headers() -> None:
    class Broken:
        def lookup(self, iban: str) -> AccountRecord | None:
            raise RuntimeError(iban)

    with TestClient(create_app(Settings(), Broken()), raise_server_exceptions=False) as client:
        response = post(client, body())
    assert_error(response, 500, "INTERNAL_ERROR")
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert TIMESTAMP_PATTERN.fullmatch(response.headers["X-Response-Timestamp"])
    assert IBAN_PERSON not in response.text


@pytest.mark.parametrize(
    "request_id",
    [f"urn:uuid:{REQUEST_ID}", "{" + REQUEST_ID + "}", REQUEST_ID.replace("-", "")],
)
def test_non_canonical_request_ids_are_rejected(client: TestClient, request_id: str) -> None:
    assert_error(post(client, body(), **{"X-Request-ID": request_id}), 400, "FORMAT_ERROR")


def test_invalid_request_ids_are_never_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "<script>" + "x" * 5000})
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["X-Request-ID"])


def test_holder_name_cap_is_validated() -> None:
    with pytest.raises(ValueError, match="max_holder_names"):
        Settings(max_holder_names=30)


def test_pathological_request_stays_fast(client: TestClient) -> None:
    worst = ("Ευάγγελος Αντετοκούνμπο Παπαδόπουλος Владимир Зеленський " * 3)[:140]
    directory = InMemoryDirectory({IBAN_PERSON: AccountRecord((worst,) * 30)})
    with TestClient(create_app(Settings(), directory)) as slow_client:
        start = datetime.now(UTC)
        response = post(slow_client, body({"name": "Evangelos Antetokounmpo Papadopoulos"}))
        assert response.status_code == 200
        assert datetime.now(UTC) - start < timedelta(seconds=2)


def test_timestamp_pattern_matches_spec_examples() -> None:
    valid = ["2025-07-10T14:36:25.465Z", "2025-07-10T14:36:25.46Z", "2025-07-10T14:36:25.4Z",
             "2025-07-10T14:36:25Z", "2025-07-10T16:36:25.123+02:00"]  # fmt: skip
    invalid = ["2025-07-10T14:36:25.460Z", "2025-07-10T14:36:25.400Z", "2025-07-10T14:36:25.000Z"]
    assert all(TIMESTAMP_PATTERN.fullmatch(v) for v in valid)
    assert not any(TIMESTAMP_PATTERN.fullmatch(v) for v in invalid)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,3})?Z", now())
