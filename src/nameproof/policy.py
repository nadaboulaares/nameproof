"""Versioned, bank-configurable decision policies."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

DEFAULT_POLICY = "epc-default@2"

_SPEC = re.compile(r"[a-z0-9][a-z0-9-]*@[0-9]+")
_POLICY_DIR = files("nameproof") / "data" / "policies"


@dataclass(frozen=True, slots=True)
class Policy:
    """Thresholds and switches that turn an alignment into a verdict.

    ``MATCH`` always requires every aligned token to be identical after
    normalisation; fuzzy differences can at most give ``CLOSE_MATCH``. The three
    ``*_can_match`` switches (all off in ``epc-default``, as in EPC288-23 v2.0)
    let a bank also accept a dropped surname particle ("van Beethoven" vs
    "Beethoven"), a spelled-out or missing legal form ("Ltd" vs "Limited"), and
    company words in another order as a ``MATCH``. ``distinct_word_threshold``
    (0 = off; 0.65 from ``epc-default@2``) rules out ``CLOSE_MATCH`` for a
    person's name with a word less similar than that ("Mohamed" vs "Mahmoud").
    ``known_variants_can_match`` accepts known spellings of one Arabic name
    ("Youssef" / "Yusuf", ``records@1``) as a ``MATCH``.
    """

    name: str
    version: int
    match_threshold: float
    close_threshold: float
    missing_token_penalty: float
    max_missing_tokens_for_match: int
    initials_can_match: bool
    particle_variants_can_match: bool = False
    legal_form_variants_can_match: bool = False
    company_reorder_can_match: bool = False
    distinct_word_threshold: float = 0.0
    known_variants_can_match: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        """Reject inconsistent policies early."""
        if not _SPEC.fullmatch(self.id):
            msg = f"invalid policy name or version: {self.id!r}"
            raise ValueError(msg)
        for field in (
            "match_threshold",
            "close_threshold",
            "missing_token_penalty",
            "distinct_word_threshold",
        ):
            value = getattr(self, field)
            if not 0.0 <= value <= 1.0:
                msg = f"{field} must be within [0, 1], got {value!r}"
                raise ValueError(msg)
        if self.close_threshold > self.match_threshold:
            msg = "close_threshold must not exceed match_threshold"
            raise ValueError(msg)
        if self.max_missing_tokens_for_match < 0:
            msg = "max_missing_tokens_for_match must be >= 0"
            raise ValueError(msg)

    @property
    def id(self) -> str:
        """Identifier recorded on every verdict, e.g. ``"epc-default@2"``."""
        return f"{self.name}@{self.version}"

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> Policy:
        """Build a policy from parsed TOML/JSON, checking every field's type."""
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            msg = f"unknown policy fields: {sorted(unknown)}"
            raise ValueError(msg)
        return cls(
            name=_str(data, "name"),
            version=_int(data, "version"),
            match_threshold=_float(data, "match_threshold"),
            close_threshold=_float(data, "close_threshold"),
            missing_token_penalty=_float(data, "missing_token_penalty"),
            max_missing_tokens_for_match=_int(data, "max_missing_tokens_for_match"),
            initials_can_match=_bool(data, "initials_can_match"),
            particle_variants_can_match=_optional_bool(data, "particle_variants_can_match"),
            legal_form_variants_can_match=_optional_bool(data, "legal_form_variants_can_match"),
            company_reorder_can_match=_optional_bool(data, "company_reorder_can_match"),
            known_variants_can_match=_optional_bool(data, "known_variants_can_match"),
            distinct_word_threshold=(
                _float(data, "distinct_word_threshold")
                if "distinct_word_threshold" in data
                else 0.0
            ),
            description=_str(data, "description") if "description" in data else "",
        )


def _field(data: Mapping[str, object], key: str) -> object:
    if key not in data:
        msg = f"policy field {key!r} is required"
        raise ValueError(msg)
    return data[key]


def _wrong_type(key: str, value: object) -> ValueError:
    return ValueError(f"policy field {key!r} has the wrong type: {value!r}")


def _str(data: Mapping[str, object], key: str) -> str:
    value = _field(data, key)
    if not isinstance(value, str):
        raise _wrong_type(key, value)
    return value


def _int(data: Mapping[str, object], key: str) -> int:
    value = _field(data, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _wrong_type(key, value)
    return value


def _float(data: Mapping[str, object], key: str) -> float:
    value = _field(data, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _wrong_type(key, value)
    return float(value)


def _optional_bool(data: Mapping[str, object], key: str) -> bool:
    return _bool(data, key) if key in data else False


def _bool(data: Mapping[str, object], key: str) -> bool:
    value = _field(data, key)
    if not isinstance(value, bool):
        raise _wrong_type(key, value)
    return value


def available_policies() -> list[str]:
    """List the identifiers of the built-in policies."""
    return sorted(
        entry.name.removesuffix(".toml")
        for entry in _POLICY_DIR.iterdir()
        if entry.name.endswith(".toml")
    )


@lru_cache(maxsize=32)
def _builtin(spec: str) -> Policy:
    if not _SPEC.fullmatch(spec):
        msg = f"invalid policy identifier {spec!r} (expected 'name@version')"
        raise ValueError(msg)
    resource = _POLICY_DIR / f"{spec}.toml"
    if not resource.is_file():
        msg = f"unknown policy {spec!r}; available: {', '.join(available_policies())}"
        raise ValueError(msg)
    policy = Policy.from_mapping(tomllib.loads(resource.read_text(encoding="utf-8")))
    if policy.id != spec:
        msg = f"policy file {spec!r} declares id {policy.id!r}"
        raise ValueError(msg)
    return policy


def load_policy(policy: str | Policy = DEFAULT_POLICY) -> Policy:
    """Return ``policy`` itself, or the built-in policy with that identifier."""
    if isinstance(policy, Policy):
        return policy
    return _builtin(policy)
