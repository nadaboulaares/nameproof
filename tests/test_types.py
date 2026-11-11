import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nameproof import MatchResult, Verdict


def test_match_result_values_are_stable_wire_strings() -> None:
    assert [r.value for r in MatchResult] == ["MATCH", "CLOSE_MATCH", "NO_MATCH", "NOT_POSSIBLE"]


@given(score=st.floats(min_value=0.0, max_value=1.0), result=st.sampled_from(MatchResult))
def test_valid_scores_are_accepted(score: float, result: MatchResult) -> None:
    verdict = Verdict(result=result, score=score, policy_version="test@1")
    assert verdict.score == score


@pytest.mark.parametrize("score", [-0.01, 1.01, math.nan, math.inf, -math.inf])
def test_out_of_range_scores_are_rejected(score: float) -> None:
    with pytest.raises(ValueError, match="score"):
        Verdict(result=MatchResult.MATCH, score=score, policy_version="test@1")


def test_empty_policy_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="policy_version"):
        Verdict(result=MatchResult.MATCH, score=1.0, policy_version="")


def test_suggested_name_allowed_for_close_match() -> None:
    verdict = Verdict(
        result=MatchResult.CLOSE_MATCH,
        score=0.8,
        policy_version="test@1",
        suggested_name="Giorgos Papadopoulos",
    )
    assert verdict.suggested_name == "Giorgos Papadopoulos"


@pytest.mark.parametrize(
    "result", [MatchResult.MATCH, MatchResult.NO_MATCH, MatchResult.NOT_POSSIBLE]
)
def test_suggested_name_never_leaks_outside_close_match(result: MatchResult) -> None:
    with pytest.raises(ValueError, match="suggested_name"):
        Verdict(result=result, score=0.5, policy_version="test@1", suggested_name="Real Name")


def test_verdict_is_immutable() -> None:
    verdict = Verdict(result=MatchResult.MATCH, score=1.0, policy_version="test@1")
    with pytest.raises(AttributeError):
        verdict.score = 0.0  # type: ignore[misc]
