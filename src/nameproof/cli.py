"""Command-line entry point (``nameproof``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nameproof import __version__
from nameproof.matcher import match
from nameproof.policy import DEFAULT_POLICY


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nameproof",
        description="Explainable name matching across scripts for payments.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    check = commands.add_parser(
        "match",
        help="check a provided name against the account holder name(s)",
        description="Check a provided name against the account holder name(s).",
    )
    check.add_argument("provided", help="the name the payer typed")
    check.add_argument("account", nargs="+", help="name(s) registered on the account")
    check.add_argument("--policy", default=DEFAULT_POLICY, help="policy id (default: %(default)s)")
    check.add_argument("--json", action="store_true", help="print the verdict as JSON")

    bench = commands.add_parser(
        "bench",
        help="score nameproof and baselines on a labelled JSONL benchmark",
        description="Score nameproof and simple baselines on a labelled JSONL benchmark.",
    )
    bench.add_argument("dataset", type=Path, help="JSONL file of labelled name pairs")
    bench.add_argument(
        "--systems",
        default="nameproof,exact,levenshtein,token-sort",
        help="comma-separated systems to compare (default: %(default)s)",
    )
    bench.add_argument("--json", action="store_true", help="print rates as JSON")

    serve = commands.add_parser(
        "serve",
        help="run the EPC Verification of Payee responder service",
        description=(
            'Run the HTTP service (needs `pip install "nameproof[service]"`). '
            "Configure it with NAMEPROOF_* environment variables; see docs/SERVICE.md."
        ),
    )
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: %(default)s)")
    serve.add_argument("--port", type=int, default=8080, help="port (default: %(default)s)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "match":
        return _run_match(args.provided, args.account, policy=args.policy, as_json=args.json)
    if args.command == "bench":
        return _run_bench(args.dataset, args.systems.split(","), as_json=args.json)
    if args.command == "serve":
        return _run_serve(args.host, args.port)
    parser.print_help()
    return 0


def _run_match(provided: str, accounts: list[str], *, policy: str, as_json: bool) -> int:
    try:
        verdict = match(provided, accounts, policy=policy)
    except ValueError as exc:
        print(f"nameproof: error: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(verdict.to_dict(), ensure_ascii=False))
        return 0
    print(f"{verdict.result.value}  score={verdict.score:.4f}  policy={verdict.policy_version}")
    if verdict.suggested_name is not None:
        print(f"  suggested name: {verdict.suggested_name}")
    if verdict.explanation:
        print(f"  why: {', '.join(verdict.explanation)}")
    return 0


def _run_bench(dataset: Path, systems: list[str], *, as_json: bool) -> int:
    from nameproof import bench  # noqa: PLC0415 - keep `nameproof match` startup lean

    try:
        chosen = bench.select_systems(name.strip() for name in systems)
        report = bench.run(bench.load_cases(dataset), chosen)
    except (OSError, ValueError) as exc:
        print(f"nameproof: error: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(bench.to_dict(report), indent=2))
    else:
        print(bench.render_markdown(report), end="")
    return 0


def _run_serve(host: str, port: int) -> int:  # pragma: no cover - starts a server
    try:
        import uvicorn  # noqa: PLC0415

        from nameproof.service.app import create_app  # noqa: PLC0415
    except ImportError:
        print('nameproof: error: install the service extra: pip install "nameproof[service]"',
              file=sys.stderr)  # fmt: skip
        return 2
    import logging  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(create_app(), host=host, port=port, log_level="info", server_header=False)
    return 0
