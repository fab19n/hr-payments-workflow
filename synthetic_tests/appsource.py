"""The page script's source for tests that read it as text.

The page script is a set of plain scripts under static/js/, listed in the order they run by the <script> tags in
static/index.html (no build step; they share one scope). app_files() gives their paths in that order; app_source()
gives them joined as one text, which is what the single static/app.js used to be.
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def app_files():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    names = re.findall(r'<script src="/static/(js/[^"]+)"></script>', html)
    assert names, "static/index.html lists no page scripts"
    return [STATIC / n for n in names]


def app_source():
    return "\n".join(p.read_text(encoding="utf-8") for p in app_files())


def app_bundle(dest):
    """The page script as one file at dest (for a test that runs it in Node), and the path as text."""
    Path(dest).write_text(app_source(), encoding="utf-8")
    return str(dest)
