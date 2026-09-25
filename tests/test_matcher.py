from __future__ import annotations

from torsearch.parser.release import parse_release
from torsearch.search.matcher import match_media_title


def test_series_strict_matching_avoids_false_positives():
    rel_lost = parse_release("Lost.S01E03.FRENCH.720p.WEB-DL.x264")
    assert match_media_title(rel_lost, target_title="Lost", is_series=True) is True

    rel_lost_in_space = parse_release("Lost.in.Space.S01E03.FRENCH.720p.WEB-DL.x264")
    assert match_media_title(rel_lost_in_space, target_title="Lost", is_series=True) is False


def test_movie_strict_matching_avoids_sequels():
    rel_avatar1 = parse_release("Avatar.2009.FRENCH.1080p.BluRay.x264")
    assert match_media_title(rel_avatar1, target_title="Avatar", target_year=2009) is True

    rel_avatar2 = parse_release("Avatar.The.Way.of.Water.2022.MULTi.1080p")
    assert match_media_title(rel_avatar2, target_title="Avatar", target_year=2009) is False

    rel_dune2 = parse_release("Dune.Part.Two.2024.FRENCH.1080p")
    assert match_media_title(rel_dune2, target_title="Dune", target_year=2021) is False


def test_movie_year_tolerance():
    # Year matches or delta <= 1 is accepted
    rel_exact = parse_release("Gladiator.2000.1080p.BluRay")
    assert match_media_title(rel_exact, target_title="Gladiator", target_year=2000) is True

    rel_delta = parse_release("Gladiator.2001.1080p.BluRay")
    assert match_media_title(rel_delta, target_title="Gladiator", target_year=2000) is True

    rel_bad_year = parse_release("Gladiator.1990.1080p.BluRay")
    assert match_media_title(rel_bad_year, target_title="Gladiator", target_year=2000) is False

    # If release doesn't state year, title match is sufficient
    rel_no_year = parse_release("Gladiator.1080p.BluRay")
    assert match_media_title(rel_no_year, target_title="Gladiator", target_year=2000) is True


def test_original_title_matching():
    rel_got = parse_release("Game.of.Thrones.S01E01.MULTi.1080p")
    assert match_media_title(
        rel_got,
        target_title="Le Trône de Fer",
        target_original_title="Game of Thrones",
        is_series=True,
    ) is True

    rel_french = parse_release("Le.Trone.de.Fer.S01E01.FRENCH.720p")
    assert match_media_title(
        rel_french,
        target_title="Le Trône de Fer",
        target_original_title="Game of Thrones",
        is_series=True,
    ) is True


def test_accents_and_punctuation_normalization():
    rel_amelie = parse_release("Le.Fabuleux.Destin.d.Amelie.Poulain.2001.FRENCH.1080p")
    assert match_media_title(
        rel_amelie,
        target_title="Le Fabuleux Destin d'Amélie Poulain",
        target_year=2001,
    ) is True

    rel_spiderman = parse_release("Spider-Man.No.Way.Home.2021.MULTi.1080p")
    assert match_media_title(
        rel_spiderman,
        target_title="Spider-Man: No Way Home",
        target_year=2021,
    ) is True

    rel_swat = parse_release("S.W.A.T.S01E01.720p")
    assert match_media_title(rel_swat, target_title="S.W.A.T.", is_series=True) is True
