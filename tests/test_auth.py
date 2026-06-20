from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


class _FakeSearch:
    indexers: list = []

    async def search(self, query, category):
        return []


class _FakeContext:
    def __init__(self):
        self.search_service = _FakeSearch()
        self.transmission = None
        self.config = Config()


def _client(auth: AuthSettings) -> TestClient:
    return TestClient(create_app(_FakeContext(), auth=auth))


_ENABLED = AuthSettings(
    enabled=True, username="admin", password="s3cret", secret_key="test-key"
)


def test_disabled_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("TORSEARCH_USERNAME", raising=False)
    monkeypatch.delenv("TORSEARCH_PASSWORD", raising=False)
    auth = AuthSettings.from_env(data_dir="/tmp/does-not-matter")
    assert auth.enabled is False


def test_disabled_when_only_username(monkeypatch):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.delenv("TORSEARCH_PASSWORD", raising=False)
    assert AuthSettings.from_env(data_dir="/tmp").enabled is False


def test_enabled_and_check(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.delenv("TORSEARCH_SECRET_KEY", raising=False)
    auth = AuthSettings.from_env(data_dir=tmp_path)
    assert auth.enabled is True
    assert auth.check("admin", "s3cret") is True
    assert auth.check("admin", "wrong") is False
    assert auth.check("nope", "s3cret") is False


def test_secret_persisted_across_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.delenv("TORSEARCH_SECRET_KEY", raising=False)
    first = AuthSettings.from_env(data_dir=tmp_path).secret_key
    second = AuthSettings.from_env(data_dir=tmp_path).secret_key
    assert first and first == second
    assert (tmp_path / ".session_secret").exists()


def test_secret_from_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.setenv("TORSEARCH_SECRET_KEY", "explicit-key")
    auth = AuthSettings.from_env(data_dir=tmp_path)
    assert auth.secret_key == "explicit-key"
    assert not (tmp_path / ".session_secret").exists()


def test_disabled_auth_allows_access():
    client = _client(AuthSettings(enabled=False))
    resp = client.get("/")
    assert resp.status_code == 200


def test_protected_route_redirects_to_login():
    client = _client(_ENABLED)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_htmx_request_gets_hx_redirect():
    client = _client(_ENABLED)
    resp = client.get(
        "/search", params={"q": "x"}, headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"] == "/login"


def test_login_page_accessible_without_session():
    client = _client(_ENABLED)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text
    assert 'name="username"' in resp.text


def test_login_success_then_access():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_login_failure_is_401_and_stays_locked():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "nope", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "incorrect" in resp.text.lower()
    assert client.get("/", follow_redirects=False).status_code == 303


def test_logout_clears_session():
    client = _client(_ENABLED)
    client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_login_rejects_open_redirect():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "//evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_logout_button_shown_when_logged_in():
    client = _client(_ENABLED)
    client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Deconnexion" in resp.text
    assert 'action="/logout"' in resp.text


def test_logout_button_hidden_when_auth_disabled():
    client = _client(AuthSettings(enabled=False))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Deconnexion" not in resp.text
