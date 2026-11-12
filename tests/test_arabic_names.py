import re
from collections import Counter
from importlib.resources import files

import pytest

from nameproof import MatchResult, load_policy, match
from nameproof.arabic_names import (
    arabic_key,
    arabic_spellings,
    different_known,
    different_names,
    known_names,
    latin_key,
    same_name,
)
from nameproof.dedupe import find_duplicates, word_keys
from nameproof.translit import latin_skeleton, latin_skeleton_variants

M, C, N = MatchResult.MATCH, MatchResult.CLOSE_MATCH, MatchResult.NO_MATCH


def _entries() -> list[tuple[str, list[str]]]:
    text = (files("nameproof") / "data" / "arabic_given_names.tsv").read_text(encoding="utf-8")
    return [
        (arabic, spellings.split(","))
        for arabic, spellings in (
            line.split("\t") for line in text.splitlines() if line and not line.startswith("#")
        )
    ]


def test_the_name_list_is_well_formed() -> None:
    entries = _entries()
    assert len(entries) > 150
    seen: Counter[str] = Counter()
    for arabic, spellings in entries:
        assert re.fullmatch(r"[ء-ي ]+", arabic), arabic
        assert len(spellings) == len(set(spellings)), arabic
        for spelling in spellings:
            assert re.fullmatch(r"[a-z]+", spelling), spelling
        seen.update(spellings)
    assert len({arabic_key(arabic) for arabic, _ in entries}) == len(entries)
    # Spellings shared by two names are deliberate and few.
    assert {spelling for spelling, count in seen.items() if count > 1} == {"hamid", "mhamed"}


@pytest.mark.parametrize(
    ("text", "key"),
    [("أحمد", "احمد"), ("الهادي", "هادي"), ("عبد القادر", "عبدالقادر"), ("فاطِمة", "فاطمه")],
)
def test_arabic_key_folds_spelling_variants(text: str, key: str) -> None:
    assert arabic_key(text) == key


def test_latin_key_and_lookups() -> None:
    assert latin_key("Abdel-Kader") == "abdelkader"
    assert latin_key("Saïd") == "said"
    assert arabic_spellings("HOCINE") == {"حسين"}
    assert arabic_spellings("Smith") == frozenset()
    assert arabic_spellings("hamid") == {"حامد", "حميد"}


def test_same_and_different_known_names() -> None:
    assert same_name("Hussein", "Hocine")
    assert same_name("Youssef", "Yusuf")
    assert not same_name("Mohamed", "mohamed")  # identical is not a variant
    assert not same_name("Mohamed", "Smith")
    assert different_known("Mohammed", "Mahmoud")
    assert different_known("محمد", "محمود")
    assert different_known("Samir", "Samira")
    assert not different_known("Hamid", "Hamed")  # both can be حامد
    assert not different_known("Mohamed", "Smith")  # Smith is not on the list


@pytest.mark.parametrize(
    ("left", "right", "different"),
    [
        (["mahmoud", "ali"], ["محمد", "علي"], True),
        (["mohamed", "ali"], ["علي", "محمود"], True),
        (["محمد", "علي"], ["محمود", "علي"], True),
        (["mohamed", "mahmoud"], ["محمد", "محمود"], False),
        (["a", "halim", "ibrahim"], ["أحمد", "حليم"], False),  # "A." may be أحمد
        (["hamid", "merakchi"], ["عبد", "الحميد", "مراكشي"], False),  # short form
        (["khalid", "abdel", "nasser"], ["خالد", "عبد", "الناصر"], False),  # compound
        (["mohamed", "ali"], ["محمد", "علي", "حسن"], False),  # extra name on one side only
        (["john", "smith"], ["جون", "سميث"], False),  # not on the list
    ],
)
def test_different_names(left: list[str], right: list[str], different: bool) -> None:
    assert different_names(left, right) is different
    assert different_names(right, left) is different


