from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.transmission.client import TorrentInfo
from torsearch.web.routes import create_app


class FakeTransmission:
    def __init__(self, torrents=None, fail=False):
        self._torrents = torrents or []
        self._fail = fail
        self.calls = []

    def list_torrents(self):
        if self._fail:
            raise RuntimeError("down")
        return self._torrents

    def pause(self, tid):
        self.calls.append(("pause", tid))

    def resume(self, tid):
        self.calls.append(("resume", tid))

    def remove(self, tid):
        self.calls.append(("remove", tid))


class FakeContext:
    def __init__(self, transmission):
        self.transmission = transmission
        self.search_service = None
        self.config = Config()


def _client(transmission):
    return TestClient(create_app(FakeContext(transmission)))


def _ti(**o):
    base = dict(id=1, name="ubuntu.iso", percent=50.0, status="downloading",
                down_rate=1024, up_rate=0, size=2_000_000_000)
    base.update(o)
    return TorrentInfo(**base)


def test_downloads_page_has_autorefresh_container():
    resp = _client(FakeTransmission()).get("/downloads")
    assert resp.status_code == 200
    assert 'id="downloads-list"' in resp.text
    assert "every 3s" in resp.text


def test_downloads_list_renders_torrents():
    resp = _client(FakeTransmission([_ti(name="MyShow.S01E01"), _ti(id=2, name="MyMovie")])).get("/downloads/list")
    assert resp.status_code == 200
    assert "MyShow.S01E01" in resp.text
    assert "MyMovie" in resp.text


def test_downloads_list_empty_shows_placeholder():
    resp = _client(FakeTransmission([])).get("/downloads/list")
    assert "Aucun" in resp.text


def test_downloads_list_shows_error_when_transmission_down():
    resp = _client(FakeTransmission(fail=True)).get("/downloads/list")
    assert resp.status_code == 200
    assert "injoignable" in resp.text.lower()


def test_pause_calls_transmission_and_rerenders():
    fake = FakeTransmission([_ti(id=5, name="X")])
    resp = _client(fake).post("/downloads/5/pause")
    assert resp.status_code == 200
    assert ("pause", 5) in fake.calls


def test_resume_calls_transmission():
    fake = FakeTransmission([_ti(id=5, name="X", status="stopped")])
    _client(fake).post("/downloads/5/resume")
    assert ("resume", 5) in fake.calls


def test_delete_calls_transmission():
    fake = FakeTransmission([_ti(id=5, name="X")])
    _client(fake).post("/downloads/5/delete")
    assert ("remove", 5) in fake.calls
