"""nameproof: explainable name matching across scripts."""

from nameproof._types import MatchResult, Verdict
from nameproof.explain import Reason
from nameproof.matcher import match
from nameproof.policy import DEFAULT_POLICY, Policy, available_policies, load_policy

__all__ = [
    "DEFAULT_POLICY",
    "MatchResult",
    "Policy",
    "Reason",
    "Verdict",
    "__version__",
    "available_policies",
    "load_policy",
    "match",
]

__version__ = "0.3.0"
