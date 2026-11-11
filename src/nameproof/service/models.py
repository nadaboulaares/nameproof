"""Request models for EPC103-24 v1.1.1 (section 4.2) and the /v1/match endpoint."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

from nameproof.matcher import MAX_ACCOUNT_NAMES, MAX_NAME_LENGTH
from nameproof.service.formats import BIC_PATTERN, IBAN_PATTERN, ORGANISATION_SCHEMES


def _text(max_length: int) -> object:
    # MaxNNNTextVop: 1..NNN characters, must not start with whitespace (section 3.1).
    return StringConstraints(min_length=1, max_length=max_length, pattern=r"^\S")


Max35Text = Annotated[str, _text(35)]
Max140Text = Annotated[str, _text(140)]
Max256Text = Annotated[str, _text(256)]
Bic = Annotated[str, StringConstraints(pattern=f"^{BIC_PATTERN.pattern}$")]
Iban = Annotated[str, StringConstraints(pattern=f"^{IBAN_PATTERN.pattern}$")]
Lei = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{18}[0-9]{2}$")]


def _known_scheme(code: str) -> str:
    if code not in ORGANISATION_SCHEMES:
        msg = f"unknown schemeNameCode {code!r}"
        raise ValueError(msg)
    return code


SchemeCode = Annotated[str, AfterValidator(_known_scheme)]


class _Model(BaseModel):
    """camelCase on the wire; unknown fields are a FORMAT_ERROR (section 4.4.2)."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)


def _exactly_one(model: BaseModel, *fields: str) -> None:
    present = [name for name in fields if getattr(model, name) is not None]
    if len(present) != 1:
        wire = [type(model).model_fields[name].alias or name for name in fields]
        msg = f"exactly one of {', '.join(repr(w) for w in wire)} must be provided"
        raise ValueError(msg)


class GenericOrganisationIdentification(_Model):
    """Section 4.2.4."""

    identification: Max256Text
    scheme_name_code: SchemeCode | None = None
    scheme_name_proprietary: Max35Text | None = None
    issuer: Max35Text | None = None

    @model_validator(mode="after")
    def _one_scheme(self) -> Self:
        _exactly_one(self, "scheme_name_code", "scheme_name_proprietary")
        return self

    @property
    def scheme(self) -> str:
        """The identification scheme, upper case (e.g. ``"TXID"``)."""
        return (self.scheme_name_code or self.scheme_name_proprietary or "").upper()


class OrganisationId(_Model):
    """Section 4.2.1: one of LEI, BIC or one generic identification."""

    lei: Lei | None = None
    any_bic: Bic | None = Field(default=None, alias="anyBIC")
    others: list[GenericOrganisationIdentification] | None = Field(
        default=None, min_length=1, max_length=1
    )

    @model_validator(mode="after")
    def _one_identifier(self) -> Self:
        _exactly_one(self, "lei", "any_bic", "others")
        return self

    def scheme_and_value(self) -> tuple[str, str]:
        """Return ``(scheme, value)`` for whichever identifier was sent."""
        if self.lei is not None:
            return "LEI", self.lei
        if self.any_bic is not None:
            return "BIC", self.any_bic
        assert self.others is not None  # noqa: S101 - guaranteed by _one_identifier
        return self.others[0].scheme, self.others[0].identification


class Identification(_Model):
    """Wrapper of ``organisationId``."""

    organisation_id: OrganisationId


class Party(_Model):
    """Section 4.2.1: the payee, by name or by identification (never both)."""

    name: Max140Text | None = None
    identification: Identification | None = None

    @model_validator(mode="after")
    def _name_or_identification(self) -> Self:
        _exactly_one(self, "name", "identification")
        return self


class Account(_Model):
    """Section 4.2.2."""

    iban: Iban


class FinancialInstitutionId(_Model):
    """Section 4.2.3."""

    bicfi: Bic


class Agent(_Model):
    """Section 4.2.3."""

    financial_institution_id: FinancialInstitutionId


class VopRequest(_Model):
    """Section 4.1.2.2: body of ``POST /vop/v1/payee-verifications``."""

    party: Party
    party_account: Account
    party_agent: Agent
    unstructured_remittance_information: list[Max140Text] | None = Field(
        default=None, min_length=1, max_length=1
    )
    requesting_agent: Agent


class MatchRequest(_Model):
    """Body of ``POST /v1/match``: compare a name against known holder names."""

    provided: Annotated[str, StringConstraints(max_length=MAX_NAME_LENGTH)]
    account_names: list[Annotated[str, StringConstraints(max_length=MAX_NAME_LENGTH)]] = Field(
        min_length=1, max_length=MAX_ACCOUNT_NAMES
    )
    policy: str | None = None
