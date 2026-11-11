"""FastAPI app: EPC Verification of Payee responder plus a plain matching endpoint.

Transport security (mutual TLS with PSD2 QWACs) and the EPC Directory Service
check belong to the bank's API gateway, in front of this service. The gateway can
pass the BIC it verified in a header (``Settings.client_bic_header``).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from nameproof import __version__
from nameproof._types import MatchResult
from nameproof.matcher import match
from nameproof.policy import load_policy
from nameproof.service.directory import AccountDirectory, AccountRecord, load_directory
from nameproof.service.formats import (
    format_timestamp,
    in_charset,
    parse_timestamp,
    to_sepa_latin,
)
from nameproof.service.models import MatchRequest, OrganisationId, VopRequest
from nameproof.service.settings import Settings

log = logging.getLogger("nameproof.service")

VOP_PATH = "/vop/v1/payee-verifications"
# Canonical 8-4-4-4-12 UUID; other spellings uuid.UUID accepts (urn:, braces) are refused.
_REQUEST_ID = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
PROBLEM_TYPE = "https://github.com/nadaboulaares/nameproof/blob/main/docs/SERVICE.md#errors"

ModelT = TypeVar("ModelT", bound=BaseModel)

_NAME_CODES = {
    MatchResult.MATCH: "MTCH",
    MatchResult.CLOSE_MATCH: "CMTC",
    MatchResult.NO_MATCH: "NMTC",
    MatchResult.NOT_POSSIBLE: "NOAP",
}


class ProblemError(Exception):
    """An RFC 7807 problem reported to the client (section 4.4)."""

    def __init__(self, status: int, code: str, detail: str, instance: str | None = None) -> None:
        """Record the HTTP status, EPC message code and human-readable detail."""
        super().__init__(detail)
        self.status, self.code, self.detail, self.instance = status, code, detail, instance


_TITLES = {400: "Bad Request", 401: "Unauthorized", 500: "Internal Server Error"}


def _problem(error: ProblemError) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_TYPE,
        "code": error.code,
        "title": _TITLES.get(error.status, "Error"),
        "status": error.status,
        "detail": error.detail[:500],
    }
    if error.instance:
        body["instance"] = error.instance[:256]
    return JSONResponse(body, status_code=error.status, media_type="application/problem+json")


def _pointer(location: tuple[int | str, ...]) -> str:
    """JSON pointer (RFC 6901) to the offending field, without the "body" prefix."""
    parts = [str(part) for part in location[1:]] if location[:1] == ("body",) else []
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _format_error(errors: list[Any]) -> ProblemError:
    first = errors[0] if errors else {}
    location = tuple(first.get("loc", ()))
    message = str(first.get("msg", "invalid request"))
    field = _pointer(location)
    return ProblemError(400, "FORMAT_ERROR", f"{field}: {message}", instance=field)


class _BodyLimit:
    """Reject request bodies larger than ``limit`` bytes, even without Content-Length."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def limited() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    detail = f"request body exceeds {self.limit} bytes"
                    raise ProblemError(400, "FORMAT_ERROR", detail)
            return message

        await self.app(scope, limited, send)


def create_app(
    settings: Settings | None = None, directory: AccountDirectory | None = None
) -> FastAPI:
    """Build the service.

    ``/health`` always exists; the VoP responder needs an account directory, and the
    ``/v1/match`` endpoint must be switched on (``Settings.match_endpoint``).
    """
    settings = settings or Settings.from_env()
    policy = load_policy(settings.policy)  # fail fast on a bad policy id
    if directory is None and settings.directory:
        directory = load_directory(settings.directory)

    app = FastAPI(
        title="nameproof",
        version=__version__,
        summary="Explainable name matching for Verification of Payee",
        docs_url="/docs" if settings.docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs else None,
    )
    app.add_middleware(_BodyLimit, limit=settings.max_body_bytes)

    @app.middleware("http")
    async def _vop_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Timestamp"] = format_timestamp(datetime.now(UTC))
        request_id = request.headers.get("X-Request-ID", "")
        # Echo only a well-formed id; anything else gets a fresh one.
        valid = _REQUEST_ID.fullmatch(request_id) is not None
        response.headers["X-Request-ID"] = request_id if valid else str(uuid.uuid4())
        log.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response

    @app.exception_handler(ProblemError)
    async def _on_problem(_: Request, error: ProblemError) -> JSONResponse:
        return _problem(error)

    @app.exception_handler(RequestValidationError)
    async def _on_invalid(_: Request, error: RequestValidationError) -> JSONResponse:
        return _problem(_format_error(list(error.errors())))

    @app.exception_handler(Exception)
    async def _on_crash(_: Request, error: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=error)
        return _problem(ProblemError(500, "INTERNAL_ERROR", "internal server error"))

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, object]:
        """Liveness probe."""
        return {
            "status": "ok",
            "version": __version__,
            "policy": policy.id,
            "verification_of_payee": directory is not None,
            "match_endpoint": settings.match_endpoint,
        }

    models: list[type[BaseModel]] = []
    if settings.match_endpoint:
        _add_match_endpoint(app, policy.id)
        models.append(MatchRequest)
    if directory is not None:
        _add_responder(app, settings, directory, policy.id)
        models.append(VopRequest)
    else:
        log.warning("no NAMEPROOF_DIRECTORY configured: %s is disabled", VOP_PATH)
    _register_schemas(app, models)
    return app


