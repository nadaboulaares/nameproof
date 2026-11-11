"""Behaviour of the public ``match`` API on Latin-script names.

All names are synthetic or belong to well-known public figures.
"""

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nameproof import DEFAULT_POLICY, MatchResult, Policy, Reason, load_policy, match
from nameproof._lexicon import CONNECTORS, HONORIFICS, PARTICLES, POSTNOMINALS, SUFFIXES
from nameproof.legal_forms import LEGAL_FORM_WORDS
from nameproof.matcher import MAX_ACCOUNT_NAMES, MAX_NAME_LENGTH

M, C, N, X = (
    MatchResult.MATCH,
    MatchResult.CLOSE_MATCH,
    MatchResult.NO_MATCH,
    MatchResult.NOT_POSSIBLE,
)

CASES = [
    # provided, account, expected result, reasons that must be present
    ("John Smith", "John Smith", M, set()),
    ("john smith", "JOHN  SMITH", M, set()),
    ("Smith John", "John Smith", M, {Reason.TOKEN_REORDER}),
    ("Jose Garcia", "José García", M, {Reason.DIACRITICS_FOLDED}),
    ("Lech Walesa", "Lech Wałęsa", M, {Reason.DIACRITICS_FOLDED}),
    ("Mueller Anna", "Anna Müller", M, {Reason.LETTER_EXPANSION, Reason.TOKEN_REORDER}),
    ("Soeren Kierkegaard", "Søren Kierkegaard", M, {Reason.LETTER_EXPANSION}),
    ("Hans Strasse", "Hans Straße", M, set()),
    ("Dr. John Smith", "John Smith", M, {Reason.TITLE_REMOVED}),
    ("Sean O'Brien", "Sean OBrien", M, set()),
    ("Jean-Pierre Dupont", "Jean Pierre Dupont", M, set()),
    ("Jeanpierre Dupont", "Jean-Pierre Dupont", M, {Reason.COMPOUND_JOINED}),
    ("John Michael Smith", "John Smith", M, {Reason.MISSING_TOKENS}),
    # EPC288-23: last name must be exact, so a dropped particle is a close match.
    ("Ludwig van Beethoven", "Ludwig Beethoven", C, {Reason.PARTICLE_DROPPED}),
    ("Anna Vanderberg", "Anna van der Berg", C, {Reason.PARTICLE_JOINED}),
    ("Mary Smith", "John & Mary Smith", M, {Reason.JOINT_ACCOUNT_HOLDER}),
    ("John Smith", "John and Mary Smith", M, {Reason.SHARED_SURNAME}),
    ("John Smith Jr", "John Smith", M, set()),
    ("Madonna", "Madonna", M, set()),
    # Spelling differences never MATCH: the payer must see the real name.
    ("Jon Smyth", "John Smith", C, {Reason.FUZZY_TOKEN}),
    ("Maria Garcia", "Mario Garcia", C, {Reason.FUZZY_TOKEN}),
    ("Anna Kowalska", "Anna Kowalski", C, {Reason.FUZZY_TOKEN}),
    ("J. Smith", "John Smith", C, {Reason.INITIAL}),
    ("Smith", "John Smith", N, {Reason.SINGLE_TOKEN}),  # a surname alone reveals nothing
    ("John Smith Jr", "John Smith Sr", C, {Reason.SUFFIX_CONFLICT}),
    ("John Adam Bruce Smith", "John Smith", C, {Reason.MISSING_TOKENS}),
    # Different people or companies.
    ("John Smith", "Peter Brown", N, set()),
    ("John Smith", "Mary Smith", N, {Reason.MISMATCHED_TOKEN}),
    ("J. S.", "John Smith", N, {Reason.INITIALS_ONLY}),
    ("Acme", "John Smith", N, set()),
    # Nothing to compare.
    ("", "John Smith", X, {Reason.EMPTY_NAME}),
    ("  !!! ", "John Smith", X, {Reason.EMPTY_NAME}),
    ("John Smith", " - ", X, {Reason.EMPTY_NAME}),
]


