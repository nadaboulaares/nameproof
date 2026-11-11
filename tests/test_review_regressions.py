"""Regression tests for the pre-release security review.

Each case reproduced a false MATCH (fraud risk), a name leak, or a slowdown
before the fix. Names are synthetic or belong to public figures.
"""

import time

import pytest

from nameproof import MatchResult, match
from nameproof.matcher import MAX_ACCOUNT_NAMES, MAX_NAME_LENGTH

M, C = MatchResult.MATCH, MatchResult.CLOSE_MATCH

NEVER_MATCH = [
    # 1. Different companies sharing words around a legal form.
    ("Siemens AG", "Siemens Energy AG"),
    ("Acme Ltd", "Acme Two Ltd"),
    ("Deutsche Bank AG", "Deutsche Fake Bank AG"),
    ("Acme Widgets Ltd", "Acme Bogus Widgets Ltd"),
    # 2. Particles that are names, initials or different relations.
    ("Hassan Ibn Ali", "Hassan Abu Ali"),
    ("Ali Ben", "Ali Abu"),
    ("John E. Smith", "John A. Smith"),
    ("E Smith", "Y Smith"),
    ("Maria Da Silva", "Maria Do Silva"),
    ("Ben Smith", "Smith"),
    ("Adam Smith", "Ben Adam Smith"),
    ("An", "Le Van An"),
    ("Minh Anh", "Le Minh Anh"),
    ("Adam Ben", "Adam"),
    # 3. Title-like words that are names.
    ("Hugh", "Hugh Herr"),
    ("Smith", "Dona Smith"),
    ("Lee", "Ing Lee"),
    ("Maria Mag", "Maria Dona"),
    # 4. Legal-form-like words in personal names.
    ("Maria", "Maria Sá"),
    ("Anna", "Anna Ab"),
    ("Li As", "Li"),
    ("Smith", "Smith AG"),
    # 5. One word of a joint account or a company.
    ("Gamble", "Procter & Gamble"),
    ("Spencer", "Marks and Spencer"),
    ("Smith", "Smith and Sons"),
    ("Johnson", "Johnson & Johnson"),
    ("John", "John & Mary"),
    ("Jan", "Jan en Piet"),
    # 6. Surnames that look like patronymics.
    ("Roman Arkadyevich", "Abramovich Roman Arkadyevich"),
    ("Роман Аркадьевич", "Абрамович Роман Аркадьевич"),
    ("Ivan Petrov", "Ivan Petrov Rabinovich"),
    ("Dmitri Dmitrievich", "Dmitri Dmitrievich Shostakovich"),
    # 8. Different spellings in the same script.
    ("Σοφία Παππά", "Σωφία Παππά"),
    ("Ελένη", "Ελένι"),
    ("Ηλίας", "Ιλίας"),
    ("Мила", "Мыла"),
    ("Щука", "Штука"),
    ("Элла", "Елла"),
]


@pytest.mark.parametrize(("provided", "account"), NEVER_MATCH)
def test_never_match(provided: str, account: str) -> None:
    verdict = match(provided, [account])
    assert verdict.result is not M, verdict


LEAK_PROBES = [
    ("GmbH", "Acme Widgets GmbH"),
    ("de", "Maria de Souza"),
    ("Ltd", "Smith & Sons Ltd"),
    ("and", "John and Mary Smith"),
    ("of", "Bank of Valletta"),
    ("The", "The Smith Partnership"),
    ("Bank", "Deutsche Bank AG"),
    ("van", "Ludwig van Beethoven"),
    ("al", "Fatima al Zahra"),
    ("Smith", "John Smith"),
]


@pytest.mark.parametrize(("probe", "account"), LEAK_PROBES)
def test_generic_words_never_reveal_the_account_name(probe: str, account: str) -> None:
    # 7. Anyone who knows an IBAN could otherwise read the holder's name.
    verdict = match(probe, [account])
    assert verdict.result is not C, verdict
    assert verdict.suggested_name is None


@pytest.mark.parametrize(
    ("provided", "account"),
    [
        ("Mary Smith", "John & Mary Smith"),  # one holder of a joint account
        ("John Smith", "John and Mary Smith"),
        ("Galina Vishnevskaya", "Галина Павловна Вишневская"),  # patronymic in the middle
        ("Abdel Rahman", "Abdel Rahman"),
        ("Jeanpierre Dupont", "Jean-Pierre Dupont"),
        ("Madonna", "Madonna"),
        ("Acme GmbH", "Acme GmbH"),
    ],
)
def test_legitimate_matches_still_match(provided: str, account: str) -> None:
    assert match(provided, [account]).result is M


@pytest.mark.parametrize(
    ("provided", "account"),
    [
        ("Abdullah", "عبد الله"),  # compound written as one word: not a one-word probe
        ("Jon Smyth", "John Smith"),
        ("Hassan Ibn Ali", "Hassan Abu Ali"),
    ],
)
def test_close_matches_still_close(provided: str, account: str) -> None:
    assert match(provided, [account]).result is C


def test_overlong_alias_is_skipped_not_fatal() -> None:
    # 10. One unrealistic alias must not make the whole account unverifiable.
    alias = "A" * 10 + " " + "B" * (MAX_NAME_LENGTH - 9)
    assert match("John Smith", ["John Smith", alias]).result is M


def test_unicode_expansion_is_length_checked_after_normalisation() -> None:
    # 9. NFKC turns U+FDFA into 18 characters; 140 of them is not a name.
    verdict = match("ﷺ" * 140, ["John Smith"])
    assert verdict.result is MatchResult.NOT_POSSIBLE
    assert verdict.explanation == ("name_too_long",)


def test_too_many_words_is_not_possible() -> None:
    assert match(" ".join(["ab"] * 11), ["ab"]).result is MatchResult.NOT_POSSIBLE


def test_crafted_input_stays_fast() -> None:
    # 9. Many spelling variants on both sides used to multiply into ~20 s of CPU.
    crafted = "Αβ-Ив de Αβ-Ив van Αβ-Ив da Αβ-Ив Sp z o o"
    assert len(crafted) <= MAX_NAME_LENGTH
    start = time.perf_counter()
    match(crafted, [crafted] * MAX_ACCOUNT_NAMES)
    assert time.perf_counter() - start < 3.0


def test_lenient_policy_accepts_documented_equivalences() -> None:
    lenient = "lenient@1"
    assert match("Ludwig van Beethoven", ["Ludwig Beethoven"], policy=lenient).result is M
    assert match("Acme Ltd", ["ACME LIMITED"], policy=lenient).result is M
    # ...but never the review's counterexamples.
    assert match("Hassan Ibn Ali", ["Hassan Abu Ali"], policy=lenient).result is not M
    assert match("Siemens AG", ["Siemens Energy AG"], policy=lenient).result is not M
    assert match("Smith", ["Smith AG"], policy=lenient).result is not M
