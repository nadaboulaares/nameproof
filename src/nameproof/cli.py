"""Command-line entry point (``nameproof``)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nameproof import __version__
from nameproof._table import Table, groups_csv, read_table
from nameproof.dedupe import DEDUPE_POLICY, MAX_GROUP, DedupeReport, find_duplicates
from nameproof.matcher import match
from nameproof.policy import DEFAULT_POLICY


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nameproof",
        description="Explainable name matching across scripts: same person, maybe, or different?",
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

    dedupe = commands.add_parser(
        "dedupe",
        help="find likely duplicates in a list of names",
        description=(
            "Find names in a list that likely belong to the same person or organisation, "
            "across scripts and spellings. Nothing leaves your computer."
        ),
    )
    dedupe.add_argument(
        "file", type=Path, help="CSV file with a header row, or a .txt file with one name per line"
    )
    dedupe.add_argument(
        "--column", help="CSV column with the names (default: the only column, or 'name')"
    )
    dedupe.add_argument("--policy", default=DEDUPE_POLICY, help="policy id (default: %(default)s)")
    dedupe.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="processes to compare with (default: all CPUs, %(default)s)",
    )
    dedupe.add_argument(
        "--max-group",
        type=int,
        default=MAX_GROUP,
        help="largest group of similar names compared with each other (default: %(default)s)",
    )
    dedupe.add_argument(
        "--output",
        type=Path,
        help="write the rows that have duplicates to this CSV, with group and review columns",
    )
    dedupe.add_argument("--json", action="store_true", help="print the full report as JSON")

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
    if args.command == "dedupe":
        return _run_dedupe(args)
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


def _run_dedupe(args: argparse.Namespace) -> int:
    try:
        table = read_table(
            args.file.read_text(encoding="utf-8-sig"),
            plain=args.file.suffix.lower() == ".txt",
            column=args.column,
        )
        report = find_duplicates(
            table.names, policy=args.policy, max_group=args.max_group, jobs=max(args.jobs, 1)
        )
        if args.output is not None:
            args.output.write_text(groups_csv(table, report), encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"nameproof: error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        payload = {"rows": table.numbers, **report.to_dict()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_dedupe(table, report)
    return 0


def _print_dedupe(table: Table, report: DedupeReport) -> None:
    review = sum(group.needs_review for group in report.groups)
    print(
        f"{len(report.groups)} groups of likely duplicates in {len(table.names)} names "
        f"({review} to review); {report.compared} pairs compared."
    )
    if report.unchecked:
        rows = ", ".join(str(table.numbers[index]) for index in report.unchecked[:20])
        more = " ..." if len(report.unchecked) > 20 else ""
        print(f"Not checked (empty, too long or unsupported script): rows {rows}{more}")
    if report.crowded_keys:
        print(
            f"Some very common names were not all compared ({report.crowded_keys}); "
            "a larger --max-group compares more."
        )
    links: dict[int, list[str]] = {}
    for pair in report.pairs:
        why = ", ".join(pair.explanation) or "identical"
        line = (
            f"    rows {table.numbers[pair.first]} & {table.numbers[pair.second]}: "
            f"{pair.result.value} ({why})"
        )
        links.setdefault(pair.first, []).append(line)
    for number, group in enumerate(report.groups, 1):
        print(f"\nGroup {number}" + (" (review)" if group.needs_review else ""))
        for index in group.members:
            print(f"  row {table.numbers[index]:>5}  {table.names[index]}")
        for index in group.members:
            for line in links.get(index, []):
                print(line)


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
