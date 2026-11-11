import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from nameproof.service import (
    AccountRecord,
    InMemoryDirectory,
    Settings,
    create_app,
    json_directory,
    load_directory,
)
from nameproof.service.formats import (
    format_timestamp,
    in_charset,
    parse_timestamp,
    to_sepa_latin,
)


def test_format_timestamp_drops_trailing_zeroes() -> None:
    base = datetime(2025, 7, 10, 14, 36, 25, tzinfo=UTC)
    assert format_timestamp(base.replace(microsecond=465_000)) == "2025-07-10T14:36:25.465Z"
    assert format_timestamp(base.replace(microsecond=460_000)) == "2025-07-10T14:36:25.46Z"
    assert format_timestamp(base.replace(microsecond=400_000)) == "2025-07-10T14:36:25.4Z"
    assert format_timestamp(base) == "2025-07-10T14:36:25Z"
    plus_two = base.astimezone(timezone(timedelta(hours=2)))
    assert format_timestamp(plus_two) == "2025-07-10T14:36:25Z"  # always UTC


def test_parse_timestamp() -> None:
    assert parse_timestamp("2025-07-10T16:36:25.123+02:00") == datetime(
        2025, 7, 10, 14, 36, 25, 123_000, tzinfo=UTC
    )
    assert parse_timestamp("2025-07-10T14:36:25.460Z") is None  # trailing zero
    assert parse_timestamp("2025-13-40T14:36:25Z") is None  # right shape, impossible date


@pytest.mark.parametrize(
    ("name", "latin"),
    [
        ("Γιώργος Παπαδόπουλος", "Giorgos Papadopoulos"),
        ("ΓΙΏΡΓΟΣ ΠΑΠΑΔΌΠΟΥΛΟΣ", "GIORGOS PAPADOPOULOS"),
        ("Енерго ЕООД", "Energo Eood"),
        ("Lech Wałęsa", "Lech Walesa"),
        ("Hans-Joachim Müller", "Hans-Joachim Muller"),
        ("Smith & Sons <Ltd>", "Smith + Sons .Ltd."),
        ("O’Brien", "O Brien"),
        ("محمد علي", None),
        ("王小明", None),
    ],
)
def test_to_sepa_latin(name: str, latin: str | None) -> None:
    assert to_sepa_latin(name) == latin


def test_in_charset() -> None:
    assert in_charset("John Smith-Jones (Jr.)", "sepa-basic")
    assert not in_charset("José", "sepa-basic")
    assert in_charset("José Wałęsa", "latin")
    assert not in_charset("Γιώργος", "latin")
    assert not in_charset("John_Smith", "latin")
    assert in_charset("Γιώργος", "any")


def test_json_directory(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    path.write_text(
        json.dumps({"be68 5390 0754 7034": {"names": ["John Smith"], "identifiers": {"lei": "X"}}})
    )
    directory = json_directory(path)
    record = directory.lookup("BE68539007547034")
    assert record == AccountRecord(("John Smith",), {"LEI": "X"})
    assert directory.lookup("DE89370400440532013000") is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[]", "keyed by IBAN"),
        ('{"X": "John"}', "expected an object"),
        ('{"X": {"names": []}}', "non-empty list"),
        ('{"X": {"names": ["A"], "identifiers": {"LEI": 1}}}', "map strings"),
    ],
)
def test_json_directory_rejects_bad_files(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        json_directory(path)


def test_load_directory_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bank_plugin.py").write_text(
        "from nameproof.service import AccountRecord, InMemoryDirectory\n"
        "def make():\n"
        "    return InMemoryDirectory({'BE68539007547034': AccountRecord(('John Smith',))})\n"
        "def wrong():\n"
        "    return object()\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    directory = load_directory("plugin:bank_plugin:make")
    assert isinstance(directory, InMemoryDirectory)
    with pytest.raises(TypeError, match="AccountDirectory"):
        load_directory("plugin:bank_plugin:wrong")


@pytest.mark.parametrize("spec", ["", "json:", "ldap:server", "plugin:no_factory"])
def test_load_directory_rejects_bad_specs(spec: str) -> None:
    with pytest.raises(ValueError, match="invalid directory spec"):
        load_directory(spec)


def test_settings_from_env() -> None:
    settings = Settings.from_env(
        {
            "NAMEPROOF_DIRECTORY": "json:/data/a.json",
            "NAMEPROOF_ALLOWED_REQUESTING_BICS": "abcdbebbxxx, OTHRBEBBXXX,",
            "NAMEPROOF_CLIENT_BIC_HEADER": "X-Client-BIC",
            "NAMEPROOF_MAX_REQUEST_AGE_S": "60",
            "NAMEPROOF_MAX_BODY_BYTES": "4096",
            "NAMEPROOF_LATIN_MATCHED_NAME": "no",
            "NAMEPROOF_REQUEST_CHARSET": "sepa-basic",
            "NAMEPROOF_DOCS": "0",
            "NAMEPROOF_MATCH_ENDPOINT": "1",
        }
    )
    assert settings.directory == "json:/data/a.json"
    assert settings.allowed_requesting_bics == {"ABCDBEBBXXX", "OTHRBEBBXXX"}
    assert settings.client_bic_header == "X-Client-BIC"
    assert settings.max_request_age_s == 60.0
    assert settings.max_body_bytes == 4096
    assert settings.latin_matched_name is False
    assert settings.request_charset == "sepa-basic"
    assert settings.docs is False
    assert settings.match_endpoint is True
    assert Settings.from_env({}) == Settings()


def test_settings_reject_unknown_charset() -> None:
    with pytest.raises(ValueError, match="request_charset"):
        Settings(request_charset="ascii")


def test_lazy_create_app() -> None:
    app = create_app(Settings(), InMemoryDirectory({}))
    assert app.title == "nameproof"  # type: ignore[attr-defined]