def _add_match_endpoint(app: FastAPI, policy: str) -> None:
    @app.post(
        "/v1/match",
        tags=["matching"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/MatchRequest"}}
                },
            }
        },
    )
    async def match_names(request: Request) -> JSONResponse:
        """Compare a provided name with the account holder names you already looked up."""
        body = _parse_model(await request.body(), MatchRequest)
        try:
            verdict = await run_in_threadpool(
                match, body.provided, body.account_names, policy=body.policy or policy
            )
        except ValueError as error:
            raise ProblemError(400, "FORMAT_ERROR", str(error), "/policy") from None
        except Exception as error:
            raise _internal(error) from None
        return JSONResponse(verdict.to_dict())


def _internal(error: Exception) -> ProblemError:
    """Log an unexpected failure and turn it into a 500 the middleware still decorates."""
    log.error("unhandled error: %s", type(error).__name__, exc_info=error)
    return ProblemError(500, "INTERNAL_ERROR", "internal server error")


def _add_responder(
    app: FastAPI, settings: Settings, directory: AccountDirectory, policy: str
) -> None:
    @app.post(
        VOP_PATH,
        tags=["verification of payee"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/VopRequest"}}
                },
            }
        },
    )
    async def payee_verification(request: Request) -> JSONResponse:
        """EPC VOP Inter-PSP API (EPC103-24 v1.1.1): verify a payee name or identifier."""
        _check_headers(request.headers, settings)
        payload = _parse_model(await request.body(), VopRequest)
        _check_charset(payload, settings)
        _check_client(payload, request.headers, settings)
        try:
            # Directory lookups and matching are blocking work: keep them off the event loop.
            body = await run_in_threadpool(_verify, payload, directory, settings, policy)
        except Exception as error:
            raise _internal(error) from None
        log.info(
            "verification %s", " ".join(f"{k}={v}" for k, v in body.items() if k != "matchedName")
        )
        return JSONResponse(body)


