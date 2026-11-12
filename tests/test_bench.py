import json
from pathlib import Path

import pytest

from nameproof import MatchResult
from nameproof.bench import (
    SYSTEMS,
    Case,
    Tally,
    exact_baseline,
    levenshtein_baseline,
    load_cases,
    render_markdown,
    run,
    select_systems,
    to_dict,
    token_sort_baseline,
)
from nameproof.cli import main

CASES = [
    {"id": "g-1", "slice": "greek", "variation": "native_script", "label": "same",
     "provided": "Giorgos Papadopoulos", "account": "Γιώργος Παπαδόπουλος"},
    {"id": "g-2", "slice": "greek", "variation": "different_person", "label": "different",
     "provided": "Nikos Kazantzakis", "account": "Γιώργος Παπαδόπουλος"},
    {"id": "p-1", "slice": "polish", "variation": "ascii_typed", "label": "same",
     "provided": "Lech Walesa", "account": "Lech Wałęsa"},
    {"id": "p-2", "slice": "polish", "variation": "typo", "label": "same",
     "provided": "Lech Walexa", "account": "Lech Wałęsa"},
]  # fmt: skip


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "bench.jsonl"
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES) + "\n\n")
    return path


def test_load_cases(dataset: Path) -> None:
    cases = load_cases(dataset)
    assert [case.id for case in cases] == ["g-1", "g-2", "p-1", "p-2"]
    assert cases[0] == Case(
        "g-1", "greek", "native_script", "same", "Giorgos Papadopoulos", "Γιώργος Παπαδόπουλος"
    )


def test_load_cases_rejects_bad_records(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    missing.write_text(json.dumps({"id": "x"}) + "\n")
    with pytest.raises(ValueError, match="missing field"):
        load_cases(missing)
    bad_label = tmp_path / "label.jsonl"
    bad_label.write_text(json.dumps({**CASES[0], "label": "maybe"}) + "\n")
    with pytest.raises(ValueError, match="label must be"):
        load_cases(bad_label)


def test_baselines() -> None:
    assert exact_baseline("John  SMITH", "john smith") is MatchResult.MATCH
    assert exact_baseline("Jon Smith", "John Smith") is MatchResult.NO_MATCH
    assert levenshtein_baseline("John Smith", "John Smith") is MatchResult.MATCH
    assert levenshtein_baseline("John Smyth", "John Smith") is MatchResult.CLOSE_MATCH
    assert levenshtein_baseline("Peter Brown", "John Smith") is MatchResult.NO_MATCH
    assert token_sort_baseline("Garcia Jose", "José García") is MatchResult.MATCH
    assert token_sort_baseline("Walesa Lech", "Lech Wałęsa") is MatchResult.CLOSE_MATCH  # ł
    # No baseline can read another script.
    assert token_sort_baseline("Giorgos", "Γιώργος") is MatchResult.NO_MATCH


def test_tally_rates() -> None:
    tally = Tally()
    assert tally.rate(MatchResult.MATCH) == 0.0
    tally.add(MatchResult.MATCH)
    tally.add(MatchResult.NO_MATCH)
    assert tally.total == 2
    assert tally.rate(MatchResult.MATCH) == 0.5
    assert tally.rate(MatchResult.MATCH, MatchResult.NO_MATCH) == 1.0


def test_run_and_report(dataset: Path) -> None:
    report = run(load_cases(dataset))
    assert report.systems == tuple(SYSTEMS)
    assert report.slices == ("greek", "polish")
    greek_same = report.tally("nameproof", "same", "greek")
    assert greek_same.counts[MatchResult.MATCH] == 1
    assert report.tally("exact", "same", "greek").counts[MatchResult.NO_MATCH] == 1
    assert report.tally("nameproof", "same").total == 3  # summed over slices
    assert report.tally("nameproof", "same", "nowhere").total == 0
    assert len(report.latencies_ms) == len(CASES)
    assert 0 < report.latency(0.5) <= report.latency(0.95)

    markdown = render_markdown(report)
    assert "| greek | 0.0% | 100.0% | 100.0% | 100.0% |" in markdown  # wrongly rejected
    assert "**all**" in markdown
    assert "shown the other's name** (CLOSE_MATCH" in markdown
    assert "| same | typo | 1 |" in markdown

    data = to_dict(report)
    assert data["nameproof"]["same"]["all"]["n"] == 3  # type: ignore[index]
    assert data["nameproof"]["different"]["greek"]["MATCH"] == 0.0  # type: ignore[index]
    latency = data["latency_ms"]
    assert isinstance(latency, dict)
    assert set(latency) == {"p50", "p95"}


def test_empty_report_latency() -> None:
    assert run([], {}).latency(0.5) == 0.0


def test_select_systems() -> None:
    assert list(select_systems(["exact", "nameproof"])) == ["exact", "nameproof"]
    with pytest.raises(ValueError, match="unknown system"):
        select_systems(["nope"])


def test_cli_bench_markdown(dataset: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bench", str(dataset), "--systems", "nameproof, exact"]) == 0
    out = capsys.readouterr().out
    assert "| slice | nameproof | exact |" in out
    assert "nameproof latency" in out


def test_cli_bench_json(dataset: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bench", str(dataset), "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {*SYSTEMS, "latency_ms"}


def test_cli_bench_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bench", str(tmp_path / "missing.jsonl")]) == 2
    assert main(["bench", str(tmp_path), "--systems", "nope"]) == 2
    assert "unknown system" in capsys.readouterr().err
