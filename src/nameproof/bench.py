"""Benchmark runner: score nameproof and simple baselines on labelled name pairs.

The dataset is JSONL, one pair per line::

    {"id": "greek-0001", "slice": "greek", "variation": "native_script",
     "label": "same", "provided": "Maria Callas", "account": "Μαρία Κάλλας"}

``label`` is ``"same"`` (same person or company) or ``"different"``.
"""

from __future__ import annotations

import json
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from nameproof._types import MatchResult
from nameproof.matcher import match

Matcher = Callable[[str, str], MatchResult]

LABELS = ("same", "different")

# Thresholds for the similarity baselines: the typical "fuzzy score" setup.
BASELINE_MATCH = 0.95
BASELINE_CLOSE = 0.85


@dataclass(frozen=True, slots=True)
class Case:
    """One labelled pair."""

    id: str
    slice: str
    variation: str
    label: str
    provided: str
    account: str


def load_cases(path: Path) -> list[Case]:
    """Read and validate a JSONL benchmark file."""
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        try:
            case = Case(
                id=str(record["id"]),
                slice=str(record["slice"]),
                variation=str(record["variation"]),
                label=str(record["label"]),
                provided=str(record["provided"]),
                account=str(record["account"]),
            )
        except KeyError as exc:
            msg = f"{path}:{number}: missing field {exc}"
            raise ValueError(msg) from None
        if case.label not in LABELS:
            msg = f"{path}:{number}: label must be one of {LABELS}, got {case.label!r}"
            raise ValueError(msg)
        cases.append(case)
    return cases


# --- systems -----------------------------------------------------------------


def nameproof_matcher(provided: str, account: str) -> MatchResult:
    """Run nameproof with the default policy."""
    return match(provided, [account]).result


def _plain(text: str) -> str:
    return " ".join(text.casefold().split())


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _plain(text))
    return "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))


def _threshold(similarity: float) -> MatchResult:
    if similarity >= BASELINE_MATCH:
        return MatchResult.MATCH
    if similarity >= BASELINE_CLOSE:
        return MatchResult.CLOSE_MATCH
    return MatchResult.NO_MATCH


def exact_baseline(provided: str, account: str) -> MatchResult:
    """Case- and whitespace-insensitive string equality."""
    return MatchResult.MATCH if _plain(provided) == _plain(account) else MatchResult.NO_MATCH


def levenshtein_baseline(provided: str, account: str) -> MatchResult:
    """Normalised Levenshtein similarity with fixed thresholds."""
    return _threshold(Levenshtein.normalized_similarity(_plain(provided), _plain(account)))


def token_sort_baseline(provided: str, account: str) -> MatchResult:
    """Diacritic-folded, order-insensitive fuzzy ratio with fixed thresholds."""
    return _threshold(fuzz.token_sort_ratio(_ascii(provided), _ascii(account)) / 100)


SYSTEMS: dict[str, Matcher] = {
    "nameproof": nameproof_matcher,
    "exact": exact_baseline,
    "levenshtein": levenshtein_baseline,
    "token-sort": token_sort_baseline,
}


# --- scoring -----------------------------------------------------------------


@dataclass(slots=True)
class Tally:
    """Counts of each verdict for a group of pairs."""

    counts: dict[MatchResult, int] = field(default_factory=lambda: dict.fromkeys(MatchResult, 0))

    def add(self, result: MatchResult) -> None:
        """Count one verdict."""
        self.counts[result] += 1

    @property
    def total(self) -> int:
        """Number of pairs counted."""
        return sum(self.counts.values())

    def rate(self, *results: MatchResult) -> float:
        """Share of pairs whose verdict is one of ``results``."""
        return sum(self.counts[r] for r in results) / self.total if self.total else 0.0


@dataclass(slots=True)
class Report:
    """Verdict counts per system, slice and label, plus nameproof latency."""

    tallies: dict[tuple[str, str, str], Tally]
    systems: tuple[str, ...]
    slices: tuple[str, ...]
    latencies_ms: list[float]
    by_variation: dict[tuple[str, str, str], Tally] = field(default_factory=dict)
    variations: tuple[tuple[str, str], ...] = ()

    def tally(self, system: str, label: str, slice_: str | None = None) -> Tally:
        """Tally for one slice, or summed over all slices when ``slice_`` is None."""
        if slice_ is not None:
            return self.tallies.get((system, slice_, label), Tally())
        total = Tally()
        for name in self.slices:
            for result, count in self.tally(system, label, name).counts.items():
                total.counts[result] += count
        return total

    def latency(self, quantile: float) -> float:
        """Latency of nameproof at ``quantile`` (0-1), in milliseconds."""
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        return ordered[min(len(ordered) - 1, int(quantile * len(ordered)))]