def test_known_names_span_several_words() -> None:
    assert known_names(["abd", "el", "kader", "ali"]) == [{"عبدالقادر"}, {"علي"}]
    assert known_names(["نور", "الدين"]) == [{"نورالدين"}]


@pytest.mark.parametrize(
    ("provided", "account", "result"),
    [
        # Known names that share a skeleton are told apart.
        ("Mohamed", "محمود", N),
        ("Mahmoud Ali", "محمد علي", N),
        ("Muhammad Taymur", "محمود تيمور", N),
        ("محمد علي", "محمود علي", N),
        ("Mohammed Ali", "Mahmoud Ali", N),
        ("Hassan Ali", "Hussein Ali", N),
        ("Samir Ali", "Samira Ali", N),
        # Known spellings of one name are close (EPC: spellings differ).
        ("Hussein Ali", "Hocine Ali", C),
        ("Mohamed Ali", "Muhammad Ali", C),
        ("Abdelkader Ali", "Abdul Qadir Ali", C),
        # Maghreb and French romanisations of Arabic script.
        ("Hocine Soltani", "حسين سلطاني", C),  # soft c
        ("Larbi Zekkal", "العربي زكال", C),  # glued article
        ("Lotfia Elnadi", "لطفية النادي", C),
        ("Belgacem Ali", "بلقاسم علي", C),  # g for qaf
        ("Mohamed Benguettaf", "محمد بن قطاف", C),
        ("Lakhdar Brahimi", "الأخضر الإبراهيمي", C),  # dropped first vowel
        ("M'hamed Benguettaf", "امحمد بن قطاف", C),
        ("Hamid Salah", "حامد صلاح", C),  # final h is a real consonant
        ("Fatimah Ali", "فاطمة علي", C),  # ...or a silent ta marbuta
        ("Hamid Merakchi", "عبد الحميد مراكشي", C),
        ("Ahmed", "حامد", N),
    ],
)
def test_arabic_matching(provided: str, account: str, result: MatchResult) -> None:
    verdict = match(provided, [account])
    assert verdict.result is result, verdict
    if provided in {"Mohamed", "Mahmoud Ali", "محمد علي"}:
        assert "different_given_name" in verdict.explanation
    if account in {"Hocine Ali", "Muhammad Ali"}:
        assert verdict.explanation == ("known_variant",)


def test_records_policy_accepts_known_variants() -> None:
    records = load_policy("records@1")
    assert records.known_variants_can_match
    assert not load_policy("epc-default@2").known_variants_can_match
    assert match("Mohamed Ali", ["Mohammed Ali"], policy="records@1").result is M
    assert match("Hamid Ali", ["Hamed Ali"], policy="records@1").result is M
    # Arabic script against Latin stays a close match for review.
    assert match("Mohamed Ali", ["محمد علي"], policy="records@1").result is C
    assert match("Mohammed Ali", ["Mahmoud Ali"], policy="records@1").result is N


def test_romanisation_readings() -> None:
    assert latin_skeleton("hocine") == "hsn"
    assert latin_skeleton("salah") == "sl"
    assert latin_skeleton("salah", final_h=True) == "slh"
    assert ("arb", "zkl") in latin_skeleton_variants(("larbi", "zekkal"))
    assert ("bnktf",) in latin_skeleton_variants(("benguettaf",))
    assert ("abrhm",) in latin_skeleton_variants(("brahim",))
    assert latin_skeleton_variants(("ghassan",)) == [("Gsn",)]  # gh is ghayn, not qaf


def test_dedupe_tells_mohamed_from_mahmoud() -> None:
    names = ["Mohamed Ali", "Mohammed Ali", "Muhammad Ali", "محمد علي", "Mahmoud Ali", "محمود علي"]
    report = find_duplicates(names)
    assert [group.members for group in report.groups] == [(0, 1, 2, 3), (4, 5)]
    assert report.policy_version == "records@1"
    assert {"jtf", "ktf"} <= word_keys("guettaf")
