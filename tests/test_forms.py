from torsearch.web.forms import GB, split_words, to_int, to_size_bytes


def test_to_int_parses_and_falls_back():
    assert to_int("12") == 12
    assert to_int("-3") == -3
    assert to_int("abc") == 0
    assert to_int("", default=3) == 3


def test_to_size_bytes_converts_gb():
    assert to_size_bytes("1.5") == int(1.5 * GB)
    assert to_size_bytes("0") is None
    assert to_size_bytes("") is None
    assert to_size_bytes("xyz") is None


def test_split_words_on_spaces_and_commas():
    assert split_words("cam, ts  multi") == ["cam", "ts", "multi"]
    assert split_words("") == []


def test_to_size_bytes_rejects_non_finite_values():
    assert to_size_bytes("inf") is None
    assert to_size_bytes("1e400") is None
    assert to_size_bytes("nan") is None
