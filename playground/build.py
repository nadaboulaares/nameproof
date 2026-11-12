"""Assemble the static site (playground) into ``_site/``.

    uv build --wheel --out-dir dist
    uv run python playground/build.py

The playground loads Pyodide from the jsDelivr CDN and installs the nameproof wheel
copied next to it, so nothing a visitor types is sent anywhere.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"


def assemble(root: Path, site: Path) -> Path:
    """Copy the pages and the newest wheel from ``root`` into ``site``; return the wheel."""
    wheels = sorted((root / "dist").glob("nameproof-*-py3-none-any.whl"))
    if not wheels:
        msg = "no wheel in dist/: run `uv build --wheel --out-dir dist` first"
        raise FileNotFoundError(msg)
    wheel = wheels[-1]
    shutil.rmtree(site, ignore_errors=True)
    site.mkdir(parents=True)
    for page in sorted((root / "playground").iterdir()):
        if page.suffix in {".html", ".css", ".js"}:
            shutil.copy2(page, site / page.name)
    shutil.copy2(wheel, site / wheel.name)
    (site / "wheel.json").write_text(json.dumps({"wheel": wheel.name}) + "\n")
    (site / ".nojekyll").touch()
    return wheel


def main() -> int:
    """Build ``_site/`` from this checkout."""
    try:
        wheel = assemble(ROOT, SITE)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"built {SITE} with {wheel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
