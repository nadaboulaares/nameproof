"""Where the responder looks up who holds an IBAN.

A bank plugs in its own directory (core banking lookup). Two are built in:

- ``json:/path/accounts.json``: a JSON file, for demos and tests;
- ``plugin:package.module:factory``: any callable returning an ``AccountDirectory``.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AccountRecord:
    """What the responding bank knows about one account.

    ``names`` should list each holder separately ("John Smith", "Mary Smith"),
    so a close match reveals only the matching holder (data minimisation).
    ``identifiers`` maps a scheme (``"LEI"``, ``"BIC"``, or an ISO
    ExternalOrganisationIdentification1Code such as ``"TXID"``) to its value.
    """

    names: tuple[str, ...]
    identifiers: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class AccountDirectory(Protocol):
    """Looks up account records by IBAN."""

    def lookup(self, iban: str) -> AccountRecord | None:
        """Return the record for ``iban``, or ``None`` if the account is unknown."""
        ...  # pragma: no cover


class InMemoryDirectory:
    """A directory backed by a dict; handy for tests and as a plugin base."""

    def __init__(self, records: Mapping[str, AccountRecord]) -> None:
        """Index ``records`` by IBAN (spaces removed, upper case)."""
        self._records = {_clean_iban(iban): record for iban, record in records.items()}

    def lookup(self, iban: str) -> AccountRecord | None:
        """Return the record for ``iban``, or ``None``."""
        return self._records.get(_clean_iban(iban))


def _clean_iban(iban: str) -> str:
    return "".join(iban.split()).upper()


def _record(iban: str, data: object) -> AccountRecord:
    if not isinstance(data, dict):
        msg = f"account {iban}: expected an object with 'names'"
        raise ValueError(msg)
    names = data.get("names")
    identifiers = data.get("identifiers", {})
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        msg = f"account {iban}: 'names' must be a non-empty list of strings"
        raise ValueError(msg)
    if not isinstance(identifiers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in identifiers.items()
    ):
        msg = f"account {iban}: 'identifiers' must map strings to strings"
        raise ValueError(msg)
    return AccountRecord(tuple(names), {k.upper(): v for k, v in identifiers.items()})


def json_directory(path: Path) -> InMemoryDirectory:
    """Load ``{"<IBAN>": {"names": [...], "identifiers": {...}}}`` from a JSON file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{path}: expected a JSON object keyed by IBAN"
        raise ValueError(msg)
    return InMemoryDirectory({iban: _record(iban, data) for iban, data in raw.items()})


def load_directory(spec: str) -> AccountDirectory:
    """Build a directory from ``json:<path>`` or ``plugin:<module>:<factory>``."""
    kind, _, target = spec.partition(":")
    if kind == "json" and target:
        return json_directory(Path(target))
    if kind == "plugin" and ":" in target:
        module_name, _, factory_name = target.rpartition(":")
        factory = getattr(importlib.import_module(module_name), factory_name)
        directory = factory()
        if not isinstance(directory, AccountDirectory):
            msg = f"{target} did not return an AccountDirectory"
            raise TypeError(msg)
        return directory
    msg = f"invalid directory spec {spec!r}; use 'json:<path>' or 'plugin:<module>:<factory>'"
    raise ValueError(msg)