def _register_schemas(app: FastAPI, models: list[type[BaseModel]]) -> None:
    """Publish request models in the OpenAPI document (the routes parse them themselves)."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        schema = original()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in models:
            definitions = model.model_json_schema(
                by_alias=True, ref_template="#/components/schemas/{model}"
            )
            components.update(definitions.pop("$defs", {}))
            components[model.__name__] = definitions
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def _accepts_json(accept: str) -> bool:
    media = {part.split(";")[0].strip().lower() for part in accept.split(",")}
    return bool(media & {"application/json", "application/*", "*/*"})


def _check_headers(headers: Mapping[str, str], settings: Settings) -> None:
    content_type = headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type != "application/json":  # RSR_038
        detail = "Content-Type must be application/json"
        raise ProblemError(400, "FORMAT_ERROR", detail, "/headers/Content-Type")
    if not _accepts_json(headers.get("Accept", "*/*")):  # RSR_039
        detail = "Accept must allow application/json"
        raise ProblemError(400, "FORMAT_ERROR", detail, "/headers/Accept")
    if _REQUEST_ID.fullmatch(headers.get("X-Request-ID", "")) is None:
        detail = "X-Request-ID header is mandatory and must be a UUID"
        raise ProblemError(400, "FORMAT_ERROR", detail, "/headers/X-Request-ID")
    raw = headers.get("X-Request-Timestamp")
    if raw is None:  # RSR_009 expects TIMESTAMP_INVALID, not FORMAT_ERROR
        detail = "X-Request-Timestamp header is mandatory"
        raise ProblemError(400, "TIMESTAMP_INVALID", detail, "/headers/X-Request-Timestamp")
    stamp = parse_timestamp(raw)
    now = datetime.now(UTC)
    if stamp is None:
        detail = "X-Request-Timestamp must be an ISODateTime (section 4.2.9)"
        raise ProblemError(400, "TIMESTAMP_INVALID", detail, "/headers/X-Request-Timestamp")
    if stamp > now + timedelta(seconds=settings.max_clock_skew_s):
        detail = "X-Request-Timestamp is in the future"
        raise ProblemError(400, "TIMESTAMP_INVALID", detail, "/headers/X-Request-Timestamp")
    if stamp < now - timedelta(seconds=settings.max_request_age_s):
        detail = "X-Request-Timestamp is outside the accepted validity period"
        raise ProblemError(400, "TIMESTAMP_INVALID", detail, "/headers/X-Request-Timestamp")


def _parse_model(raw: bytes, model: type[ModelT]) -> ModelT:
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProblemError(400, "FORMAT_ERROR", "request body is not valid JSON") from None
    try:
        return model.model_validate(data)
    except ValidationError as error:
        errors = [{**e, "loc": ("body", *e["loc"])} for e in error.errors()]
        raise _format_error(errors) from None


def _verify(
    payload: VopRequest, directory: AccountDirectory, settings: Settings, policy: str
) -> dict[str, str]:
    record = directory.lookup(payload.party_account.iban)
    if payload.party.name is not None:
        return _name_check(payload.party.name, record, settings, policy)
    assert payload.party.identification is not None  # noqa: S101 - model guarantees it
    return {"partyIdMatch": _id_check(payload.party.identification.organisation_id, record)}


def _check_charset(payload: VopRequest, settings: Settings) -> None:
    """Reject characters outside the agreed set (RSR_047, RSR_048)."""
    fields: list[tuple[str, str | None]] = [("/party/name", payload.party.name)]
    for index, info in enumerate(payload.unstructured_remittance_information or ()):
        fields.append((f"/unstructuredRemittanceInformation/{index}", info))
    for pointer, text in fields:
        if text is not None and not in_charset(text, settings.request_charset):
            detail = f"{pointer}: characters outside the {settings.request_charset} character set"
            raise ProblemError(400, "FORMAT_ERROR", detail, pointer)


def _check_client(payload: VopRequest, headers: Mapping[str, str], settings: Settings) -> None:
    bic = payload.requesting_agent.financial_institution_id.bicfi
    if settings.allowed_requesting_bics and bic not in settings.allowed_requesting_bics:
        detail = "the requesting PSP is not served by this responder"
        raise ProblemError(401, "CLIENT_INVALID", detail, "/requestingAgent")
    if settings.client_bic_header:
        verified = (headers.get(settings.client_bic_header) or "").strip().upper()
        if verified != bic:
            detail = "requestingAgent BIC does not match the authenticated client"
            raise ProblemError(401, "CLIENT_INCONSISTENT", detail, "/requestingAgent")


def _name_check(
    name: str, record: AccountRecord | None, settings: Settings, policy: str
) -> dict[str, str]:
    names = record.names[: settings.max_holder_names] if record else ()
    if not names:
        return {"partyNameMatch": "NOAP"}  # unknown or closed account
    verdict = match(name, names, policy=policy)
    code = _NAME_CODES[verdict.result]
    if code != "CMTC":
        return {"partyNameMatch": code}
    shown = verdict.suggested_name or ""
    if settings.latin_matched_name:
        latin = to_sepa_latin(shown)
        if latin is None:
            # The real name can't be written in the agreed character set (e.g.
            # Arabic only), so a close match can't be shown: verification not possible.
            return {"partyNameMatch": "NOAP"}
        shown = latin
    return {"partyNameMatch": "CMTC", "matchedName": shown[:140]}


def _id_check(organisation: OrganisationId, record: AccountRecord | None) -> str:
    if record is None:
        return "NOAP"
    scheme, value = organisation.scheme_and_value()
    known = record.identifiers.get(scheme)
    if known is None:
        return "NOAP"  # identifier not available for this payee (section 4.2.6)
    return "MTCH" if _canon(known) == _canon(value) else "NMTC"


def _canon(identifier: str) -> str:
    return "".join(identifier.split()).upper()
