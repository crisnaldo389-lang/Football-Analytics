""" Tests des calculs purs : aucune figure, aucun réseau. """
import numpy as np
import pandas as pd
import pytest

from helpers import (compute_ppda, ensure_columns, check_required_columns, aggregate_matches,
                     get_shots, _get_player_stats_for_pdf, _get_defensive_stats_for_pdf,
                     _get_match_stats_for_pdf, PPDA_ZONE_START, PITCH_LENGTH,
                     SHOOTOUT_PERIOD)
from conftest import HOME_TEAM, AWAY_TEAM


# ==================== TIRS ET SÉANCE DE TIRS AU BUT ====================

def shootout_match():
    """
    Match nul 1-1 décidé aux tirs au but, à la manière d'un export StatsBomb.

    Le penalty de la 30e est obtenu dans le jeu et compte au score ; les deux tirs de la
    période 5 décident de la qualification mais pas du score.
    """
    return pd.DataFrame({
        'team': [HOME_TEAM] * 3 + [AWAY_TEAM],
        'player': ['Marqueur'] * 3 + ['Adversaire'],
        'type': ['Shot'] * 4,
        'period': [1, SHOOTOUT_PERIOD, SHOOTOUT_PERIOD, 2],
        'minute': [30, 120, 120, 70],
        'shot_type': ['Penalty', 'Penalty', 'Penalty', 'Open Play'],
        'shot_outcome': ['Goal', 'Goal', 'Saved', 'Goal'],
        'shot_statsbomb_xg': [0.78, 0.78, 0.78, 0.1],
        'pass_outcome': [np.nan] * 4,  # colonne lue par les stats d'équipe
    })


def test_get_shots_excludes_the_shootout_but_keeps_penalties_in_play():
    shots = get_shots(shootout_match())

    assert len(shots) == 2
    assert (shots['period'] != SHOOTOUT_PERIOD).all()
    # Le penalty obtenu dans le jeu reste compté
    assert (shots['shot_type'] == 'Penalty').sum() == 1


def test_get_shots_keeps_the_shootout_on_demand():
    assert len(get_shots(shootout_match(), include_shootout=True)) == 4


def test_get_shots_without_a_period_column_keeps_every_shot():
    """ Un fichier importé peut ne pas porter la colonne : ne rien perdre silencieusement. """
    df = shootout_match().drop(columns=['period'])
    assert len(get_shots(df)) == 4


def test_match_stats_ignore_shootout_goals_and_xg():
    stats = _get_match_stats_for_pdf(shootout_match(), HOME_TEAM, AWAY_TEAM)

    assert stats[f'{HOME_TEAM} Goals'] == 1
    assert stats[f'{HOME_TEAM} xG'] == 0.78
    assert stats[f'{AWAY_TEAM} Goals'] == 1


def test_player_stats_ignore_shootout_goals():
    stats = _get_player_stats_for_pdf(shootout_match(), 'Marqueur', HOME_TEAM, 'Shots')

    assert stats['Shots'] == 1
    assert stats['Goals'] == 1
    assert stats['xG'] == 0.78


# ==================== PPDA ====================

def test_ppda_separates_pressing_styles(events):
    """ Barcelone presse haut, Huesca défend en bloc bas : le PPDA doit les distinguer. """
    pressing = compute_ppda(events, HOME_TEAM)
    sitting_back = compute_ppda(events, AWAY_TEAM)

    assert pressing < sitting_back, (
        f"{HOME_TEAM} ({pressing:.1f}) devrait presser plus intensément que {AWAY_TEAM} ({sitting_back:.1f})")
    # Un PPDA réaliste tient dans cet intervalle ; en sortir signale une erreur de calcul
    assert 3 < pressing < 40
    assert 3 < sitting_back < 40


def test_ppda_returns_float(events):
    """ Une valeur numpy remonterait telle quelle dans le PDF. """
    assert type(compute_ppda(events, HOME_TEAM)) is float


def test_ppda_is_none_without_opponent(events):
    """ Sans adversaire dans les données, le dénominateur n'a pas de sens. """
    assert compute_ppda(events[events['team'] == HOME_TEAM], HOME_TEAM) is None


def test_ppda_is_none_without_defensive_action():
    """ Zéro action défensive dans la zone : pas de division par zéro. """
    passes_only = pd.DataFrame({
        'team': [HOME_TEAM, AWAY_TEAM],
        'type': ['Pass', 'Pass'],
        'location': [[10.0, 40.0], [10.0, 40.0]],
    })
    assert compute_ppda(passes_only, HOME_TEAM) is None


