import json
import random
from pathlib import Path

import pytest

import build_dataset as b


@pytest.mark.parametrize(
    ("en", "native", "script", "kind", "keep"),
    [
        ("Maria Callas", "Μαρία Κάλλας", "GREEK", "person", True),
        ("George I of Greece", "Γεώργιος Α΄ της Ελλάδας", "GREEK", "person", False),
        ("Elder Paisios", "Γέροντας Παΐσιος", "GREEK", "person", False),
        ("Madonna", "Μαντόνα", "GREEK", "person", False),  # one-word person names
        ("Maria Callas", "Maria Callas", "GREEK", "person", False),  # wrong script
        ("LARCO", "ΛΑΡΚΟ", "GREEK", "company", True),
        ("Hellenic (Group)", "Ελληνική", "GREEK", "company", False),
    ],
)
def test_is_clean_name(en: str, native: str, script: str, kind: str, keep: bool) -> None:
    assert b.is_clean_name(en, native, script, kind=kind) is keep


def test_entities_dedupe_filter_and_sort() -> None:
    source = b.SOURCES[0]
    rows = [
        {"qid": "Q30", "en": "Maria Callas", "native": "Μαρία Κάλλας"},
        {"qid": "Q30", "en": "Maria Callas", "native": "Μαρία Κάλλας"},
        {"qid": "Q4", "en": "Irene Papas", "native": "Ειρήνη Παπά"},
        {"qid": "Q5", "en": "Pope Paul", "native": "Πάπας Παύλος"},
    ]
    assert [e.qid for e in b.entities(rows, source)] == ["Q4", "Q30"]


def test_variations() -> None:
    rng = random.Random(1)
    assert b.strip_diacritics("Lech Wałęsa") == "Lech Wałesa"  # ł has no decomposition
    assert b.initial("Maria Callas") == "M. Callas"
    assert b.initial("Madonna") is None
    assert b.reordered("Maria Callas") == "Callas Maria"
    assert b.reordered("Madonna") is None
    assert b.dropped_middle("Anna Maria Kowalska") == "Anna Kowalska"
    assert b.dropped_middle("Anna Kowalska") is None
    assert b.typo("Jo Li", rng) is None
    mutated = b.typo("Maria Callas", rng)
    assert mutated is not None
    assert mutated != "Maria Callas"
    assert mutated.split()[1][0] == "C"  # first letters are never changed
    assert len(mutated) == len("Maria Callas")


def _pool(count: int) -> list[b.Entity]:
    given = ["Anna", "Maria", "Elena", "Nikos", "Petros", "Ioanna"]
    surnames = ["Papas", "Kallas", "Vlachou"]
    return [
        b.Entity(f"Q{i}", f"{given[i % 6]} {surnames[i % 3]}", f"Νάμε{i} Σουρ{i % 3}")
        for i in range(count)
    ]


def test_build_slice_is_deterministic_and_labelled() -> None:
    source = b.SOURCES[0]
    pool = _pool(40)
    first, second = b.build_slice(source, pool), b.build_slice(source, pool)
    assert first == second
    labels = {case["label"] for case in first}
    assert labels == {"same", "different"}
    assert all(case["slice"] == "greek" and case["id"].startswith("greek-") for case in first)
    different = [case for case in first if case["label"] == "different"]
    assert len(different) <= b.NEGATIVES_PER_SLICE
    assert any(case["variation"] == "same_surname" for case in different)


def test_latin_slice_variations() -> None:
    polish = next(source for source in b.SOURCES if source.slice == "polish")
    entity = b.Entity("Q1", "Lech Walesa", "Lech Wałęsa")
    variations = {case["variation"] for case in b.build_slice(polish, [entity])}
    assert {"english_label", "ascii_typed", "uppercase", "reordered"} <= variations


def test_fetch_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(b, "CACHE", tmp_path)
    rows = [{"qid": "Q1", "en": "Maria Callas", "native": "Μαρία Κάλλας"}]
    (tmp_path / "greek.json").write_text(json.dumps(rows, ensure_ascii=False))
    assert b.fetch(b.SOURCES[0], refresh=False) == rows


def test_queries_mention_language_and_countries() -> None:
    person = b._query(b.SOURCES[0])
    assert 'LANG(?native) = "el"' in person
    assert "wd:Q41 wd:Q229" in person
    assert "wdt:P570" in person  # deceased people only
    company = b._query(next(s for s in b.SOURCES if s.kind == "company"))
    assert "wdt:P570" not in company
