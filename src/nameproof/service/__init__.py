"""EPC Verification of Payee responder service (``pip install "nameproof[service]"``)."""

from nameproof.service.directory import (
    AccountDirectory,
    AccountRecord,
    InMemoryDirectory,
    json_directory,
    load_directory,
)
from nameproof.service.settings import Settings

__all__ = [
    "AccountDirectory",
    "AccountRecord",
    "InMemoryDirectory",
    "Settings",
    "create_app",
    "json_directory",
    "load_directory",
]


def create_app(*args: object, **kwargs: object) -> object:
    """Build the FastAPI app (imported lazily so the core library needs no web stack)."""
    try:
        from nameproof.service.app import create_app as build  # noqa: PLC0415
    except ImportError as error:  # pragma: no cover - depends on installed extras
        msg = 'the service needs extra dependencies: pip install "nameproof[service]"'
        raise ImportError(msg) from error
    return build(*args, **kwargs)  # type: ignore[arg-type]
