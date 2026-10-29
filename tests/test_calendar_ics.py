from __future__ import annotations

import re
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from torsearch.context import AppContext
from torsearch.db.database import Database
from torsearch.library.calendar import CalendarEntry, build_ics
from torsearch.library.series import SeriesLibrary
from torsearch.models import EpisodeInfo, SeasonInfo, WantedSeries
from torsearch.settings.store import SettingsStore
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


def test_build_ics_is_valid_and_escaped():
    entries = [(date(2026, 11, 4), [CalendarEntry(
        day=date(2026, 11, 4), kind="episode", title="Severance, la serie; vraiment",
        detail="S02E03 · Who Is Alive?", link="/series/1", poster_url=None, status="upcoming")])]
    ics = build_ics(entries, now=datetime(2026, 10, 29, 12, 0, tzinfo=UTC))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261104\r\n" in ics
    assert "DTEND;VALUE=DATE:20261105\r\n" in ics
    assert r"SUMMARY:Severance\, la serie\; vraiment · S02E03 · Who Is Alive?" in ics.replace("\r\n ", "")
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    uids = re.findall(r"UID:(.+)\r\n", ics)
    assert len(uids) == 1 and uids == re.findall(r"UID:(.+)\r\n", build_ics(entries))  # stable


class Tmdb:
    enabled = True

    async def seasons(self, tv_id):
        today = date.today().isoformat()
        return [SeasonInfo(season_number=1, episodes=[
            EpisodeInfo(season_number=1, episode_number=1, code="S01E01", name="Pilote", air_date=today)])]

    async def release_date(self, movie_id):
        return None


def _app(tmp_path, auth=False):
    db = Database(tmp_path / "db.sqlite")
    ctx = AppContext(SettingsStore(db.collection("settings")))
    ctx._tmdb = Tmdb()
    series = SeriesLibrary(db)
    series.add(WantedSeries(tmdb_id=1, title="Severance", added_at=datetime.now(UTC)))
    kw = {}
    if auth:
        users = UserStore(db.collection("users"))
        users.add("bob", "password1", Role.MEMBER)
        kw = {"auth": AuthSettings(enabled=True, secret_key="k"), "users": users}
    return TestClient(create_app(ctx, series_library=series, db=db, **kw))


def test_feed_requires_the_token_even_without_login(tmp_path):
    client = _app(tmp_path, auth=True)
    assert client.get("/calendar.ics", follow_redirects=False).status_code == 404
    assert client.get("/calendar.ics?token=wrong", follow_redirects=False).status_code == 404
    client.post("/login", data={"username": "bob", "password": "password1", "next": "/"})
    page = client.get("/calendar").text
    token = re.search(r"calendar\.ics\?token=([A-Za-z0-9_-]+)", page).group(1)
    client.cookies.clear()  # the phone's calendar app has no session
    resp = client.get(f"/calendar.ics?token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Severance · S01E01 · Pilote" in resp.text
    assert "webcal://" in page


def test_token_is_stable_and_can_be_regenerated(tmp_path):
    client = _app(tmp_path)
    first = re.search(r"token=([A-Za-z0-9_-]+)", client.get("/calendar").text).group(1)
    assert first == re.search(r"token=([A-Za-z0-9_-]+)", client.get("/calendar").text).group(1)
    client.post("/calendar/token")
    second = re.search(r"token=([A-Za-z0-9_-]+)", client.get("/calendar").text).group(1)
    assert second != first
    assert client.get(f"/calendar.ics?token={first}").status_code == 404
    assert client.get(f"/calendar.ics?token={second}").status_code == 200
