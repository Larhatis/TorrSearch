from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.transmission.client import TorrentInfo
from torsearch.web.routes import create_app


class FakeTransmission:
    def __init__(self, torrents=None, fail=False):
        self._torrents = torrents or []
        self._fail = fail
        self.calls = []

    async def list_torrents(self):
        if self._fail:
            raise RuntimeError("down")
        return self._torrents

    async def pause(self, tid):
        self.calls.append(("pause", tid))

    async def resume(self, tid):
        self.calls.append(("resume", tid))

    async def remove(self, tid, delete_data=False):
        self.calls.append(("remove", tid, delete_data))


class FakeJellyfin:
    enabled = True

    def __init__(self):
        self.refreshed = False
        self.base_url = "http://jf:8096"

    async def refresh(self):
        self.refreshed = True
        return True

    async def owned(self):
        return {}


class FakeContext:
    def __init__(self, transmission, jellyfin=None):
        self.transmission = transmission
        self.jellyfin = jellyfin or FakeJellyfin()
        self.search_service = None
        self.config = Config()


def _client(transmission, jellyfin=None):
    return TestClient(create_app(FakeContext(transmission, jellyfin=jellyfin)))


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
    assert ("remove", 5, False) in fake.calls


def test_delete_calls_transmission_with_delete_data():
    fake = FakeTransmission([_ti(id=5, name="X")])
    _client(fake).post("/downloads/5/delete?delete_data=true")
    assert ("remove", 5, True) in fake.calls


def test_activity_alias_renders_downloads_page():
    resp = _client(FakeTransmission()).get("/activity")
    assert resp.status_code == 200
    assert 'id="downloads-list"' in resp.text


def test_scan_jellyfin_calls_refresh_and_returns_toast():
    jelly = FakeJellyfin()
    resp = _client(FakeTransmission(), jellyfin=jelly).post("/downloads/scan-jellyfin")
    assert resp.status_code == 200
    assert jelly.refreshed is True
    assert "Jellyfin" in resp.text


def test_downloads_list_displays_eta_and_rates():
    torrent = _ti(
        name="Blockbuster.2024.1080p",
        percent=62.5,
        status="downloading",
        down_rate=8_500_000,
        up_rate=250_000,
        size=3_500_000_000,
        eta=185,
        peers_connected=14,
    )
    resp = _client(FakeTransmission([torrent])).get("/downloads/list")
    assert resp.status_code == 200
    assert "Blockbuster.2024.1080p" in resp.text
    assert "8.1 Mo/s" in resp.text
    assert "3m 5s" in resp.text
    assert "Telechargement" in resp.text


class _LeakyTransmission(FakeTransmission):
    async def list_torrents(self):
        raise RuntimeError("Invalid URL 'http://u:TR-SECRET@:9091/transmission/rpc'")


def test_transmission_errors_never_show_credentials():
    resp = _client(_LeakyTransmission()).get("/downloads/list")
    assert "injoignable" in resp.text.lower()
    assert "TR-SECRET" not in resp.text


def test_downloads_list_filters_and_counters():
    t_down = _ti(id=1, name="Downloading.Movie", percent=50.0, status="downloading", down_rate=1000, up_rate=0)
    t_seed = _ti(id=2, name="Completed.Movie", percent=100.0, status="seeding", down_rate=0, up_rate=500)
    t_pause = _ti(id=3, name="Paused.Movie", percent=20.0, status="stopped", down_rate=0, up_rate=0)
    torrents = [t_down, t_seed, t_pause]
    fake = FakeTransmission(torrents)
    client = _client(fake)

    # 1. Filter: all (default)
    resp_all = client.get("/downloads/list")
    assert resp_all.status_code == 200
    assert "Downloading.Movie" in resp_all.text
    assert "Completed.Movie" in resp_all.text
    assert "Paused.Movie" in resp_all.text
    # Tabs exist with counters
    assert "En cours" in resp_all.text
    assert "Termines" in resp_all.text
    assert "Actifs" in resp_all.text
    assert "En pause" in resp_all.text

    # 2. Filter: downloading
    resp_down = client.get("/downloads/list?filter=downloading")
    assert resp_down.status_code == 200
    assert "Downloading.Movie" in resp_down.text
    assert "Completed.Movie" not in resp_down.text
    assert "Paused.Movie" not in resp_down.text
    assert 'filter=downloading' in resp_down.text

    # 3. Filter: completed
    resp_comp = client.get("/downloads/list?filter=completed")
    assert resp_comp.status_code == 200
    assert "Completed.Movie" in resp_comp.text
    assert "Downloading.Movie" not in resp_comp.text

    # 4. Filter: active
    resp_act = client.get("/downloads/list?filter=active")
    assert resp_act.status_code == 200
    assert "Downloading.Movie" in resp_act.text  # down_rate = 1000
    assert "Completed.Movie" in resp_act.text    # up_rate = 500
    assert "Paused.Movie" not in resp_act.text   # rate = 0

    # 5. Filter: paused
    resp_pause = client.get("/downloads/list?filter=paused")
    assert resp_pause.status_code == 200
    assert "Paused.Movie" in resp_pause.text
    assert "Downloading.Movie" not in resp_pause.text

    # 6. Action preserves filter query
    resp_action = client.post("/downloads/1/pause?filter=downloading")
    assert resp_action.status_code == 200
    assert 'filter=downloading' in resp_action.text


