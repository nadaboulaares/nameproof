import json
import subprocess
import sys

import pytest

import nameproof
from nameproof.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"nameproof {nameproof.__version__}"


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: nameproof" in capsys.readouterr().out


def test_module_is_importable_in_fresh_interpreter() -> None:
    out = subprocess.run(
        [sys.executable, "-c", "import nameproof; print(nameproof.__version__)"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == nameproof.__version__


def test_match_prints_human_readable_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["match", "Jon Smyth", "Peter Brown", "John Smith"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("CLOSE_MATCH  score=")
    assert "suggested name: John Smith" in out
    assert "why: fuzzy_token" in out


def test_match_exact_has_no_extra_lines(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["match", "John Smith", "John Smith"]) == 0
    assert capsys.readouterr().out.splitlines() == ["MATCH  score=1.0000  policy=epc-default@1"]


def test_match_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["match", "--json", "Anna Müller", "Anna Mueller"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "MATCH"
    assert payload["suggested_name"] is None
    assert payload["policy_version"] == "epc-default@1"


def test_match_unknown_policy_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["match", "--policy", "nope@1", "A B", "A B"]) == 2
    assert "unknown policy" in capsys.readouterr().err
