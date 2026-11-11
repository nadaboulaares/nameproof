"""Core result types shared by every matcher stage."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class MatchResult(StrEnum):
    """Outcome of a payee name check, aligned with the four EPC VoP answers."""

    MATCH = "MATCH"
    CLOSE_MATCH = "CLOSE_MATCH"
    NO_MATCH = "NO_MATCH"
    NOT_POSSIBLE = "NOT_POSSIBLE"


@dataclass(frozen=True, slots=True)
class Verdict:
    """Explainable result of comparing a provided name against account holder names.

    ``suggested_name`` may only be set for ``CLOSE_MATCH``: the scheme lets the
    payer see the real account name in that case only, so any other outcome must
    not leak it (the matcher must never become a name-lookup oracle).
    """

    result: MatchResult
    score: float
    policy_version: str
    explanation: tuple[str, ...] = ()
    suggested_name: str | None = None

    def __post_init__(self) -> None:
        """Validate invariants that downstream code and auditors rely on."""
        if math.isnan(self.score) or not 0.0 <= self.score <= 1.0:
            msg = f"score must be within [0, 1], got {self.score!r}"
            raise ValueError(msg)
        if not self.policy_version:
            msg = "policy_version must be non-empty so results are reproducible"
            raise ValueError(msg)
        if self.suggested_name is not None and self.result is not MatchResult.CLOSE_MATCH:
            msg = "suggested_name is only allowed for CLOSE_MATCH results"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view with a stable key order."""
        return {
            "result": self.result.value,
            "score": self.score,
            "policy_version": self.policy_version,
            "explanation": list(self.explanation),
            "suggested_name": self.suggested_name,
        }
