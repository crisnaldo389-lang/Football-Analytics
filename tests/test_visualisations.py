"""
Tests des visualisations.

On ne vérifie pas le rendu pixel par pixel : ces tests garantissent que chaque vue
produit une figure sur des données réelles, et surtout qu'aucune ne casse sur les cas
dégradés (joueur sans action, équipe absente, colonne manquante) qui arrivent
régulièrement avec les données open data.
"""
import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure

from helpers import (passes_map, heatmap, shots_map, carries_map, dribbles_map,
                     defensive_actions_map, defensive_shape, pass_network, xg_timeline,
                     match_summary, player_comparison_radar, player_season_summary,
                     performance_trend, ensure_columns, add_statsbomb_credit)
from conftest import HOME_TEAM, AWAY_TEAM

PLAYER_VIZ = [passes_map, heatmap, shots_map, carries_map, dribbles_map, defensive_actions_map]
TEAM_VIZ = [pass_network, xg_timeline, defensive_shape]

# Colonnes qu'une visualisation peut trouver vides sur un match sans l'action correspondante
OPTIONAL_COLUMNS = ['dribble_outcome', 'duel_outcome', 'duel_type', 'pass_goal_assist']


@pytest.fixture
def busiest_player(events):
    """ Joueur le plus impliqué de l'équipe à domicile : il a des données pour toutes les vues. """
    home = events[events['team'] == HOME_TEAM]
    return home['player'].value_counts().idxmax()


def assert_is_figure(result):
    """ Toutes les vues renvoient (figure, axes) ; les axes sont tantôt un dict mplsoccer,
    tantôt un Axes matplotlib selon la vue. Seule la figure nous intéresse ici. """
    fig, axes = result
    assert isinstance(fig, Figure)
    assert axes is not None
    return fig


# ==================== CAS NOMINAL ====================

@pytest.mark.parametrize('viz', PLAYER_VIZ, ids=lambda f: f.__name__)
def test_player_visualisation_renders(viz, events, busiest_player):
    assert_is_figure(viz(player=busiest_player, df=events, team=HOME_TEAM, match='Test match'))


@pytest.mark.parametrize('viz', TEAM_VIZ, ids=lambda f: f.__name__)
def test_team_visualisation_renders(viz, events):
    assert_is_figure(viz(df=events, team=HOME_TEAM, match='Test match'))


def test_match_summary_renders(events):
    assert_is_figure(match_summary(df=events, match='Test match'))


def test_player_comparison_radar_renders(events):
    home = events[events['team'] == HOME_TEAM]['player'].value_counts().idxmax()
    away = events[events['team'] == AWAY_TEAM]['player'].value_counts().idxmax()
    assert_is_figure(player_comparison_radar(df=events, player1=home, player2=away,
                                             team1=HOME_TEAM, team2=AWAY_TEAM, match='Test match'))


def test_multi_match_visualisations_render(multi_events):
    player = multi_events[multi_events['team'] == HOME_TEAM]['player'].value_counts().idxmax()
    assert_is_figure(player_season_summary(df=multi_events, player=player, team=HOME_TEAM, num_matches=2))
    assert_is_figure(performance_trend(df=multi_events, player=player, team=HOME_TEAM, stat_type='xG'))


# ==================== SANS NOM DE MATCH ====================

@pytest.mark.parametrize('viz', PLAYER_VIZ, ids=lambda f: f.__name__)
def test_player_visualisation_without_match_name(viz, events, busiest_player):
    """ Le mode Upload JSON n'a pas de nom de match : match=None doit passer. """
    assert_is_figure(viz(player=busiest_player, df=events, team=HOME_TEAM))


@pytest.mark.parametrize('viz', TEAM_VIZ, ids=lambda f: f.__name__)
def test_team_visualisation_without_match_name(viz, events):
    assert_is_figure(viz(df=events, team=HOME_TEAM))


# ==================== CAS DÉGRADÉS ====================

@pytest.mark.parametrize('viz', PLAYER_VIZ, ids=lambda f: f.__name__)
def test_player_visualisation_survives_unknown_player(viz, events):
    """ Un joueur sans aucune action doit rendre un terrain vide, pas une exception. """
    assert_is_figure(viz(player='Nobody', df=events, team=HOME_TEAM, match='Test match'))


@pytest.mark.parametrize('viz', TEAM_VIZ, ids=lambda f: f.__name__)
def test_team_visualisation_survives_unknown_team(viz, events):
    assert_is_figure(viz(df=events, team='Nobody FC', match='Test match'))


@pytest.mark.parametrize('viz', PLAYER_VIZ, ids=lambda f: f.__name__)
def test_player_visualisation_survives_missing_optional_columns(viz, events, busiest_player):
    """
    StatsBomb n'émet une colonne que si l'action existe dans le match. ensure_columns
    est censé combler le trou : ce test vérifie que le contrat tient bout en bout.
    """
    trimmed = ensure_columns(events.drop(columns=OPTIONAL_COLUMNS), OPTIONAL_COLUMNS)
    assert_is_figure(viz(player=busiest_player, df=trimmed, team=HOME_TEAM, match='Test match'))


def test_visualisation_survives_an_empty_dataframe(events):
    """ Un filtre temporel serré peut ne rien laisser passer. """
    empty = events.iloc[0:0]
    assert_is_figure(defensive_actions_map(player='Nobody', df=empty, team=HOME_TEAM, match='x'))
    assert_is_figure(defensive_shape(df=empty, team=HOME_TEAM, match='x'))


# ==================== CRÉDIT STATSBOMB ====================

@pytest.mark.parametrize('viz', PLAYER_VIZ + TEAM_VIZ, ids=lambda f: f.__name__)
def test_visualisation_carries_the_statsbomb_credit(viz, events, busiest_player):
    """
    La clause 1.4 de la licence impose le crédit sur toute publication : il doit être
    apposé sur la figure elle-même, donc survivre à l'export PNG.
    """
    kwargs = {'df': events, 'team': HOME_TEAM, 'match': 'Test match'}
    if viz in PLAYER_VIZ:
        kwargs['player'] = busiest_player
    fig, _ = viz(**kwargs)

    has_logo = any(ax.get_images() for ax in fig.axes)
    has_text = any('StatsBomb' in t.get_text() for t in fig.texts)
    assert has_logo or has_text, "Aucun crédit StatsBomb sur la figure"


def test_credit_falls_back_to_text_without_the_logo(monkeypatch):
    """ Un clone sans le fichier de logo doit rester crédité. """
    import helpers
    monkeypatch.setattr(helpers, 'load_statsbomb_logo', lambda: None)

    fig = plt.figure()
    add_statsbomb_credit(fig)
    assert any('StatsBomb' in t.get_text() for t in fig.texts)
