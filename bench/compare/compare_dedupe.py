"""Compare nameproof dedupe with fuzzy matching and Splink on arabic-dedupe-v1.

Every system gets the same 13k names and must group the records of the same person.
Scores are computed on the groups: every pair of records placed in one group is a
predicted duplicate. The baselines are given every advantage nameproof is not:

- Arabic is transliterated to Latin letters first (anyascii), since neither fuzzy
  matching nor Splink compares scripts;
- their threshold and grouping (chained or complete linkage) are tuned on the
  answers (the best F1), while nameproof runs with its defaults.

    uv venv /tmp/cmp && VIRTUAL_ENV=/tmp/cmp uv pip install splink anyascii rapidfuzz pandas -e .
    /tmp/cmp/bin/python bench/compare/compare_dedupe.py
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from itertools import combinations
from pathlib import Path

import numpy as np
from anyascii import anyascii
from rapidfuzz import fuzz, process

from nameproof.dedupe import find_duplicates

DATA = Path(__file__).resolve().parent.parent / "data" / "arabic-dedupe-v1.jsonl"
Pair = tuple[int, int]


def load(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Return names, the person of each record, and each record's language."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [r["name"] for r in rows], [r["person"] for r in rows], [r["lang"] for r in rows]


def truth_pairs(people: Sequence[str]) -> set[Pair]:
    """Every pair of records of the same person."""
    by_person: dict[str, list[int]] = defaultdict(list)
    for index, person in enumerate(people):
        by_person[person].append(index)
    return {pair for members in by_person.values() for pair in combinations(members, 2)}


def components(edges: Iterable[Pair], size: int) -> list[list[int]]:
    """Group records by chaining links (connected components)."""
    parent = list(range(size))

    def root(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left, right in edges:
        a, b = root(left), root(right)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups: dict[int, list[int]] = defaultdict(list)
    for item in range(size):
        groups[root(item)].append(item)
    return [members for members in groups.values() if len(members) > 1]


def complete_link(edges: dict[Pair, float], size: int) -> list[list[int]]:
    """Group records so that every two members are linked (strongest links first)."""
    group_of = list(range(size))
    members: dict[int, list[int]] = {}
    for (first, second), _ in sorted(edges.items(), key=lambda item: -item[1]):
        left_head, right_head = group_of[first], group_of[second]
        if left_head == right_head:
            continue
        left, right = members.get(left_head, [first]), members.get(right_head, [second])
        if all((min(a, b), max(a, b)) in edges for a in left for b in right):
            head = min(left_head, right_head)
            members.pop(max(left_head, right_head), None)
            members[head] = left + right
            for item in members[head]:
                group_of[item] = head
    return list(members.values())


def group_pairs(groups: Iterable[Sequence[int]]) -> set[Pair]:
    """Every pair of records placed in one group."""
    return {pair for members in groups for pair in combinations(sorted(members), 2)}


def score(predicted: set[Pair], truth: set[Pair], langs: Sequence[str]) -> dict[str, float]:
    """Precision, recall and F1 of predicted pairs, with recall by script."""
    hits = predicted & truth
    precision = len(hits) / len(predicted) if predicted else 0.0
    recall = len(hits) / len(truth)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    cross = {pair for pair in truth if "ar" in (langs[pair[0]], langs[pair[1]])}
    latin = truth - cross
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "recall_arabic_latin": len(hits & cross) / len(cross),
        "recall_latin_latin": len(hits & latin) / len(latin),
        "predicted_pairs": len(predicted),
    }


def best_threshold(
    scored: dict[Pair, float], thresholds: Iterable[float], size: int, truth: set[Pair],
    langs: Sequence[str],
) -> tuple[float, dict[str, float]]:  # fmt: skip
    """Pick the threshold and grouping with the best F1 (tuned on the answers: generous)."""
    best: tuple[float, dict[str, float]] | None = None
    for threshold in thresholds:
        edges = {pair: value for pair, value in scored.items() if value >= threshold}
        for grouping in (components(edges, size), complete_link(edges, size)):
            result = score(group_pairs(grouping), truth, langs)
            if best is None or result["f1"] > best[1]["f1"]:
                best = (threshold, result)
    assert best is not None  # noqa: S101
    return best


def run_nameproof(names: list[str], jobs: int) -> tuple[list[list[int]], list[list[int]]]:
    """All groups, and the groups made of MATCH links only."""
    report = find_duplicates(names, jobs=jobs)
    flagged = [list(group.members) for group in report.groups]
    auto = components(
        ((pair.first, pair.second) for pair in report.pairs if pair.result.value == "MATCH"),
        len(names),
    )
    return flagged, auto


def latin(name: str) -> str:
    """Latin letters for the baselines (anyascii), lower case, single spaces."""
    return " ".join(anyascii(name).casefold().replace("-", " ").replace("'", "").split())


def run_fuzzy(names: list[str]) -> dict[Pair, float]:
    """Token-sort ratio of every pair (vectorised), keeping scores of 60 and above."""
    texts = [latin(name) for name in names]
    matrix = process.cdist(
        texts, texts, scorer=fuzz.token_sort_ratio, dtype=np.uint8, score_cutoff=60, workers=-1
    )
    rows, cols = np.nonzero(np.triu(matrix, k=1))
    return {(int(r), int(c)): float(matrix[r, c]) for r, c in zip(rows, cols, strict=True)}


def run_splink(names: list[str]) -> dict[Pair, float]:
    """Splink with name-only comparisons, trained without labels (as in real use)."""
    import pandas as pd  # noqa: PLC0415
    import splink.comparison_library as cl  # noqa: PLC0415
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on  # noqa: PLC0415

    texts = [latin(name) for name in names]
    frame = pd.DataFrame(  # noqa: F841 - read by name in the DuckDB SQL below
        {
            "unique_id": range(len(names)),
            "full_name": texts,
            "first_name": [text.split()[0] for text in texts],
            "surname": [text.split()[-1] for text in texts],
        }
    )
    settings = SettingsCreator(
        link_type="dedupe_only",
        comparisons=[
            cl.JaroWinklerAtThresholds("full_name", [0.95, 0.88, 0.8]),
            cl.NameComparison("first_name"),
            cl.NameComparison("surname"),
        ],
        blocking_rules_to_generate_predictions=[
            block_on("first_name"),
            block_on("surname"),
            block_on("substr(full_name, 1, 3)"),
        ],
    )
    # Splink 5 turns Python lists and dicts into tables with pyarrow; build them with
    # pandas instead when pyarrow isn't installed (same table, nothing else changes).
    import duckdb  # noqa: PLC0415
    import splink.internals.duckdb.database_api as splink_duckdb  # noqa: PLC0415

    try:
        import pyarrow  # noqa: F401, PLC0415
    except ImportError:
        splink_duckdb.to_pyarrow_if_list_tuple_or_dict = lambda table: (
            pd.DataFrame(table) if isinstance(table, list | tuple | dict) else table
        )

    connection = duckdb.connect()
    connection.execute("CREATE TABLE names AS SELECT * FROM frame")
    linker = Linker(DuckDBAPI(connection).register("names"), settings)
    linker.training.estimate_probability_two_random_records_match(
        [block_on("full_name")], recall=0.5
    )
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("first_name"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("surname"))
    # A third pass so every comparison gets m values (each pass can't train its block).
    linker.training.estimate_parameters_using_expectation_maximisation(
        block_on("substr(full_name, 1, 3)")
    )
    predictions = linker.inference.predict(threshold_match_probability=0.01).as_pandas_dataframe()
    return {
        (min(int(a), int(b)), max(int(a), int(b))): float(p)
        for a, b, p in zip(
            predictions["unique_id_l"], predictions["unique_id_r"],
            predictions["match_probability"], strict=True,
        )
    }  # fmt: skip


def main() -> None:
    """Run every system and print a Markdown table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--skip-splink", action="store_true")
    parser.add_argument("--json", type=Path, help="also write the results here")
    args = parser.parse_args()

    names, people, langs = load(DATA)
    truth = truth_pairs(people)
    print(f"{len(names)} records, {len(set(people))} people, {len(truth)} duplicate pairs\n")
    results: dict[str, dict[str, float]] = {}

    start = time.perf_counter()
    flagged, auto = run_nameproof(names, args.jobs)
    seconds = time.perf_counter() - start
    results["nameproof (all groups, defaults)"] = {
        **score(group_pairs(flagged), truth, langs), "seconds": seconds,
    }  # fmt: skip
    results["nameproof (MATCH only, defaults)"] = score(group_pairs(auto), truth, langs)

    start = time.perf_counter()
    fuzzy = run_fuzzy(names)
    threshold, result = best_threshold(fuzzy, range(60, 101, 2), len(names), truth, langs)
    results[f"fuzzy token-sort, best threshold {threshold}"] = {
        **result, "seconds": time.perf_counter() - start,
    }  # fmt: skip

    if not args.skip_splink:
        start = time.perf_counter()
        splink = run_splink(names)
        thresholds = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99]
        threshold, result = best_threshold(splink, thresholds, len(names), truth, langs)
        results[f"Splink, best threshold {threshold}"] = {
            **result, "seconds": time.perf_counter() - start,
        }  # fmt: skip

    print("| system | precision | recall | F1 | recall Arabic↔Latin | recall Latin↔Latin |")
    print("|---|---|---|---|---|---|")
    for system, row in results.items():
        print(
            f"| {system} | {row['precision']:.1%} | {row['recall']:.1%} | {row['f1']:.1%} | "
            f"{row['recall_arabic_latin']:.1%} | {row['recall_latin_latin']:.1%} |"
        )
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
