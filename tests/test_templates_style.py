import re

from torsearch.web.templating import TEMPLATES_DIR

# Tailwind only generates opacity modifiers on its scale (multiples of 5): "bg-slate-900/98"
# silently produces no CSS, i.e. a transparent dropdown on phones.
_OPACITY = re.compile(r"\b(?:bg|text|border|ring|from|to|via|shadow)-[a-z]+(?:-\d+)?/(\d+)\b")


def test_tailwind_opacity_modifiers_are_on_the_scale():
    bad = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        for m in _OPACITY.finditer(path.read_text()):
            if int(m.group(1)) % 5:
                bad.append(f"{path.name}: {m.group(0)}")
    assert bad == []


def test_base_layout_never_widens_on_phones():
    base = (TEMPLATES_DIR / "base.html").read_text()
    assert "overflow-x: clip" in base
    assert "safe-area-inset-bottom" in base
