import pytest

from torsearch.users.passwords import hash_password, verify_password
from torsearch.users.store import Role, UserError, UserStore


# --- passwords ---

def test_hash_verify_roundtrip():
    h = hash_password("s3cret")
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False


def test_hash_is_salted_and_not_plaintext():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b  # random salt
    assert "same" not in a
    assert a.startswith("pbkdf2_sha256$")


def test_verify_rejects_malformed_hash():
    assert verify_password("x", "not-a-valid-hash") is False
    assert verify_password("x", "") is False


# --- store ---

def _store(tmp_path):
    return UserStore(tmp_path / "users.json")


def test_add_get_and_verify(tmp_path):
    s = _store(tmp_path)
    s.add("bob", "pw", Role.MEMBER)
    assert s.get("bob").role == Role.MEMBER
    assert s.verify("bob", "pw").username == "bob"
    assert s.verify("bob", "nope") is None
    assert s.verify("ghost", "pw") is None


def test_password_is_hashed_on_disk(tmp_path):
    s = _store(tmp_path)
    s.add("bob", "plaintext", Role.GUEST)
    raw = (tmp_path / "users.json").read_text()
    assert "plaintext" not in raw


def test_add_duplicate_raises(tmp_path):
    s = _store(tmp_path)
    s.add("bob", "pw", Role.GUEST)
    with pytest.raises(UserError):
        s.add("bob", "pw2", Role.MEMBER)


def test_is_empty_and_bootstrap_admin(tmp_path):
    s = _store(tmp_path)
    assert s.is_empty() is True
    assert s.bootstrap_admin("root", "pw") is True
    assert s.is_empty() is False
    assert s.get("root").role == Role.ADMIN
    assert s.bootstrap_admin("other", "pw") is False  # only when empty


def test_remove_works_but_protects_last_admin(tmp_path):
    s = _store(tmp_path)
    s.add("admin", "pw", Role.ADMIN)
    s.add("bob", "pw", Role.MEMBER)
    s.remove("bob")
    assert s.get("bob") is None
    with pytest.raises(UserError):
        s.remove("admin")  # last admin


def test_remove_admin_ok_when_another_admin_exists(tmp_path):
    s = _store(tmp_path)
    s.add("a1", "pw", Role.ADMIN)
    s.add("a2", "pw", Role.ADMIN)
    s.remove("a1")
    assert s.count_admins() == 1


def test_set_role_protects_last_admin(tmp_path):
    s = _store(tmp_path)
    s.add("admin", "pw", Role.ADMIN)
    with pytest.raises(UserError):
        s.set_role("admin", Role.MEMBER)  # would leave zero admins


def test_set_password_changes_verification(tmp_path):
    s = _store(tmp_path)
    s.add("bob", "old", Role.MEMBER)
    s.set_password("bob", "new")
    assert s.verify("bob", "old") is None
    assert s.verify("bob", "new").username == "bob"


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "users.json"
    UserStore(path).add("bob", "pw", Role.MEMBER)
    again = UserStore(path)
    assert again.get("bob").role == Role.MEMBER
    assert not path.with_name(path.name + ".tmp").exists()
