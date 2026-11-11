from hypothesis import given
from hypothesis import strategies as st

from nameproof.explain import Reason
from nameproof.normalize import fold_variants, normalize_text


def test_normalize_casefolds_and_collapses_punctuation() -> None:
    assert normalize_text("  Jean-Pierre   DUPONT, Jr. ") == "jean-pierre dupont jr"


def test_normalize_keeps_only_inner_hyphens() -> None:
    assert normalize_text("Al-Zahra - Smith-  -Jones--Lee") == "al-zahra smith jones lee"


def test_normalize_drops_apostrophes() -> None:
    assert normalize_text("O\u2019Brien d'Angelo") == "obrien dangelo"


def test_normalize_keeps_joint_symbols_as_tokens() -> None:
    assert normalize_text("John&Mary+Ann") == "john & mary + ann"


def test_normalize_keeps_combining_marks() -> None:
    assert normalize_text("José") == "josé"


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize_text(text)
    assert normalize_text(once) == once


def test_fold_plain_ascii_has_no_reasons() -> None:
    assert fold_variants("john smith") == (("john smith", ()),)


def test_fold_diacritics() -> None:
    assert fold_variants("jose garcía") == (("jose garcia", (Reason.DIACRITICS_FOLDED,)),)


def test_fold_offers_letter_expansion() -> None:
    assert dict(fold_variants("müller")) == {
        "muller": (Reason.DIACRITICS_FOLDED,),
        "mueller": (Reason.LETTER_EXPANSION,),
    }


def test_fold_special_letters() -> None:
    assert dict(fold_variants("łódź søren"))["lodz soren"] == (Reason.DIACRITICS_FOLDED,)
