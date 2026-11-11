"""Render the README benchmark chart (light and dark SVG) from the benchmark itself.

    uv run python bench/chart.py

Writes docs/assets/benchmark-light.svg and docs/assets/benchmark-dark.svg. Each panel
is one measure, so every bar shares one validated hue and the system names on the
axis carry identity; nameproof is emphasised with bold text, not color.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from nameproof._types import MatchResult
from nameproof.bench import load_cases, run

HERE = Path(__file__).parent
DATASET = HERE / "data" / "nameproof-bench-v1.jsonl"
OUT = HERE.parent / "docs" / "assets"
SYSTEMS = ("nameproof", "token-sort", "levenshtein", "exact")
LABELS = {"nameproof": "nameproof", "token-sort": "token-sort", "levenshtein": "Levenshtein",
          "exact": "exact match"}  # fmt: skip


@dataclass(frozen=True)
class Theme:
    """Chart tokens for one color scheme (dataviz reference palette)."""

    name: str
    surface: str
    text_primary: str
    text_secondary: str
    muted: str
    grid: str
    baseline: str
    bar: str


LIGHT = Theme("light", "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6")
DARK = Theme("dark", "#1a1a19", "#ffffff", "#c3c2b7", "#898781", "#2c2c2a", "#383835", "#3987e5")

FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
BAR_H, BAR_GAP, RADIUS = 20, 12, 4
LABEL_W, PANEL_W, PANEL_GAP, MARGIN = 104, 270, 56, 28
INSIDE_LABEL = 0.8  # bars longer than this share of the axis carry their label inside
TOP = 78
WIDTH = MARGIN * 2 + 2 * (LABEL_W + PANEL_W) + PANEL_GAP + 24  # + room for "100%"
HEIGHT = 292


def _bar(x: float, y: float, length: float, color: str) -> str:
    """Horizontal bar: square on the baseline, 4px rounded data end."""
    if length <= 0:
        return ""
    r = min(RADIUS, length)
    return (
        f'<path d="M{x:.1f},{y:.1f} h{length - r:.1f} a{r},{r} 0 0 1 {r},{r} '
        f'v{BAR_H - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{length - r:.1f} z" fill="{color}"/>'
    )


def _panel(theme: Theme, x0: float, title: str, note: str, values: dict[str, float]) -> str:
    parts = [
        f'<text x="{x0}" y="40" font-size="15" font-weight="600" fill="{theme.text_primary}">'
        f"{escape(title)}</text>",
        f'<text x="{x0}" y="60" font-size="12.5" fill="{theme.text_secondary}">'
        f"{escape(note)}</text>",
    ]
    plot_x = x0 + LABEL_W
    plot_bottom = TOP + len(SYSTEMS) * (BAR_H + BAR_GAP) - BAR_GAP
    for tick in (0, 50, 100):
        tx = plot_x + PANEL_W * tick / 100
        color = theme.baseline if tick == 0 else theme.grid
        parts.append(
            f'<line x1="{tx:.1f}" y1="{TOP - 6}" x2="{tx:.1f}" y2="{plot_bottom + 6}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{tx:.1f}" y="{plot_bottom + 22}" font-size="11.5" text-anchor="middle" '
            f'fill="{theme.muted}">{tick}%</text>'
        )
    for index, system in enumerate(SYSTEMS):
        y = TOP + index * (BAR_H + BAR_GAP)
        value = values[system]
        weight = "700" if system == "nameproof" else "400"
        parts.append(
            f'<text x="{plot_x - 10}" y="{y + BAR_H / 2 + 4.5}" font-size="13" '
            f'font-weight="{weight}" text-anchor="end" fill="{theme.text_primary}">'
            f"{LABELS[system]}</text>"
        )
        length = PANEL_W * value
        parts.append(f"<g><title>{LABELS[system]}: {value * 100:.1f}%</title>")
        parts.append(_bar(plot_x, y, length, theme.bar))
        parts.append("</g>")
        inside = value > INSIDE_LABEL
        label_x = plot_x + length - 8 if inside else plot_x + length + 6
        anchor = "end" if inside else "start"
        label_color = theme.surface if inside else theme.text_secondary
        parts.append(
            f'<text x="{label_x:.1f}" y="{y + BAR_H / 2 + 4.5}" font-size="12.5" '
            f'font-weight="{weight}" text-anchor="{anchor}" fill="{label_color}">'
            f"{value * 100:.1f}%</text>"
        )
    return "\n".join(parts)


def render(theme: Theme, rejected: dict[str, float], matched: dict[str, float], n: int) -> str:
    """Return the SVG document for ``theme``."""
    left = MARGIN
    right = left + LABEL_W + PANEL_W + PANEL_GAP
    caption = (
        f"Different people falsely matched (fraud risk): 0.0% for every system, n = {n:,}. "
        "Data: nameproof-bench v1, 6,000 Wikidata name pairs."
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}" role="img" '
        f'aria-labelledby="t d">\n'
        f'<title id="t">nameproof benchmark versus fuzzy-matching baselines</title>\n'
        f'<desc id="d">Same person wrongly rejected: '
        + ", ".join(f"{LABELS[s]} {rejected[s] * 100:.1f}%" for s in SYSTEMS)
        + ". Same person auto-matched: "
        + ", ".join(f"{LABELS[s]} {matched[s] * 100:.1f}%" for s in SYSTEMS)
        + f". {escape(caption)}</desc>\n"
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="10" fill="{theme.surface}"/>\n'
        + _panel(theme, left, "Same person wrongly rejected", "lower is better", rejected)
        + "\n"
        + _panel(theme, right, "Same person auto-matched", "higher is better", matched)
        + f'\n<text x="{left}" y="{HEIGHT - 18}" font-size="12" fill="{theme.text_secondary}">'
        f"{escape(caption)}</text>\n</svg>\n"
    )


def main() -> None:
    """Run the benchmark and write both SVGs."""
    report = run(load_cases(DATASET))
    rejected, matched = {}, {}
    for system in SYSTEMS:
        same = report.tally(system, "same")
        rejected[system] = same.rate(MatchResult.NO_MATCH, MatchResult.NOT_POSSIBLE)
        matched[system] = same.rate(MatchResult.MATCH)
        false_match = report.tally(system, "different").rate(MatchResult.MATCH)
        if false_match:
            msg = f"{system} has false matches ({false_match:.2%}); update the caption"
            raise SystemExit(msg)
    n = report.tally("nameproof", "different").total
    OUT.mkdir(parents=True, exist_ok=True)
    for theme in (LIGHT, DARK):
        path = OUT / f"benchmark-{theme.name}.svg"
        path.write_text(render(theme, rejected, matched, n), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
