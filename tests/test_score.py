import pytest

from nameproof.score import INITIAL_SIMILARITY, Alignment, PairKind, align, token_similarity


def test_token_similarity_kinds() -> None:
    assert token_similarity("john", "john") == (1.0, PairKind.EXACT)
    assert token_similarity("j", "john") == (INITIAL_SIMILARITY, PairKind.INITIAL)
    assert token_similarity("john", "j") == (INITIAL_SIMILARITY, PairKind.INITIAL)
    assert token_similarity("m", "john") == (0.0, PairKind.FUZZY)
    similarity, kind = token_similarity("maria", "mario")
    assert kind is PairKind.FUZZY
    assert 0.8 < similarity < 0.9


def test_align_handles_reordering() -> None:
    alignment = align(("smith", "john"), ("john", "smith"))
    assert alignment.reordered
    assert alignment.unmatched == 0
    assert alignment.score(0.05) == 1.0


def test_align_counts_missing_tokens_on_either_side() -> None:
    assert align(("john", "smith"), ("john", "paul", "smith")).unmatched == 1
    longer_left = align(("john", "paul", "smith"), ("john", "smith"))
    assert longer_left.unmatched == 1
    assert not longer_left.reordered
    assert longer_left.score(0.05) == pytest.approx(0.95)


def test_align_uses_greedy_beyond_brute_force_limit() -> None:
    left = ("a1", "b2", "c3", "d4", "e5", "f6", "g7")
    alignment = align(left, tuple(reversed(left)))
    assert all(pair.kind is PairKind.EXACT for pair in alignment.pairs)
    assert alignment.reordered


def test_empty_alignment_scores_zero() -> None:
    assert Alignment(pairs=(), unmatched=0).score(0.05) == 0.0
