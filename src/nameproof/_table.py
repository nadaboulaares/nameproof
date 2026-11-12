"""Read a list of names from CSV or plain text, and write duplicate groups back.

Shared by ``nameproof dedupe`` and the browser playground, so a file gives the
same result in both.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from nameproof.dedupe import DedupeReport

_BOM = "\ufeff"  # Excel starts UTF-8 CSV files with a byte-order mark


@dataclass(frozen=True, slots=True)
class Table:
    """Rows read from a file: original columns, file row numbers, and the name column."""

    header: list[str]
    rows: list[list[str]]
    numbers: list[int]
    column: int
    names: list[str]  # the name of every row ("" when a row is shorter than the header)


def _table(header: list[str], rows: list[list[str]], numbers: list[int], column: int) -> Table:
    names = [row[column] if column < len(row) else "" for row in rows]
    return Table(header, rows, numbers, column, names)


def read_table(text: str, *, plain: bool, column: str | None = None) -> Table:
    """Parse ``text``: one name per line if ``plain``, else CSV with a header row.

    The CSV delimiter (comma, semicolon or tab) is detected. Without ``column``,
    the only column or the one called "name" holds the names.

    Raises:
        ValueError: if the CSV is empty or the name column can't be found.

    """
    text = text.removeprefix(_BOM)
    if plain:
        lines = text.splitlines()
        return _table(
            ["name"], [[line.strip()] for line in lines], list(range(1, len(lines) + 1)), 0
        )
    header, rows, numbers = _csv_rows(text)
    index = name_column(header) if column is None else _named_column(header, column)
    if index is None:
        msg = f"choose the name column with --column; columns are: {', '.join(header)}"
        raise ValueError(msg)
    return _table(header, rows, numbers, index)


def csv_header(text: str) -> tuple[list[str], int | None, int]:
    """Return the header, the guessed name column (or ``None``) and the row count."""
    header, rows, _ = _csv_rows(text.removeprefix(_BOM))
    return header, name_column(header), len(rows)


def name_column(header: list[str]) -> int | None:
    """Guess the name column, or return ``None`` to ask.

    It is the only column, the one called "name", or the single column whose title
    mentions a name ("Full name", "Beneficiary name", "Nom", "الاسم").
    """
    folded = [title.strip().casefold() for title in header]
    if len(header) == 1:
        return 0
    if "name" in folded:
        return folded.index("name")
    mentions = [index for index, title in enumerate(folded) if _NAME_WORDS.search(title)]
    return mentions[0] if len(mentions) == 1 else None


_NAME_WORDS = re.compile(r"name|\bnom\b|nombre|nome|imię|jméno|név|όνομα|имя|ім'я|име|اسم")


def groups_csv(table: Table, report: DedupeReport) -> str:
    """CSV of the rows that have duplicates, with ``group``, ``review`` and ``row`` first."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["group", "review", "row", *table.header])
    for number, group in enumerate(report.groups, 1):
        review = "yes" if group.needs_review else "no"
        for index in group.members:
            writer.writerow([number, review, table.numbers[index], *table.rows[index]])
    return out.getvalue()


def _csv_rows(text: str) -> tuple[list[str], list[list[str]], list[int]]:
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(text[:4096], ",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(text.splitlines(), dialect)
    header = next(reader, None)
    if header is None:
        msg = "the file is empty"
        raise ValueError(msg)
    rows: list[list[str]] = []
    numbers: list[int] = []
    for row in reader:
        if any(cell.strip() for cell in row):
            rows.append(row)
            numbers.append(reader.line_num)
    return header, rows, numbers


def _named_column(header: list[str], column: str) -> int:
    folded = [name.strip().casefold() for name in header]
    wanted = column.strip().casefold()
    if wanted not in folded:
        msg = f"no column {column!r}; columns are: {', '.join(header)}"
        raise ValueError(msg)
    return folded.index(wanted)
