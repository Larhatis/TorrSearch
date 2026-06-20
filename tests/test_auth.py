from torsearch.web.auth import AuthSettings


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
