from typing import Any

import pytest

from nameproof import DEFAULT_POLICY, Policy, available_policies, load_policy

BASE: dict[str, Any] = {
    "name": "custom",
    "version": 2,
    "match_threshold": 0.95,
    "close_threshold": 0.8,
    "missing_token_penalty": 0.05,
    "max_missing_tokens_for_match": 1,
    "initials_can_match": False,
}


def test_builtin_policies_are_listed_and_load() -> None:
    assert DEFAULT_POLICY in available_policies()
    for spec in available_policies():
        assert load_policy(spec).id == spec


def test_policy_object_passes_through() -> None:
    policy = Policy.from_mapping(BASE)
    assert load_policy(policy) is policy
    assert policy.id == "custom@2"


@pytest.mark.parametrize("spec", ["../etc/passwd@1", "epc-default", "EPC@1", "x@1.0", ""])
def test_malformed_identifiers_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError, match="invalid policy identifier"):
        load_policy(spec)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"match_threshold": 1.5}, "match_threshold"),
        ({"close_threshold": 0.99}, "must not exceed"),
        ({"max_missing_tokens_for_match": -1}, ">= 0"),
        ({"name": "Bad Name"}, "invalid policy name"),
        ({"version": True}, "wrong type"),
        ({"version": "1"}, "wrong type"),
        ({"match_threshold": "high"}, "wrong type"),
        ({"initials_can_match": 1}, "wrong type"),
        ({"name": 7}, "wrong type"),
        ({"surprise": 1}, "unknown policy fields"),
    ],
)
def test_invalid_policies_are_rejected(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Policy.from_mapping({**BASE, **override})


def test_missing_field_is_rejected() -> None:
    data = dict(BASE)
    del data["close_threshold"]
    with pytest.raises(ValueError, match="required"):
        Policy.from_mapping(data)


def test_description_is_optional_and_typed() -> None:
    assert Policy.from_mapping({**BASE, "description": "hi"}).description == "hi"
    assert Policy.from_mapping({**BASE, "match_threshold": 1}).match_threshold == 1.0