@pytest.mark.parametrize(("provided", "account", "expected", "reasons"), CASES)
def test_match_cases(
    provided: str, account: str, expected: MatchResult, reasons: set[Reason]
) -> None:
    verdict = match(provided, [account])
    assert verdict.result is expected, verdict
    assert reasons <= set(verdict.explanation), verdict
    assert verdict.policy_version == DEFAULT_POLICY


def test_close_match_suggests_the_registered_account_name() -> None:
    verdict = match("Jon Smyth", ["Peter Brown", "John Smith"])
    assert verdict.result is C
    assert verdict.suggested_name == "John Smith"


@pytest.mark.parametrize(("provided", "account"), [("John Smith", "John Smith"), ("X Y", "Q Z")])
def test_no_name_is_revealed_outside_close_match(provided: str, account: str) -> None:
    assert match(provided, [account]).suggested_name is None


def test_best_of_several_account_names_wins() -> None:
    verdict = match("Anna Müller", ["Anna Schmidt", "Anna Mueller"])
    assert verdict.result is M


def test_exact_match_scores_one() -> None:
    assert match("John Smith", ["John Smith"]).score == 1.0


def test_initials_can_match_when_policy_allows() -> None:
    lenient = Policy.from_mapping(
        {
            "name": "lenient-initials",
            "version": 1,
            "match_threshold": 0.95,
            "close_threshold": 0.8,
            "missing_token_penalty": 0.05,
            "max_missing_tokens_for_match": 1,
            "initials_can_match": True,
        }
    )
    verdict = match("J. Smith", ["John Smith"], policy=lenient)
    assert verdict.result is M
    assert verdict.policy_version == "lenient-initials@1"


def test_name_longer_than_sepa_limit_is_not_possible() -> None:
    verdict = match("a" * (MAX_NAME_LENGTH + 1), ["John Smith"])
    assert verdict.result is X
    assert verdict.explanation == (Reason.NAME_TOO_LONG,)


def test_single_string_account_names_is_rejected() -> None:
    with pytest.raises(TypeError, match="sequence"):
        match("John Smith", "John Smith")


def test_empty_account_names_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        match("John Smith", [])


def test_too_many_account_names_is_rejected() -> None:
    with pytest.raises(ValueError, match="at most"):
        match("John Smith", ["John Smith"] * (MAX_ACCOUNT_NAMES + 1))


def test_unknown_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown policy"):
        match("John Smith", ["John Smith"], policy="nope@1")


@pytest.mark.parametrize(
    "worst",
    [
        " ".join(["ab", "ba", "aa", "bb"] * 8),
        "Ευάγγελος Αντετοκούνμπο Παπαδόπουλος Владимир Зеленський " * 3,  # most renderings
    ],
)
def test_pathological_input_stays_fast(worst: str) -> None:
    worst = worst[:MAX_NAME_LENGTH]
    accounts = [worst] * MAX_ACCOUNT_NAMES
    start = time.perf_counter()
    match(worst, accounts)
    assert time.perf_counter() - start < 3.0


# --- properties --------------------------------------------------------------

_RESERVED = HONORIFICS | POSTNOMINALS | PARTICLES | CONNECTORS | set(SUFFIXES) | LEGAL_FORM_WORDS
_token = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=4, max_size=10).filter(
    lambda token: token not in _RESERVED
)
_name = st.lists(_token, min_size=1, max_size=4).map(" ".join)


@given(name=_name)
def test_identical_names_always_match(name: str) -> None:
    verdict = match(name, [name])
    assert verdict.result is M
    assert verdict.score == 1.0


@given(left=_name, right=_name)
def test_result_is_symmetric(left: str, right: str) -> None:
    assert match(left, [right]).result is match(right, [left]).result


