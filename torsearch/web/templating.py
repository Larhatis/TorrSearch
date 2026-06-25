from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from torsearch.search.filters import detect_quality

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _auth_context(request):
    from torsearch.web.authz import effective_role

    auth = getattr(request.app.state, "auth", None)
    enabled = bool(auth and getattr(auth, "enabled", False))
    role = effective_role(request)
    return {
        "auth_enabled": enabled,
        "role": role,
        "is_admin": role == "admin",
        "is_member": role in ("admin", "member"),
    }


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_auth_context])
templates.env.globals["detect_quality"] = detect_quality