def test_ppda_counts_the_same_physical_zone_for_both_teams():
    """
    StatsBomb oriente les coordonnées de chaque équipe vers le but adverse. Une passe
    adverse à x=20 dans SES coordonnées se joue dans la zone de pressing, et doit donc
    être comptée ; la même passe à x=100 en est hors.
    """
    df = pd.DataFrame({
        'team': [AWAY_TEAM, AWAY_TEAM, HOME_TEAM],
        'type': ['Pass', 'Pass', 'Interception'],
        'location': [
            [20.0, 40.0],   # relance adverse : dans la zone -> comptée
            [100.0, 40.0],  # passe adverse dans notre surface : hors zone -> ignorée
            [PPDA_ZONE_START + 10, 40.0],  # notre interception, dans la zone
        ],
    })
    assert compute_ppda(df, HOME_TEAM) == 1.0

    # Les deux seuils décrivent bien la même bande de terrain
    assert PPDA_ZONE_START == PITCH_LENGTH - (PITCH_LENGTH - PPDA_ZONE_START)


def test_ppda_ignores_pressure_events():
    """ La définition classique exclut le Pressure, absent du modèle d'origine. """
    def ten_passes_against(action_type):
        return pd.DataFrame({
            'team': [AWAY_TEAM] * 10 + [HOME_TEAM],
            'type': ['Pass'] * 10 + [action_type],
            'location': [[20.0, 40.0]] * 10 + [[60.0, 40.0]],
        })

    assert compute_ppda(ten_passes_against('Duel'), HOME_TEAM) == 10.0
    assert compute_ppda(ten_passes_against('Pressure'), HOME_TEAM) is None


# ==================== STATISTIQUES POUR LE PDF ====================

@pytest.mark.parametrize('analysis_type, expected_keys', [
    ('Passes', ['Total Passes', 'Completed']),
    ('Shots', ['Shots', 'Goals', 'xG']),
    ('Carries', ['Total Carries']),
    ('Dribbles', ['Total Dribbles', 'Successful']),
    ('Defensive Actions', ['Defensive Actions', 'Duels Won', 'Avg Height', 'In Final Third']),
])
def test_player_stats_for_pdf(events, analysis_type, expected_keys):
    player = events[events['team'] == HOME_TEAM]['player'].dropna().iloc[0]
    stats = _get_player_stats_for_pdf(events, player, HOME_TEAM, analysis_type)
    assert list(stats) == expected_keys


def test_player_stats_for_pdf_survives_a_player_without_events(events):
    """ Un joueur sans action ne doit pas provoquer de division par zéro. """
    stats = _get_player_stats_for_pdf(events, 'Nobody', HOME_TEAM, 'Defensive Actions')
    assert stats['Defensive Actions'] == 0
    assert stats['Duels Won'] == '0/0 (0%)'


def test_defensive_stats_for_pdf(events):
    stats = _get_defensive_stats_for_pdf(events, HOME_TEAM)
    assert stats['Defensive Actions'] > 0
    assert isinstance(stats['PPDA'], float)
    assert stats['Avg Height'].endswith('%')
    assert stats['In Opponent Half'].endswith('%')
    # Le détail par type ne liste que les actions réellement présentes
    assert stats['Pressure'] > 0


def test_defensive_stats_for_pdf_without_any_action(events):
    empty = events[events['type'] == 'Starting XI']
    assert _get_defensive_stats_for_pdf(empty, HOME_TEAM) == {'Defensive Actions': 0}


def test_match_stats_for_pdf_covers_both_teams(events):
    stats = _get_match_stats_for_pdf(events, HOME_TEAM, AWAY_TEAM)
    assert f'{HOME_TEAM} Goals' in stats
    assert f'{AWAY_TEAM} Goals' in stats


# ==================== CHARGEMENT ====================

def test_ensure_columns_adds_missing_as_nan(events):
    trimmed = events.drop(columns=['duel_outcome'])
    restored = ensure_columns(trimmed, ['duel_outcome', 'team'])

    assert restored['duel_outcome'].isna().all()
    # Une colonne déjà présente n'est pas écrasée
    assert restored['team'].notna().any()


def test_check_required_columns_reports_what_is_missing(events):
    ok, _ = check_required_columns(events, ['team', 'player'])
    assert ok

    ok, detail = check_required_columns(events, ['team', 'inexistante'])
    assert not ok
    assert 'inexistante' in detail


def test_aggregate_matches_tags_each_match(multi_events, raw_events):
    assert len(multi_events) == 2 * len(raw_events)
    assert sorted(multi_events['match_id'].unique()) == [0, 1]
    assert sorted(multi_events['match_name'].unique()) == ['Match 1', 'Match 2']
