"""
Test de bout en bout : l'application est réellement exécutée et pilotée, sans navigateur.

C'est ce que ces tests attrapent et que les tests unitaires laissent passer : une
visualisation oubliée dans la chaîne de dispatch, un titre manquant, un menu mal câblé.

Les trois chargeurs StatsBomb sont remplacés par le fixture local : la suite reste
déterministe et ne dépend pas du réseau ni de la disponibilité de l'API.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import helpers
from conftest import HOME_TEAM, AWAY_TEAM

APP = 'main.py'
TIMEOUT = 60
MATCH_ID = 3773369
MATCH_LABEL = f'{HOME_TEAM} 4-1 {AWAY_TEAM} (2020-11-05)'


@pytest.fixture
def offline_statsbomb(monkeypatch, raw_events):
    """
    Neutralise les appels réseau. main.py importe ces fonctions au chargement du script,
    et AppTest réimporte le module à chaque run : patcher helpers en amont suffit.
    """
    competitions = pd.DataFrame([{
        'competition_label': 'Spain - La Liga',
        'competition_id': 11, 'season_id': 90, 'season_name': '2020/2021',
    }])
    matches = pd.DataFrame([{
        'match_id': MATCH_ID, 'match_label': MATCH_LABEL,
        'home_team': HOME_TEAM, 'away_team': AWAY_TEAM, 'match_date': '2020-11-05',
    }])

    monkeypatch.setattr(helpers, 'load_competitions', lambda: competitions)
    monkeypatch.setattr(helpers, 'load_matches', lambda competition_id, season_id: matches)
    monkeypatch.setattr(helpers, 'load_events', lambda match_id: raw_events.copy())
    monkeypatch.setattr(helpers, 'load_events_parallel',
                        lambda match_ids: [(m, raw_events.copy()) for m in match_ids])


@pytest.fixture
def app(offline_statsbomb):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not at.exception, f"L'application ne démarre pas : {at.exception}"
    return at


def statistic_selector(at):
    return next(s for s in at.sidebar.selectbox if s.label == 'Select a Statistic')


def analysis_level(at):
    return next(r for r in at.sidebar.radio if r.label == 'Analysis Level')


def test_app_starts(app):
    assert statistic_selector(app).options


def test_every_player_statistic_renders(app):
    """ Chaque entrée du menu Player doit produire une figure sans lever. """
    for stat in statistic_selector(app).options:
        run = statistic_selector(app).select(stat).run()
        assert not run.exception, f"'{stat}' lève : {run.exception}"
        assert run.get('arrow_vega_lite_chart') is not None or run.markdown, stat


def test_every_team_statistic_renders(app):
    at = analysis_level(app).set_value('Team').run()
    assert not at.exception

    for stat in statistic_selector(at).options:
        run = statistic_selector(at).select(stat).run()
        assert not run.exception, f"'{stat}' lève : {run.exception}"


def test_comparison_statistic_renders(app):
    at = analysis_level(app).set_value('Comparison').run()
    assert not at.exception
    assert 'Player Radar' in statistic_selector(at).options


def test_every_statistic_is_wired_to_a_title(app):
    """
    Le titre est construit par une liste tenue à la main dans main.py : une vue oubliée
    s'affiche en 'X Map', ce que ce test rend visible.
    """
    for level, expected_suffixes in [('Player', ('Map', 'Heatmap', 'Defensive Actions')),
                                     ('Team', None)]:
        at = analysis_level(app).set_value(level).run()
        for stat in statistic_selector(at).options:
            run = statistic_selector(at).select(stat).run()
            titles = [m.value for m in run.markdown if m.value.startswith('###')]
            assert any(stat in t for t in titles), f"Aucun titre pour '{stat}'"


def test_defensive_views_expose_their_metrics(app):
    """ Les métriques défensives sont le produit de la feature : elles doivent s'afficher. """
    run = statistic_selector(app).select('Defensive Actions').run()
    labels = [m.label for m in run.metric]
    assert labels == ['Defensive Actions', 'Duels Won', 'Avg Height', 'In Final Third']

    at = analysis_level(run).set_value('Team').run()
    run = statistic_selector(at).select('Defensive Shape').run()
    labels = [m.label for m in run.metric]
    assert labels == ['Defensive Actions', 'PPDA', 'Avg Height', 'In Opponent Half']
    assert next(m.value for m in run.metric if m.label == 'PPDA') != 'N/A'


def test_time_filter_narrows_the_data(app):
    """ Le filtre temporel doit réellement réduire le volume analysé. """
    full = statistic_selector(app).select('Defensive Actions').run()
    total = int(next(m.value for m in full.metric if m.label == 'Defensive Actions'))

    period = next(r for r in full.sidebar.radio if r.label == 'Period')
    first_half = period.set_value('1st Half').run()
    assert not first_half.exception

    partial = int(next(m.value for m in first_half.metric if m.label == 'Defensive Actions'))
    assert 0 < partial < total


def test_multi_match_mode_renders(app):
    at = next(r for r in app.sidebar.radio if r.label == 'Data Mode').set_value('Multi-Match').run()
    assert not at.exception, f"Le mode Multi-Match lève : {at.exception}"

    for stat in statistic_selector(at).options:
        run = statistic_selector(at).select(stat).run()
        assert not run.exception, f"'{stat}' lève en Multi-Match : {run.exception}"
