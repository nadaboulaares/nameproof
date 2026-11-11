"""Service configuration, read from ``NAMEPROOF_*`` environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from nameproof.matcher import MAX_ACCOUNT_NAMES
from nameproof.policy import DEFAULT_POLICY


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _codes(value: str) -> frozenset[str]:
    return frozenset(code.strip().upper() for code in value.split(",") if code.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings. Every field has a safe default.

    Attributes:
        directory: account directory spec (``json:<path>`` or ``plugin:<mod>:<factory>``).
        policy: nameproof policy identifier.
        allowed_requesting_bics: if set, only these requesting PSPs are served
            (401 CLIENT_INVALID otherwise).
        client_bic_header: header in which the TLS-terminating gateway passes the
            BIC it verified from the client's QWAC; it must equal
            ``requestingAgent`` (401 CLIENT_INCONSISTENT otherwise).
        max_request_age_s / max_clock_skew_s: accepted ``X-Request-Timestamp`` window.
        max_body_bytes: requests larger than this are rejected (400 FORMAT_ERROR).
        max_holder_names: at most this many names per account are compared.
        latin_matched_name: send ``matchedName`` in the SEPA basic Latin set.
        request_charset: characters accepted in request names and remittance
            information: ``latin`` (default), ``sepa-basic`` or ``any``.
        match_endpoint: serve ``POST /v1/match`` (off by default: it accepts
            arbitrary account names, so only enable it behind authentication).
        docs: serve the OpenAPI UI at ``/docs``.

    """

    directory: str = ""
    policy: str = DEFAULT_POLICY
    allowed_requesting_bics: frozenset[str] = field(default_factory=frozenset)
    client_bic_header: str = ""
    max_request_age_s: float = 300.0
    max_clock_skew_s: float = 30.0
    max_body_bytes: int = 16_384
    max_holder_names: int = 10
    latin_matched_name: bool = True
    request_charset: str = "latin"
    match_endpoint: bool = False
    docs: bool = True

    def __post_init__(self) -> None:
        """Reject settings the service can't honour."""
        if self.request_charset not in {"latin", "sepa-basic", "any"}:
            msg = f"request_charset must be latin, sepa-basic or any: {self.request_charset!r}"
            raise ValueError(msg)
        if not 1 <= self.max_holder_names <= MAX_ACCOUNT_NAMES:
            msg = f"max_holder_names must be between 1 and {MAX_ACCOUNT_NAMES}"
            raise ValueError(msg)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Read settings from ``env`` (defaults to ``os.environ``)."""
        env = os.environ if env is None else env
        default = cls()
        return cls(
            directory=env.get("NAMEPROOF_DIRECTORY", default.directory),
            policy=env.get("NAMEPROOF_POLICY", default.policy),
            allowed_requesting_bics=_codes(env.get("NAMEPROOF_ALLOWED_REQUESTING_BICS", "")),
            client_bic_header=env.get("NAMEPROOF_CLIENT_BIC_HEADER", default.client_bic_header),
            max_request_age_s=float(
                env.get("NAMEPROOF_MAX_REQUEST_AGE_S", default.max_request_age_s)
            ),
            max_clock_skew_s=float(env.get("NAMEPROOF_MAX_CLOCK_SKEW_S", default.max_clock_skew_s)),
            max_body_bytes=int(env.get("NAMEPROOF_MAX_BODY_BYTES", default.max_body_bytes)),
            max_holder_names=int(env.get("NAMEPROOF_MAX_HOLDER_NAMES", default.max_holder_names)),
            latin_matched_name=_flag(env.get("NAMEPROOF_LATIN_MATCHED_NAME", "true")),
            request_charset=env.get("NAMEPROOF_REQUEST_CHARSET", default.request_charset),
            match_endpoint=_flag(env.get("NAMEPROOF_MATCH_ENDPOINT", "false")),
            docs=_flag(env.get("NAMEPROOF_DOCS", "true")),
        )