@settings(max_examples=200)
@given(provided=st.text(max_size=60), account=st.text(max_size=60))
def test_any_text_gives_a_valid_deterministic_verdict(provided: str, account: str) -> None:
    first = match(provided, [account])
    assert 0.0 <= first.score <= 1.0
    assert first == match(provided, [account])
    if first.result is not C:
        assert first.suggested_name is None


def test_default_policy_loads() -> None:
    assert load_policy().id == DEFAULT_POLICY


# --- M2: other scripts and companies -------------------------------------------

SCRIPT_CASES = [
    # Official romanisations: identical output may MATCH.
    ("Giorgos Papadopoulos", "Γιώργος Παπαδόπουλος", M, {Reason.TRANSLITERATED}),
    ("PAPADOPOULOS GEORGIOS", "ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΕΩΡΓΙΟΣ", M, {Reason.TRANSLITERATED}),
    ("Giannis Antetokounmpo", "Γιάννης Αντετοκούνμπο", M, {Reason.TRANSLITERATED}),
    ("Vladimir Putin", "Владимир Путин", M, {Reason.TRANSLITERATED}),
    ("Taras Shevchenko", "Шевченко Тарас", M, {Reason.TOKEN_REORDER}),
    ("Volodymyr Zelenskyi", "Володимир Зеленський", M, {Reason.TRANSLITERATED}),
    ("Boyko Borisov", "Бойко Борисов", M, {Reason.TRANSLITERATED}),
    ("Novak Djokovic", "Новак Ђоковић", M, {Reason.LETTER_EXPANSION}),
    ("Novak Djokovic", "Novak Đoković", M, {Reason.LETTER_EXPANSION}),
    ("Γιώργος Παπαδόπουλος", "ΓΙΏΡΓΟΣ ΠΑΠΑΔΌΠΟΥΛΟΣ", M, set()),
    ("محمد علي", "مُحَمَّد علي", M, {Reason.DIACRITICS_FOLDED}),
    ("王小明", "王小明", M, set()),
    # Informal spellings and Arabic are guesses: at most CLOSE_MATCH.
    ("Yannis", "Γιάννης", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Mohammed Ali", "محمد علي", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Muhammad Ali", "محمد علي", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Abdullah", "عبد الله", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Abdel Rahman", "عبد الرحمن", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Abderrahmane", "عبد الرحمن", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Fatima Al-Zahra", "فاطمة الزهراء", C, {Reason.APPROXIMATE_TRANSLITERATION}),
    ("Vladimir Putin", "Владимир Путен", C, {Reason.FUZZY_TOKEN}),
    # Different names stay apart across scripts.
    ("Ahmed", "حامد", N, {Reason.APPROXIMATE_TRANSLITERATION}),  # Ahmad vs Hamid
    ("Giorgos Papadopoulos", "Νίκος Παπαδόπουλος", N, set()),
    ("Ivan Petrov", "Сергей Петров", N, set()),
    ("Γιώργος", "محمد", N, set()),
    # No romanisation available for this script yet.
    ("Wang Xiaoming", "王小明", X, {Reason.UNSUPPORTED_SCRIPT}),
    # Companies.
    # EPC288-23: abbreviated or missing legal forms are close matches for companies.
    ("Acme GmbH", "ACME Gesellschaft mit beschränkter Haftung", C, {Reason.LEGAL_FORM_MATCHED}),
    ("Acme", "Acme Ltd", C, {Reason.LEGAL_FORM_MISSING}),
    ("Acme Ltd.", "ACME LIMITED", C, {Reason.LEGAL_FORM_MATCHED}),
    ("Kowalski Sp. z o.o.", "Kowalski spółka z ograniczoną odpowiedzialnością", C, set()),
    ("Athinaiki Zythopoiia AE", "Αθηναϊκή Ζυθοποιία ΑΕ", M, {Reason.TRANSLITERATED}),
    ("Energo EOOD", "Енерго ЕООД", M, {Reason.TRANSLITERATED}),
    ("Acme GmbH", "Acme AG", C, {Reason.LEGAL_FORM_CONFLICT}),
    ("Acme Ltd", "Apex Ltd", N, set()),
    ("Smith & Sons Ltd", "Smith & Sons Ltd", M, set()),
    ("Li Ou", "Ou Li", M, {Reason.TOKEN_REORDER}),  # "ou" is also a legal form (Estonian OÜ)
]


