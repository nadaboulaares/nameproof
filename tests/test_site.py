import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

import chart

ROOT = Path(__file__).resolve().parent.parent


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("site_builder", ROOT / "playground" / "build.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_playground_build(tmp_path: Path) -> None:
    builder = _load_builder()
    (tmp_path / "playground").mkdir()
    for page in ("index.html", "dedupe.html", "style.css", "shared.js", "build.py"):
        (tmp_path / "playground" / page).write_text("x")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "nameproof-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
    site = tmp_path / "_site"
    wheel = builder.assemble(tmp_path, site)
    assert wheel.name == "nameproof-0.1.0-py3-none-any.whl"
    assert json.loads((site / "wheel.json").read_text()) == {"wheel": wheel.name}
    assert {page.name for page in site.iterdir()} == {
        "index.html",
        "dedupe.html",
        "style.css",
        "shared.js",
        "wheel.json",
        ".nojekyll",
        wheel.name,
    }
    assert (site / ".nojekyll").exists()


def test_playground_build_needs_a_wheel(tmp_path: Path) -> None:
    builder = _load_builder()
    with pytest.raises(FileNotFoundError, match="no wheel"):
        builder.assemble(tmp_path, tmp_path / "_site")


def test_playground_page_pins_pyodide_and_installs_without_deps() -> None:
    page = (ROOT / "playground" / "index.html").read_text()
    assert re.search(r"cdn\.jsdelivr\.net/pyodide/v[\d.]+/full/pyodide\.js", page)
    assert "deps=False" in page  # rapidfuzz has no browser build; nameproof falls back


def test_dedupe_worker_uses_the_same_pinned_pyodide() -> None:
    page = (ROOT / "playground" / "index.html").read_text()
    worker = (ROOT / "playground" / "dedupe-worker.js").read_text()
    dedupe = (ROOT / "playground" / "dedupe.html").read_text()
    pinned = re.search(r"pyodide/(v[\d.]+)/full/pyodide\.js", page)
    assert pinned is not None
    assert f"pyodide/{pinned.group(1)}/full/" in worker
    assert re.search(r'PYODIDE_MJS_SRI = "sha384-[A-Za-z0-9+/]{64}"', worker)
    assert "integrity: PYODIDE_MJS_SRI" in worker
    assert "deps=False" in worker
    assert 'new Worker("dedupe-worker.js", { type: "module" })' in dedupe


def test_chart_render() -> None:
    systems = chart.SYSTEMS
    rejected = dict(zip(systems, (0.09, 0.638, 0.765, 0.898), strict=True))
    matched = dict(zip(systems, (0.431, 0.262, 0.113, 0.102), strict=True))
    svg = chart.render(chart.LIGHT, rejected, matched, 2250)
    assert svg.startswith("<svg")
    assert 'role="img"' in svg
    assert "9.0%" in svg
    assert "89.8%" in svg  # long bars carry their label inside
    assert "n = 2,250" in svg
    assert chart.LIGHT.bar in svg
    assert chart.DARK.bar in chart.render(chart.DARK, rejected, matched, 2250)
    widest_text = max(float(x) for x in re.findall(r'<text x="([\d.]+)"', svg))
    assert widest_text + 36 < chart.WIDTH  # nothing runs off the image


def test_chart_bar_has_rounded_data_end() -> None:
    assert chart._bar(0, 0, 0, "#000") == ""
    path = chart._bar(10, 5, 100, "#000")
    assert path.count(" a4,4 ") == 2
