"""The pure-Python fallback must agree with rapidfuzz, which it replaces in the browser."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rapidfuzz.distance import JaroWinkler, Levenshtein

from nameproof import _similarity

# Small alphabets make matches and transpositions likely, which is where bugs hide.
_word = st.text(alphabet="abcdeé", max_size=12)


@settings(max_examples=2000)
@given(left=_word, right=_word)
def test_levenshtein_equals_rapidfuzz(left: str, right: str) -> None:
    expected = Levenshtein.normalized_similarity(left, right)
    assert _similarity.levenshtein(left, right) == pytest.approx(expected, abs=1e-12)


@settings(max_examples=2000)
@given(left=_word, right=_word)
def test_jaro_winkler_equals_rapidfuzz(left: str, right: str) -> None:
    expected = JaroWinkler.normalized_similarity(left, right)
    assert _similarity.jaro_winkler(left, right) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    ("left", "right"),
    [("martha", "marhta"), ("dixon", "dicksonx"), ("maria", "mario"), ("", ""), ("a", "")],
)
def test_known_values(left: str, right: str) -> None:
    assert _similarity.jaro_winkler(left, right) == pytest.approx(
        JaroWinkler.normalized_similarity(left, right)
    )
    assert _similarity.levenshtein(left, right) == pytest.approx(
        Levenshtein.normalized_similarity(left, right)
    )