def run(cases: Sequence[Case], systems: Mapping[str, Matcher] = SYSTEMS) -> Report:
    """Run every system on every case."""
    tallies: dict[tuple[str, str, str], Tally] = {}
    by_variation: dict[tuple[str, str, str], Tally] = {}
    latencies: list[float] = []
    for case in cases:
        for name, matcher in systems.items():
            start = time.perf_counter()
            result = matcher(case.provided, case.account)
            if name == "nameproof":
                latencies.append((time.perf_counter() - start) * 1000)
            tallies.setdefault((name, case.slice, case.label), Tally()).add(result)
            by_variation.setdefault((name, case.variation, case.label), Tally()).add(result)
    slices = tuple(dict.fromkeys(case.slice for case in cases))
    variations = tuple(sorted({(case.label, case.variation) for case in cases}, reverse=True))
    return Report(tallies, tuple(systems), slices, latencies, by_variation, variations)


# --- output ------------------------------------------------------------------

_M, _C, _N, _X = (
    MatchResult.MATCH,
    MatchResult.CLOSE_MATCH,
    MatchResult.NO_MATCH,
    MatchResult.NOT_POSSIBLE,
)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _table(report: Report, label: str, metric: Callable[[Tally], float]) -> list[str]:
    header = ["slice", *report.systems]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for slice_ in (*report.slices, None):
        cells = [_pct(metric(report.tally(system, label, slice_))) for system in report.systems]
        name = "**all**" if slice_ is None else slice_
        lines.append("| " + " | ".join([name, *cells]) + " |")
    return lines


def _variation_table(report: Report, system: str) -> list[str]:
    lines = [
        f"**{system} by variation** (share of each verdict)",
        "",
        "| label | variation | n | MATCH | CLOSE | NO | NOT POSSIBLE |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, variation in report.variations:
        tally = report.by_variation.get((system, variation, label), Tally())
        rates = [_pct(tally.rate(result)) for result in (_M, _C, _N, _X)]
        lines.append(f"| {label} | {variation} | {tally.total} | " + " | ".join(rates) + " |")
    return [*lines, ""]


def render_markdown(report: Report) -> str:
    """Render the headline tables as GitHub-flavoured Markdown."""
    same_n = report.tally(report.systems[0], "same").total
    different_n = report.tally(report.systems[0], "different").total
    parts = [
        "**Same person/company: wrongly rejected** "
        f"(NO_MATCH or NOT_POSSIBLE; n={same_n}, lower is better)",
        "",
        *_table(report, "same", lambda t: t.rate(_N, _X)),
        "",
        f"**Same person/company: auto-matched** (MATCH; n={same_n}, higher is better)",
        "",
        *_table(report, "same", lambda t: t.rate(_M)),
        "",
        f"**Different people/companies: false MATCH** (n={different_n}, lower is better)",
        "",
        *_table(report, "different", lambda t: t.rate(_M)),
        "",
        *_variation_table(report, report.systems[0]),
        f"{report.systems[0]} latency: p50 {report.latency(0.5):.2f} ms, "
        f"p95 {report.latency(0.95):.2f} ms",
    ]
    return "\n".join(parts) + "\n"


def to_dict(report: Report) -> dict[str, object]:
    """JSON-serialisable report: rates per system, label and slice."""
    out: dict[str, object] = {}
    for system in report.systems:
        per_label: dict[str, object] = {}
        for label in LABELS:
            groups: dict[str, object] = {}
            for slice_ in (*report.slices, None):
                tally = report.tally(system, label, slice_)
                groups["all" if slice_ is None else slice_] = {
                    "n": tally.total,
                    **{result.value: tally.rate(result) for result in MatchResult},
                }
            per_label[label] = groups
        out[system] = per_label
    out["latency_ms"] = {"p50": report.latency(0.5), "p95": report.latency(0.95)}
    return out


def select_systems(names: Iterable[str]) -> dict[str, Matcher]:
    """Pick systems by name, rejecting unknown ones."""
    chosen: dict[str, Matcher] = {}
    for name in names:
        if name not in SYSTEMS:
            msg = f"unknown system {name!r}; available: {', '.join(SYSTEMS)}"
            raise ValueError(msg)
        chosen[name] = SYSTEMS[name]
    return chosen
