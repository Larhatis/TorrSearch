from torsearch.web.templating import templates


def _render(call: str) -> str:
    src = (
        "{% from 'partials/components.html' import badge_quality, health, source_chip %}"
        + call
    )
    return templates.env.from_string(src).render()


def test_health_good_ok_low():
    assert 'data-health="good"' in _render("{{ health(150) }}")
    assert 'data-health="ok"' in _render("{{ health(40) }}")
    assert 'data-health="low"' in _render("{{ health(5) }}")
    assert ">5<" in _render("{{ health(5) }}")


def test_badge_quality_labels():
    out = _render("{{ badge_quality('Film.2024.1080p.WEB') }}")
    assert 'data-quality="1080p"' in out
    assert "1080p" in out
    assert 'data-quality="2160p"' in _render("{{ badge_quality('Film 2160p UHD') }}")
    assert 'data-quality="other"' in _render("{{ badge_quality('Film DVDRip') }}")


def test_source_chip_shows_name():
    assert "torr9" in _render("{{ source_chip('torr9') }}")
