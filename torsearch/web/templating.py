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
    requests_store = getattr(request.app.state, "requests", None)
    pending = requests_store.count_pending() if (role == "admin" and requests_store) else 0
    return {
        "auth_enabled": enabled,
        "role": role,
        "is_admin": role == "admin",
        "is_member": role in ("admin", "member"),
        "pending_requests": pending,
    }


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_auth_context])
templates.env.globals["detect_quality"] = detect_quality
