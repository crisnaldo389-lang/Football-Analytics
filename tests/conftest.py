"""
Fixtures partagées par la suite de tests.

Le jeu de données est un vrai match StatsBomb open data (Barcelona 4-1 Huesca),
réduit aux colonnes que l'application lit et compressé pour rester léger dans le dépôt.
Données fournies par StatsBomb : https://github.com/statsbomb/open-data
"""
import matplotlib
matplotlib.use('Agg')  # Aucun backend graphique en CI

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from helpers import aggregate_matches

# Chemin déduit du fichier de test : la suite doit tourner quel que soit le dossier courant
FIXTURE = Path(__file__).parent / 'fixtures' / 'sample_match.json.gz'

HOME_TEAM = 'Barcelona'
AWAY_TEAM = 'Huesca'


@pytest.fixture(scope='session')
def raw_events():
    """ Évènements bruts du match de référence, chargés une seule fois. """
    return pd.read_json(FIXTURE, compression='gzip')


@pytest.fixture
def events(raw_events):
    """ Copie par test, pour qu'un test qui modifie le DataFrame n'affecte pas les autres. """
    return raw_events.copy()


@pytest.fixture
def multi_events(raw_events):
    """ Deux fois le même match, comme le fait le mode Multi-Match. """
    return aggregate_matches([raw_events.copy(), raw_events.copy()], ['Match 1', 'Match 2'])


@pytest.fixture
def top_defender(raw_events):
    """ Joueur au plus grand volume d'actions défensives, et son équipe. """
    from helpers import DEFENSIVE_ACTIONS
    actions = raw_events[raw_events['type'].isin(DEFENSIVE_ACTIONS)]
    return actions.groupby(['player', 'team']).size().idxmax()


@pytest.fixture(autouse=True)
def close_figures():
    """ Les visualisations créent des figures : sans fermeture, matplotlib alerte au bout de 20. """
    yield
    plt.close('all')
