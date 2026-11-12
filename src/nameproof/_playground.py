"""Entry points for the browser playground, called from a Web Worker through Pyodide.

Everything takes and returns JSON text, so JavaScript never handles Python objects.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from nameproof._table import csv_header, groups_csv, read_table
from nameproof.dedupe import find_duplicates


def inspect_csv(text: str) -> str:
    """Describe a CSV file: its columns, the guessed name column and the row count."""
    header, column, rows = csv_header(text)
    return json.dumps({"header": header, "column": column, "rows": rows})


def find_in_text(
    text: str,
    plain: bool,
    column: str | None = None,
    progress: Callable[[int, int], object] | None = None,
) -> str:
    """Find duplicates in a pasted list or an uploaded CSV; return groups and a result CSV."""
    table = read_table(text, plain=plain, column=column)
    report = find_duplicates(table.names, progress=progress)
    links: dict[int, list[tuple[int, dict[str, object]]]] = {}
    for pair in report.pairs:
        links.setdefault(pair.first, []).append(
            (
                pair.second,
                {
                    "rows": [table.numbers[pair.first], table.numbers[pair.second]],
                    "result": pair.result.value,
                    "explanation": list(pair.explanation),
                },
            )
        )
    groups = [
        {
            "review": group.needs_review,
            "members": [
                {"row": table.numbers[index], "name": table.names[index]} for index in group.members
            ],
            "links": [
                link
                for index in group.members
                for second, link in links.get(index, [])
                if second in group.members
            ],
        }
        for group in report.groups
    ]
    return json.dumps(
        {
            "names": len(table.names),
            "compared": report.compared,
            "unchecked": [table.numbers[index] for index in report.unchecked],
            "crowded": report.crowded_keys,
            "policy": report.policy_version,
            "groups": groups,
            "csv": groups_csv(table, report),
        },
        ensure_ascii=False,
    )