@pytest.mark.parametrize(("provided", "account", "expected", "reasons"), SCRIPT_CASES)
def test_script_and_company_cases(
    provided: str, account: str, expected: MatchResult, reasons: set[Reason]
) -> None:
    verdict = match(provided, [account])
    assert verdict.result is expected, verdict
    assert reasons <= set(verdict.explanation), verdict


def test_company_with_ampersand_is_not_split_into_holders() -> None:
    verdict = match("Smith", ["Smith & Sons Ltd"])
    assert Reason.JOINT_ACCOUNT_HOLDER not in verdict.explanation


def test_arabic_skeleton_limit_is_documented() -> None:
    # Arabic leaves vowels unwritten, so Mohamed (محمد) and Mahmoud (محمود) share
    # the skeleton "mhmd". That is why Arabic never MATCHes: the payer is shown
    # the real name and decides.
    verdict = match("Mohamed", ["محمود"])
    assert verdict.result is C
    assert verdict.suggested_name == "محمود"


# --- M3 regressions: false MATCHes found by the benchmark ----------------------

MISSING_PART_CASES = [
    # A missing first name, surname or compound half may be someone else.
    ("Jan Józef Lipski", "Józef Lipski", C),  # two different people (Q443673 / Q1349536)
    ("Hans Herrmann", "Hans-Joachim Herrmann", C),  # Q65915 / Q61008
    ("GSKB Almaz-Antey", "Алмаз-Антей", C),  # subsidiary vs parent company
    ("Gabriel García", "Gabriel García Márquez", C),  # surname missing: payer must check
    # Genuine middle names and patronymics are still fine.
    ("John Smith", "John Michael Smith", M),
    ("Galina Vishnevskaya", "Галина Павловна Вишневская", M),
    # Official order "Surname Given Patronymic": a trailing female patronymic is
    # always a patronymic; a trailing male one (-ovich) could be a surname.
    ("Galina Vishnevskaya", "ВИШНЕВСКАЯ ГАЛИНА ПАВЛОВНА", M),
    ("Inna Derusova", "Дерусова Інна Миколаївна", M),
    ("Viktor Tsybulenko", "Цибуленко Віктор Сергійович", C),
    ("Jean-Pierre Dupont", "Jean-Pierre Dupont", M),
    ("Jean Pierre Dupont", "Jean-Pierre Dupont", M),
]


@pytest.mark.parametrize(("provided", "account", "expected"), MISSING_PART_CASES)
def test_missing_name_parts(provided: str, account: str, expected: MatchResult) -> None:
    verdict = match(provided, [account])
    assert verdict.result is expected, verdict
    if expected is C:
        assert Reason.MISSING_NAME_PART in verdict.explanation


@pytest.mark.parametrize(
    ("provided", "account", "expected"),
    [
        # English-media convention: ё -> yo, final -ий/-ый -> y.
        ("Pyotr Kapitsa", "Пётр Леонидович Капица", M),
        ("Semyon Budyonny", "Семён Михайлович Будённый", M),
        ("Fyodor Dostoyevsky", "Фёдор Михайлович Достоевский", M),
        ("Dmitry Shostakovich", "Дмитрий Дмитриевич Шостакович", M),
        # Spellings no scheme produces stay CLOSE: the payer checks the real name.
        ("Pyotr Tchaikovsky", "Пётр Ильич Чайковский", C),
        ("Fyodor Dostoevsky", "Фёдор Михайлович Достоевский", C),
        ("Mehdaoui Abderrahmane", "عبد الرحمان مهداوي", C),  # Arabic compound, reordered
    ],
)
def test_benchmark_driven_recall_fixes(provided: str, account: str, expected: MatchResult) -> None:
    assert match(provided, [account]).result is expected
