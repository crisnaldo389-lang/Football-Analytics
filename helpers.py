import warnings
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import requests_cache
from mplsoccer import Pitch, Radar
from statsbombpy import sb

# statsbombpy installe à l'import un cache HTTP SQLite global sur requests. Ce cache
# corrompt la mémoire du process (segfault) dès que plusieurs matchs sont téléchargés
# en parallèle, et il fait doublon avec le nôtre, qui garde le DataFrame déjà parsé.
requests_cache.uninstall_cache()
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import matplotlib.patheffects as path_effects
import pandas as pd
import numpy as np
from scipy.ndimage import gaussian_filter
from io import BytesIO
from datetime import datetime
from functools import lru_cache
from pathlib import Path

# PDF generation imports
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# La clause 1.4 du StatsBomb Public Data User Agreement impose de créditer toute
# publication d'analyse tirée de ces données avec le logo de marque StatsBomb. Le crédit
# est apposé sur la figure elle-même, et non seulement dans l'interface, pour que
# l'export PNG le conserve.
STATSBOMB_LOGO_PATH = Path(__file__).parent / 'assets' / 'SB - Icon Lockup - Colour positive.png'
STATSBOMB_CREDIT = 'Data: StatsBomb'


@lru_cache(maxsize=1)
def load_statsbomb_logo():
    """ Charge le logo officiel une seule fois, ou None s'il est absent du dépôt. """
    try:
        return mpimg.imread(STATSBOMB_LOGO_PATH)
    except Exception:
        return None


def add_statsbomb_credit(fig, x=0.02, y=0.012, width=0.13, color='#000000',
                         fontsize=9, alpha=1.0):
    """
    Appose le crédit StatsBomb en bas à gauche d'une figure.

    Utilise le logo de marque exigé par la licence, et retombe sur un crédit texte si
    le fichier manque, pour qu'un clone incomplet reste malgré tout crédité.

    Args:
        fig: figure matplotlib
        x, y, width: position et largeur du logo, en coordonnées normalisées de figure
        color, fontsize, alpha: mise en forme du crédit texte de repli
    """
    logo = load_statsbomb_logo()
    if logo is None:
        fig.text(x, y, STATSBOMB_CREDIT, ha='left', va='bottom',
                 fontsize=fontsize, color=color, alpha=alpha)
        return

    # Hauteur déduite du ratio du logo, corrigée par le format de la figure
    fig_width, fig_height = fig.get_size_inches()
    logo_ratio = logo.shape[1] / logo.shape[0]
    height = width * (fig_width / fig_height) / logo_ratio

    ax_logo = fig.add_axes((x, y, width, height), zorder=10)
    ax_logo.imshow(logo)
    ax_logo.axis('off')

def passes_map(player, df, team, match=None):
    df_pass = df.loc[(df['player'] == player) & (df['type'] == 'Pass')].dropna(subset=['location', 'pass_end_location'])
    mask_complete = df_pass.pass_outcome.isnull()

    # Créer des séries de données pour chaque type de passe
    pass_types = {
        'Completed': df_pass[mask_complete],
        'Assist': df_pass[df_pass["pass_goal_assist"] == True],
        'Missed': df_pass[~mask_complete]
    }

    total_completed_passes = len(pass_types['Completed'])
    total_missed_passes = len(pass_types['Missed'])
    percentage_completed_passes = round((total_completed_passes / (total_completed_passes + total_missed_passes)) * 100)

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86,
                      # Turn off the endnote/title axis. I usually do this after
                      # I am happy with the chart layout and text placement
                      axis=False)

    # Variables pour stocker les totaux des passes vers l'avant
    forward_passes_completed = 0
    forward_passes_missed = 0

    # Parcourir chaque type de passe et tracer les flèches correspondantes
    for label, data in pass_types.items():
        if not data.empty:
            location = data['location'].tolist()
            pass_end_location = data['pass_end_location'].tolist()
            x1 = pd.Series([el[0] for el in location])
            y1 = pd.Series([el[1] for el in location])
            x2 = pd.Series([el[0] for el in pass_end_location])
            y2 = pd.Series([el[1] for el in pass_end_location])
            color = '#3CD74A' if label == 'Completed' else '#F4D03F' if label == 'Assist' else '#F31515'

            # Compter le nombre de passes vers l'avant
            if label == 'Completed':
                forward_passes_completed += ((x2 > x1)).sum()
            elif label == 'Missed':
                forward_passes_missed += ((x2 > x1)).sum()

            pitch.arrows(x1, y1, x2, y2, width=2, headwidth=6, headlength=6, color=color, ax=axs['pitch'], label=label)

    # Calcul du pourcentage de passes vers l'avant
    total_forward_passes = forward_passes_completed + forward_passes_missed
    percentage_forward_passes = round((total_forward_passes / (total_completed_passes + total_missed_passes)) * 100)

    percentage_completed_forward_passes = round(forward_passes_completed / total_forward_passes * 100)
 
    col1, col2, col3 = st.columns(3)
    col1.metric("Completed passes", f"{total_completed_passes}/{total_completed_passes + total_missed_passes} ({percentage_completed_passes}%)",
                help="Successful passes that reached a teammate")
    col2.metric("Completed forward passes", f"{forward_passes_completed}/{total_forward_passes} ({percentage_completed_forward_passes}%)",
                help="Passes moving toward the opponent's goal that were successful")
    col3.metric("Forward play", f"{percentage_forward_passes}%",
                help="% of all passes that were played forward - indicates attacking intent")

    # Setup the legend
    axs['pitch'].legend(facecolor='#D4DADC', handlelength=5, edgecolor='None', fontsize=16, loc='upper left')

    # endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#000000')
    add_statsbomb_credit(fig)
    TITLE_TEXT = f'Passes of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
                    va='center', ha='center', fontsize=18)
    
    return fig, axs

def heatmap(player, df, team, match=None):

    # Filtrer les données du joueur spécifié
    df_heatmap = df.loc[df['player'] == player]

    # Récupérer les coordonnées des emplacements non nuls
    location = df_heatmap["location"].dropna().tolist()
    x = pd.Series([el[0] for el in location])
    y = pd.Series([el[1] for el in location])

    # Setup pitch
    pitch = Pitch(pitch_type='statsbomb', line_zorder=2, pitch_color='#22312b', line_color='#efefef')

    # Pitch with title
    fig, axs = pitch.grid(figheight=10, title_height=0.08, endnote_space=0,
                      grid_width=0.88, left=0.025, title_space=0,
                      axis=False, grid_height=0.82, endnote_height=0.05)
    
    fig.set_facecolor('#22312b')

    # Générer la heatmap
    bin_statistic = pitch.bin_statistic(x, y, statistic='count', bins=(25, 25))
    bin_statistic['statistic'] = gaussian_filter(bin_statistic['statistic'], 1)
    pcm = pitch.heatmap(bin_statistic, ax=axs['pitch'], cmap='hot', edgecolors='#22312b')  # YlOrRd

    # Ajouter la barre de couleur et formater en blanc cassé
    ax_cbar = fig.add_axes((0.915, 0.093, 0.03, 0.786))
    cbar = plt.colorbar(pcm, cax=ax_cbar)
    cbar.outline.set_edgecolor('#efefef')
    cbar.ax.yaxis.set_tick_params(color='#efefef')
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='#efefef')

    # endnote /title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', color='#ffffff',
                        va='center', ha='right', fontsize=15)
    add_statsbomb_credit(fig, color='#ffffff')
    TITLE_TEXT = f'Heatmap of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#ffffff',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#ffffff',
                    va='center', ha='center', fontsize=18)

    return fig, axs

def shots_map(player, df, team, match=None):
    # Filtrer les tirs du joueur spécifié
    shots = df.loc[(df['player'] == player) & (df['type'] == 'Shot')]
    
    # Définir les différents types de tirs
    shot_outcomes = {
        'On target': ['Saved', 'Saved To Post'],
        'Goal': ['Goal'],
        'Blocked': ['Blocked'],
        'Off target': ['Off T', 'Post', 'Wayward', 'Saved Off T']
    }
    
    # Préparer une liste pour stocker les séries de données de chaque type de tir
    series_to_plot = []

    # Parcourir les différents types de tirs et stocker les données correspondantes
    for label, outcomes in shot_outcomes.items():
        data = shots[shots["shot_outcome"].isin(outcomes)]
        if not data.empty:
            location = shots[shots["shot_outcome"].isin(outcomes)]['location'].tolist()
            end_location = shots[shots["shot_outcome"].isin(outcomes)]['shot_end_location'].tolist()
            x1 = pd.Series([el[0] for el in location])
            y1 = pd.Series([el[1] for el in location])
            x2 = pd.Series([el[0] for el in end_location])
            y2 = pd.Series([el[1] for el in end_location])
            color = '#F39C12' if label == 'Blocked' else '#3CD74A' if label == 'Goal' else '#F4D03F' if label == 'On target' else '#F31515'
            series_to_plot.append((x1, y1, x2, y2, color, label))

    # Calculer la somme des expected goals (xG) pour chaque tir
    total_xG = shots['shot_statsbomb_xg'].sum()
    total_goals = len(shots[shots['shot_outcome'] == 'Goal'])
    # Calculer la différence entre le nombre de buts marqués et la somme des expected goals
    goal_difference = total_goals - total_xG

    col1, col2 = st.columns(2)
    col1.metric("Goals", total_goals, help="Actual goals scored by the player")
    col2.metric("Expected goals (xG)", round(total_xG, 2), round(goal_difference, 2),
                help="Sum of shot probabilities. Delta shows over/under performance vs expectations")
    
    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86,
                      # Turn off the endnote/title axis. I usually do this after
                      # I am happy with the chart layout and text placement
                      axis=False)
    
    # Parcourir la liste et tracer les flèches pour chaque type de tir
    for x1, y1, x2, y2, color, label in series_to_plot:
        pitch.arrows(x1, y1, x2, y2, width=2, headwidth=6, headlength=6, color=color, ax=axs['pitch'], label=label)

    # Setup the legend
    axs['pitch'].legend(facecolor='#D4DADC', handlelength=5, edgecolor='None', fontsize=16, loc='upper left')

    # endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#000000')
    add_statsbomb_credit(fig)
    TITLE_TEXT = f'Shots of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
                    va='center', ha='center', fontsize=18)
    
    return fig, axs

def carries_map(player, df, team, match=None):
    """Visualize ball carries for a specific player."""
    # Filter carries for the specified player
    df_carry = df.loc[(df['player'] == player) & (df['type'] == 'Carry')].dropna(subset=['location', 'carry_end_location'])

    if df_carry.empty:
        st.warning(f"No carry data available for {player}")
        # Return empty pitch
        pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
        fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                          title_height=0.06, title_space=0, grid_height=0.86, axis=False)
        return fig, axs

    # Extract coordinates
    location = df_carry['location'].tolist()
    carry_end_location = df_carry['carry_end_location'].tolist()
    x1 = pd.Series([el[0] for el in location])
    y1 = pd.Series([el[1] for el in location])
    x2 = pd.Series([el[0] for el in carry_end_location])
    y2 = pd.Series([el[1] for el in carry_end_location])

    # Calculate carry distances
    distances = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

    # Identify progressive carries (moving towards goal, x2 > x1)
    progressive_mask = x2 > x1
    progressive_carries = progressive_mask.sum()

    # Calculate metrics
    total_carries = len(df_carry)
    total_distance = distances.sum()
    avg_distance = distances.mean()
    progressive_distance = distances[progressive_mask].sum()

    # Display metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Carries", total_carries, help="Times the player moved with the ball at their feet")
    col2.metric("Progressive Carries", f"{progressive_carries} ({round(progressive_carries/total_carries*100)}%)",
                help="Carries moving toward opponent's goal - indicates ball progression ability")
    col3.metric("Total Distance", f"{round(total_distance, 1)}m",
                help="Combined distance of all carries - shows range of ball movement")

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86, axis=False)

    # Plot progressive carries (green) and non-progressive carries (blue)
    if progressive_mask.any():
        pitch.arrows(x1[progressive_mask], y1[progressive_mask],
                    x2[progressive_mask], y2[progressive_mask],
                    width=2, headwidth=6, headlength=6, color='#3CD74A',
                    ax=axs['pitch'], label='Progressive')

    if (~progressive_mask).any():
        pitch.arrows(x1[~progressive_mask], y1[~progressive_mask],
                    x2[~progressive_mask], y2[~progressive_mask],
                    width=2, headwidth=6, headlength=6, color='#3498DB',
                    ax=axs['pitch'], label='Non-progressive')

    # Setup the legend
    axs['pitch'].legend(facecolor='#D4DADC', handlelength=5, edgecolor='None', fontsize=16, loc='upper left')

    # Endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#000000')
    add_statsbomb_credit(fig)
    TITLE_TEXT = f'Carries of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
                    va='center', ha='center', fontsize=18)

    return fig, axs

def dribbles_map(player, df, team, match=None):
    """Visualize dribbles for a specific player."""
    # Filter dribbles for the specified player
    df_dribble = df.loc[(df['player'] == player) & (df['type'] == 'Dribble')].dropna(subset=['location'])

    if df_dribble.empty:
        st.warning(f"No dribble data available for {player}")
        # Return empty pitch
        pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
        fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                          title_height=0.06, title_space=0, grid_height=0.86, axis=False)
        return fig, axs

    # Extract coordinates
    location = df_dribble['location'].tolist()
    x = pd.Series([el[0] for el in location])
    y = pd.Series([el[1] for el in location])

    # Separate successful and unsuccessful dribbles
    successful_mask = df_dribble['dribble_outcome'] == 'Complete'
    successful_count = successful_mask.sum()
    unsuccessful_count = (~successful_mask).sum()
    total_dribbles = len(df_dribble)
    success_rate = round(successful_count / total_dribbles * 100) if total_dribbles > 0 else 0

    # Display metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Dribbles", total_dribbles, help="1v1 attempts to beat a defender")
    col2.metric("Successful", f"{successful_count} ({success_rate}%)",
                help="Dribbles where the player kept possession. >60% is excellent")
    col3.metric("Unsuccessful", unsuccessful_count,
                help="Dribbles where possession was lost - high risk attempts")

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86, axis=False)

    # Plot successful dribbles (green) and unsuccessful dribbles (red)
    x_success = x[successful_mask.values]
    y_success = y[successful_mask.values]
    x_fail = x[~successful_mask.values]
    y_fail = y[~successful_mask.values]

    if len(x_success) > 0:
        pitch.scatter(x_success, y_success, s=200, color='#3CD74A', edgecolors='#000000',
                     linewidth=1.5, ax=axs['pitch'], label='Successful', zorder=2)

    if len(x_fail) > 0:
        pitch.scatter(x_fail, y_fail, s=200, color='#F31515', edgecolors='#000000',
                     linewidth=1.5, ax=axs['pitch'], label='Unsuccessful', zorder=2)

    # Setup the legend
    axs['pitch'].legend(facecolor='#D4DADC', handlelength=2, edgecolor='None', fontsize=16, loc='upper left')

    # Endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#000000')
    add_statsbomb_credit(fig)
    TITLE_TEXT = f'Dribbles of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
                    va='center', ha='center', fontsize=18)

    return fig, axs

# ==================== DEFENSIVE STATISTICS ====================

# Couleur et marqueur par type d'action défensive. Les marqueurs diffèrent pour que la
# carte reste lisible en niveaux de gris (impression, export PDF noir et blanc).
DEFENSIVE_ACTIONS = {
    'Pressure':      ('#F4D03F', 'o'),
    'Ball Recovery': ('#3CD74A', 's'),
    'Duel':          ('#F31515', '^'),
    'Interception':  ('#3498DB', 'D'),
    'Block':         ('#9B59B6', 'P'),
    'Clearance':     ('#E67E22', 'X'),
}

# Un duel gagné se lit sur duel_outcome, sauf pour les duels aériens perdus que StatsBomb
# encode dans duel_type sans renseigner d'outcome.
DUEL_WON_OUTCOMES = ['Won', 'Success', 'Success In Play', 'Success Out']

# PPDA : passes concédées par action défensive. Le calcul classique ne retient que les
# tacles, interceptions et fautes (le Pressure n'existe pas dans le modèle d'origine) et
# se limite aux 60% de terrain les plus avancés, soit x >= 48 sur un terrain de 120.
PPDA_ACTION_TYPES = ['Duel', 'Interception', 'Foul Committed']
PPDA_ZONE_START = 48

PITCH_LENGTH = 120
FINAL_THIRD_START = 80


def _action_x(df):
    """ Abscisses des évènements localisés, en unités terrain StatsBomb (0-120). """
    located = df.dropna(subset=['location'])
    return pd.Series([loc[0] for loc in located['location']], dtype='float64')


def _empty_pitch(message, pitch_color='#FFFFFF', line_color='#000000'):
    """ Terrain vide renvoyé quand aucune action ne correspond au filtre. """
    st.warning(message)
    pitch = Pitch(pitch_type='statsbomb', pitch_color=pitch_color, line_color=line_color)
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                          title_height=0.06, title_space=0, grid_height=0.86, axis=False)
    if pitch_color != '#FFFFFF':
        fig.set_facecolor(pitch_color)
    return fig, axs


def compute_ppda(df, team):
    """
    PPDA d'une équipe : passes adverses concédées par action défensive dans la zone de
    pressing. Renvoie None si l'adversaire est absent des données ou si l'équipe n'a
    réalisé aucune action défensive dans la zone.

    StatsBomb oriente les coordonnées de chaque équipe vers le but adverse : la même zone
    physique s'écrit x >= 48 pour l'équipe qui presse et x <= 72 pour celle qui construit.
    """
    opponents = [t for t in df['team'].dropna().unique() if t != team]
    if not opponents:
        return None

    opp_passes = df.loc[df['team'].isin(opponents) & (df['type'] == 'Pass')]
    passes_in_zone = (_action_x(opp_passes) <= PITCH_LENGTH - PPDA_ZONE_START).sum()

    actions = df.loc[(df['team'] == team) & (df['type'].isin(PPDA_ACTION_TYPES))]
    actions_in_zone = (_action_x(actions) >= PPDA_ZONE_START).sum()

    if actions_in_zone == 0:
        return None

    return float(passes_in_zone) / float(actions_in_zone)


def defensive_actions_map(player, df, team, match=None):
    """Visualize the defensive actions of a specific player."""
    # Filter the player's defensive actions
    df_def = df.loc[(df['player'] == player) &
                    (df['type'].isin(DEFENSIVE_ACTIONS))].dropna(subset=['location'])

    if df_def.empty:
        return _empty_pitch(f"No defensive action available for {player}")

    # Duels: 'Aerial Lost' is a loss that StatsBomb leaves without an outcome
    duels = df_def[df_def['type'] == 'Duel']
    duels_won = duels['duel_outcome'].isin(DUEL_WON_OUTCOMES).sum()
    duel_rate = round(duels_won / len(duels) * 100) if len(duels) > 0 else 0

    x_all = _action_x(df_def)
    avg_height = round(x_all.mean() / PITCH_LENGTH * 100)
    final_third = int((x_all >= FINAL_THIRD_START).sum())

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Defensive Actions", len(df_def),
                help="Pressures, recoveries, duels, interceptions, blocks and clearances")
    col2.metric("Duels Won", f"{duels_won}/{len(duels)} ({duel_rate}%)",
                help="Tackles and aerial duels won. >50% is solid for an outfield player")
    col3.metric("Avg Height", f"{avg_height}%",
                help="Average position of the actions along the pitch. 0% = own goal, 100% = opponent goal")
    col4.metric("In Final Third", final_third,
                help="Actions in the opponent's third - a marker of high pressing")

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#FFFFFF', line_color='#000000')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86, axis=False)

    # One scatter per action type, ordered by frequency so rare actions stay on top
    for action_type in sorted(df_def['type'].unique(),
                              key=lambda t: -(df_def['type'] == t).sum()):
        color, marker = DEFENSIVE_ACTIONS[action_type]
        data = df_def[df_def['type'] == action_type]
        x = _action_x(data)
        y = pd.Series([loc[1] for loc in data['location']], dtype='float64')
        pitch.scatter(x, y, s=180, color=color, marker=marker, edgecolors='#000000',
                      linewidth=1.2, alpha=0.85, ax=axs['pitch'],
                      label=f'{action_type} ({len(data)})', zorder=2)

    # Average height of the actions, a proxy for how high the player defends
    axs['pitch'].axvline(x=x_all.mean(), color='#000000', linestyle='--',
                         linewidth=2, alpha=0.6, zorder=1)

    # Setup the legend
    axs['pitch'].legend(facecolor='#D4DADC', handlelength=2, edgecolor='None',
                        fontsize=14, loc='upper left')

    # Endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#000000')
    add_statsbomb_credit(fig)
    TITLE_TEXT = f'Defensive Actions of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
                    va='center', ha='center', fontsize=18)

    return fig, axs


def defensive_shape(df, team, match=None):
    """Visualize where a team defends, as a zone grid with its pressing intensity."""
    df_def = df.loc[(df['team'] == team) &
                    (df['type'].isin(DEFENSIVE_ACTIONS))].dropna(subset=['location'])

    if df_def.empty:
        return _empty_pitch(f"No defensive action available for {team}",
                            pitch_color='#22312b', line_color='#efefef')

    x = _action_x(df_def)
    y = pd.Series([loc[1] for loc in df_def['location']], dtype='float64')

    avg_height = round(x.mean() / PITCH_LENGTH * 100)
    opponent_half = round((x >= PITCH_LENGTH / 2).sum() / len(x) * 100)
    ppda = compute_ppda(df, team)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Defensive Actions", len(df_def),
                help="All defensive events recorded for the team")
    col2.metric("PPDA", round(ppda, 1) if ppda is not None else "N/A",
                help="Opponent passes allowed per defensive action in the pressing zone. "
                     "Lower = more aggressive press. Below 10 is intense")
    col3.metric("Avg Height", f"{avg_height}%",
                help="Average position of the defensive actions. Above 50% = the team defends high")
    col4.metric("In Opponent Half", f"{opponent_half}%",
                help="Share of defensive actions won in the opponent's half")

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', line_zorder=2, pitch_color='#22312b', line_color='#efefef')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86, axis=False)
    fig.set_facecolor('#22312b')

    # Zone grid rather than a smoothed heatmap: the raw count per zone is the readable
    # unit here, and 6x5 matches how a defensive block is usually described
    bin_statistic = pitch.bin_statistic(x, y, statistic='count', bins=(6, 5))
    pitch.heatmap(bin_statistic, ax=axs['pitch'], cmap='Reds', edgecolors='#22312b', alpha=0.85)
    # Contour blanc : le compteur doit rester lisible aussi bien sur les zones pâles que
    # sur le rouge le plus sombre, qui absorbe un texte noir
    pitch.label_heatmap(bin_statistic, color='#000000', fontsize=16, ax=axs['pitch'],
                        ha='center', va='center', str_format='{:.0f}', zorder=3,
                        path_effects=[path_effects.withStroke(linewidth=2.5, foreground='#FFFFFF')])

    # Average height line, annotated so the number is readable off the chart alone.
    # L'axe y du terrain StatsBomb est inversé : va='bottom' place le texte au-dessus
    # de la ligne de touche basse, dans le terrain.
    axs['pitch'].axvline(x=x.mean(), color='#efefef', linestyle='--', linewidth=2.5, zorder=3)
    axs['pitch'].text(x.mean() + 1.5, 77, f'Avg height {avg_height}%', color='#efefef',
                      fontsize=14, va='bottom', ha='left', zorder=3)

    # Endnote and title. Le sens de jeu va dans l'endnote : sans lui, la hauteur du bloc
    # se lit à l'envers.
    axs['endnote'].text(0, 0.5, 'Attacking direction  >>', va='center', ha='left',
                        fontsize=15, color='#efefef')
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#efefef')
    add_statsbomb_credit(fig, color='#efefef')
    TITLE_TEXT = f'Defensive Shape - {team}'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#efefef',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#efefef',
                    va='center', ha='center', fontsize=18)

    return fig, axs

# ==================== TEAM STATISTICS ====================

def pass_network(df, team, match=None):
    """Visualize the pass network for a team showing connections between players."""
    # Filter completed passes for the team
    df_pass = df.loc[(df['team'] == team) & (df['type'] == 'Pass')].dropna(subset=['location', 'pass_end_location'])
    df_pass = df_pass[df_pass['pass_outcome'].isnull()]  # Only completed passes

    if df_pass.empty:
        st.warning(f"No pass data available for {team}")
        pitch = Pitch(pitch_type='statsbomb', pitch_color='#22312b', line_color='#efefef')
        fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                          title_height=0.06, title_space=0, grid_height=0.86, axis=False)
        fig.set_facecolor('#22312b')
        return fig, axs

    # Get pass recipient
    df_pass = df_pass[df_pass['pass_recipient'].notna()]

    # Calculate average positions for each player
    player_positions = {}
    for player in df_pass['player'].unique():
        player_events = df[(df['player'] == player) & (df['team'] == team)].dropna(subset=['location'])
        if not player_events.empty:
            locations = player_events['location'].tolist()
            avg_x = np.mean([loc[0] for loc in locations])
            avg_y = np.mean([loc[1] for loc in locations])
            player_positions[player] = {'x': avg_x, 'y': avg_y}

    # Count passes between players
    pass_counts = df_pass.groupby(['player', 'pass_recipient']).size().reset_index(name='count')

    # Count total passes per player (for node size)
    player_pass_counts = df_pass.groupby('player').size().to_dict()

    # Setup the pitch
    pitch = Pitch(pitch_type='statsbomb', pitch_color='#22312b', line_color='#efefef')
    fig, axs = pitch.grid(endnote_height=0.03, endnote_space=0, figheight=12,
                      title_height=0.06, title_space=0, grid_height=0.86, axis=False)
    fig.set_facecolor('#22312b')

    # Draw pass connections (lines)
    max_count = pass_counts['count'].max() if not pass_counts.empty else 1
    for _, row in pass_counts.iterrows():
        passer = row['player']
        recipient = row['pass_recipient']
        count = row['count']

        if passer in player_positions and recipient in player_positions:
            x1, y1 = player_positions[passer]['x'], player_positions[passer]['y']
            x2, y2 = player_positions[recipient]['x'], player_positions[recipient]['y']

            # Line width based on pass frequency (min 1, max 8)
            line_width = 1 + (count / max_count) * 7
            alpha = 0.3 + (count / max_count) * 0.5

            axs['pitch'].plot([x1, x2], [y1, y2], color='#E74C3C', linewidth=line_width,
                             alpha=alpha, zorder=1)

    # Draw player nodes
    max_passes = max(player_pass_counts.values()) if player_pass_counts else 1
    for player, pos in player_positions.items():
        passes = player_pass_counts.get(player, 0)
        # Node size based on number of passes (min 300, max 1500)
        node_size = 300 + (passes / max_passes) * 1200

        pitch.scatter(pos['x'], pos['y'], s=node_size, color='#3498DB',
                     edgecolors='#FFFFFF', linewidth=2, ax=axs['pitch'], zorder=2)

        # Add player name (shortened)
        name_parts = player.split()
        short_name = name_parts[-1] if len(name_parts) > 1 else player
        axs['pitch'].annotate(short_name, (pos['x'], pos['y']), color='#FFFFFF',
                             fontsize=8, ha='center', va='center', fontweight='bold', zorder=3)

    # Metrics
    total_passes = len(df_pass)
    unique_connections = len(pass_counts)
    avg_passes_per_connection = round(total_passes / unique_connections, 1) if unique_connections > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Passes", total_passes, help="Completed passes between teammates")
    col2.metric("Unique Connections", unique_connections,
                help="Different player-to-player passing combinations used")
    col3.metric("Avg Passes/Connection", avg_passes_per_connection,
                help="How often each connection was used - higher = more repetitive patterns")

    # Endnote and title
    axs['endnote'].text(1, 0.5, '@alex.mrl38', va='center', ha='right', fontsize=20, color='#FFFFFF')
    add_statsbomb_credit(fig, color='#FFFFFF')
    TITLE_TEXT = f'Pass Network - {team}'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#FFFFFF',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#FFFFFF',
                    va='center', ha='center', fontsize=18)

    return fig, axs

def xg_timeline(df, team, match=None):
    """Visualize xG accumulation over time for both teams."""
    # Get both teams
    teams = df['team'].unique()
    team_1 = teams[0]
    team_2 = teams[1] if len(teams) > 1 else None

    # Filter shots for both teams
    shots = df[df['type'] == 'Shot'].copy()

    if shots.empty:
        st.warning("No shot data available for this match")
        fig, ax = plt.subplots(figsize=(12, 6))
        return fig, ax

    # Sort by minute
    shots = shots.sort_values('minute')

    # Calculate cumulative xG for each team
    shots_team1 = shots[shots['team'] == team_1].copy()
    shots_team2 = shots[shots['team'] == team_2].copy() if team_2 else pd.DataFrame()

    # Add cumulative xG
    shots_team1['cumulative_xg'] = shots_team1['shot_statsbomb_xg'].cumsum()
    if not shots_team2.empty:
        shots_team2['cumulative_xg'] = shots_team2['shot_statsbomb_xg'].cumsum()

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 7))
    fig.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    # Colors for teams
    color_1 = '#E74C3C'  # Red
    color_2 = '#3498DB'  # Blue

    # Plot team 1 xG line
    if not shots_team1.empty:
        # Add starting point at 0
        minutes_1 = [0] + shots_team1['minute'].tolist()
        xg_1 = [0] + shots_team1['cumulative_xg'].tolist()

        ax.step(minutes_1, xg_1, where='post', color=color_1, linewidth=2.5, label=team_1)

        # Plot shot points
        for _, shot in shots_team1.iterrows():
            marker = '*' if shot['shot_outcome'] == 'Goal' else 'o'
            size = 150 if shot['shot_outcome'] == 'Goal' else 50 + shot['shot_statsbomb_xg'] * 200
            ax.scatter(shot['minute'], shot['cumulative_xg'], s=size, color=color_1,
                      marker=marker, edgecolors='white', linewidth=1.5, zorder=5)

    # Plot team 2 xG line
    if not shots_team2.empty:
        minutes_2 = [0] + shots_team2['minute'].tolist()
        xg_2 = [0] + shots_team2['cumulative_xg'].tolist()

        ax.step(minutes_2, xg_2, where='post', color=color_2, linewidth=2.5, label=team_2)

        # Plot shot points
        for _, shot in shots_team2.iterrows():
            marker = '*' if shot['shot_outcome'] == 'Goal' else 'o'
            size = 150 if shot['shot_outcome'] == 'Goal' else 50 + shot['shot_statsbomb_xg'] * 200
            ax.scatter(shot['minute'], shot['cumulative_xg'], s=size, color=color_2,
                      marker=marker, edgecolors='white', linewidth=1.5, zorder=5)

    # Add half-time line
    ax.axvline(x=45, color='#ffffff', linestyle='--', alpha=0.5, linewidth=1)
    ax.text(45, ax.get_ylim()[1] * 0.95, 'HT', color='#ffffff', alpha=0.7,
            ha='center', fontsize=10)

    # Styling
    ax.set_xlabel('Minute', color='#ffffff', fontsize=12)
    ax.set_ylabel('Cumulative xG', color='#ffffff', fontsize=12)
    ax.tick_params(colors='#ffffff')
    ax.spines['bottom'].set_color('#ffffff')
    ax.spines['left'].set_color('#ffffff')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.2, color='#ffffff')
    ax.set_xlim(0, max(shots['minute'].max() + 5, 90))
    ax.set_ylim(0, None)

    # Legend
    legend = ax.legend(loc='upper left', facecolor='#1a1a2e', edgecolor='#ffffff',
                       fontsize=11, labelcolor='#ffffff')

    # Title
    title = f'xG Timeline'
    if match:
        title += f'\n{match}'
    ax.set_title(title, color='#ffffff', fontsize=16, fontweight='bold', pad=15)

    # Add endnote
    fig.text(0.95, 0.02, '@alex.mrl38', ha='right', va='bottom',
             fontsize=10, color='#ffffff', alpha=0.7)

    # Add legend for markers
    fig.text(0.15, 0.02, '● Shot   ★ Goal', ha='left', va='bottom',
             fontsize=9, color='#ffffff', alpha=0.7)

    plt.tight_layout()

    # Après tight_layout, qui ne doit pas prendre l'axe du logo dans son calcul
    add_statsbomb_credit(fig, x=0.01, width=0.11, color='#ffffff', alpha=0.7)

    # Metrics
    total_xg_1 = shots_team1['shot_statsbomb_xg'].sum() if not shots_team1.empty else 0
    total_xg_2 = shots_team2['shot_statsbomb_xg'].sum() if not shots_team2.empty else 0
    goals_1 = len(shots_team1[shots_team1['shot_outcome'] == 'Goal']) if not shots_team1.empty else 0
    goals_2 = len(shots_team2[shots_team2['shot_outcome'] == 'Goal']) if not shots_team2.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"{team_1} xG", round(total_xg_1, 2),
                help="Expected Goals - sum of all shot probabilities")
    col2.metric(f"{team_1} Goals", goals_1, round(goals_1 - total_xg_1, 2),
                help="Actual goals. Delta shows finishing efficiency vs expected")
    col3.metric(f"{team_2} xG", round(total_xg_2, 2),
                help="Expected Goals - sum of all shot probabilities")
    col4.metric(f"{team_2} Goals", goals_2, round(goals_2 - total_xg_2, 2),
                help="Actual goals. Delta shows finishing efficiency vs expected")

    return fig, ax

def match_summary(df, match=None):
    """Create a match summary dashboard showing key stats for both teams."""
    teams = df['team'].unique()
    team_1 = teams[0]
    team_2 = teams[1] if len(teams) > 1 else None

    def get_team_stats(df, team):
        """Calculate comprehensive stats for a team."""
        team_events = df[df['team'] == team]

        # Passes
        passes = team_events[team_events['type'] == 'Pass']
        total_passes = len(passes)
        completed_passes = len(passes[passes['pass_outcome'].isnull()])
        pass_accuracy = round((completed_passes / total_passes * 100), 1) if total_passes > 0 else 0

        # Shots
        shots = team_events[team_events['type'] == 'Shot']
        total_shots = len(shots)
        shots_on_target = len(shots[shots['shot_outcome'].isin(['Goal', 'Saved', 'Saved To Post'])])
        goals = len(shots[shots['shot_outcome'] == 'Goal'])
        xg = round(shots['shot_statsbomb_xg'].sum(), 2) if not shots.empty else 0

        # Possession (approximation based on events)
        total_events = len(df[df['type'].isin(['Pass', 'Carry', 'Dribble', 'Ball Receipt*'])])
        team_possession_events = len(team_events[team_events['type'].isin(['Pass', 'Carry', 'Dribble', 'Ball Receipt*'])])
        possession = round((team_possession_events / total_events * 100), 1) if total_events > 0 else 0

        # Corners
        corners = len(passes[passes['pass_type'] == 'Corner'])

        # Free kicks
        free_kicks = len(passes[passes['pass_type'] == 'Free Kick'])

        # Fouls
        fouls_committed = len(team_events[team_events['type'] == 'Foul Committed'])

        # Cards
        cards = team_events[team_events['type'].isin(['Foul Committed'])]
        yellow_cards = len(cards[cards['foul_committed_card'] == 'Yellow Card']) if 'foul_committed_card' in cards.columns else 0
        red_cards = len(cards[cards['foul_committed_card'] == 'Red Card']) if 'foul_committed_card' in cards.columns else 0

        # Dribbles
        dribbles = team_events[team_events['type'] == 'Dribble']
        successful_dribbles = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])

        # Tackles
        tackles = len(team_events[team_events['type'] == 'Tackle'])
        interceptions = len(team_events[team_events['type'] == 'Interception'])

        return {
            'Goals': goals,
            'xG': xg,
            'Shots': total_shots,
            'Shots on Target': shots_on_target,
            'Possession': possession,
            'Passes': completed_passes,
            'Pass Accuracy': pass_accuracy,
            'Corners': corners,
            'Free Kicks': free_kicks,
            'Fouls': fouls_committed,
            'Yellow Cards': yellow_cards,
            'Red Cards': red_cards,
            'Dribbles Won': successful_dribbles,
            'Tackles': tackles,
            'Interceptions': interceptions
        }

    stats1 = get_team_stats(df, team_1)
    stats2 = get_team_stats(df, team_2) if team_2 else {}

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')
    ax.axis('off')

    # Title
    title = f"{team_1}  {stats1['Goals']} - {stats2.get('Goals', 0)}  {team_2}"
    ax.text(0.5, 0.95, title, ha='center', va='top', fontsize=24,
            color='#ffffff', fontweight='bold', transform=ax.transAxes)
    if match:
        ax.text(0.5, 0.89, match, ha='center', va='top', fontsize=12,
                color='#ffffff', alpha=0.7, transform=ax.transAxes)

    # Stats to display (excluding Goals which is in title)
    display_stats = ['xG', 'Shots', 'Shots on Target', 'Possession', 'Passes',
                    'Pass Accuracy', 'Corners', 'Fouls', 'Dribbles Won', 'Tackles', 'Interceptions']

    y_start = 0.82
    y_step = 0.065

    for i, stat in enumerate(display_stats):
        y = y_start - (i * y_step)
        v1 = stats1[stat]
        v2 = stats2.get(stat, 0)

        # Add % for percentage stats
        suffix = '%' if stat in ['Possession', 'Pass Accuracy'] else ''

        # Draw stat name in center
        ax.text(0.5, y, stat, ha='center', va='center', fontsize=12,
                color='#ffffff', alpha=0.8, transform=ax.transAxes)

        # Draw values
        ax.text(0.15, y, f"{v1}{suffix}", ha='center', va='center', fontsize=14,
                color='#E74C3C', fontweight='bold', transform=ax.transAxes)
        ax.text(0.85, y, f"{v2}{suffix}", ha='center', va='center', fontsize=14,
                color='#3498DB', fontweight='bold', transform=ax.transAxes)

        # Draw comparison bar
        total = v1 + v2 if (v1 + v2) > 0 else 1
        ratio1 = v1 / total

        bar_width = 0.25
        bar_left = 0.25
        bar_right = 0.75

        # Team 1 bar (from center to left)
        ax.barh(y, ratio1 * bar_width, left=0.5 - ratio1 * bar_width, height=0.025,
                color='#E74C3C', alpha=0.7, transform=ax.transAxes)
        # Team 2 bar (from center to right)
        ax.barh(y, (1 - ratio1) * bar_width, left=0.5, height=0.025,
                color='#3498DB', alpha=0.7, transform=ax.transAxes)

    # Team names at bottom
    ax.text(0.15, 0.05, team_1, ha='center', va='center', fontsize=14,
            color='#E74C3C', fontweight='bold', transform=ax.transAxes)
    ax.text(0.85, 0.05, team_2, ha='center', va='center', fontsize=14,
            color='#3498DB', fontweight='bold', transform=ax.transAxes)

    # Endnote
    ax.text(0.5, 0.01, '@alex.mrl38', ha='center', va='bottom', fontsize=9,
            color='#ffffff', alpha=0.5, transform=ax.transAxes)

    plt.tight_layout()

    # Après tight_layout, qui ne doit pas prendre l'axe du logo dans son calcul
    add_statsbomb_credit(fig, color='#ffffff', alpha=0.5)

    return fig, ax

# ==================== COMPARISON STATISTICS ====================

def player_comparison_radar(df, player1, player2, team1, team2, match=None):
    """Create a radar chart comparing two players across multiple metrics."""

    def calculate_player_stats(df, player, team):
        """Calculate stats for a single player."""
        player_events = df[(df['player'] == player) & (df['team'] == team)]

        # Passes
        passes = player_events[player_events['type'] == 'Pass']
        total_passes = len(passes)
        completed_passes = len(passes[passes['pass_outcome'].isnull()])
        pass_accuracy = round((completed_passes / total_passes * 100), 1) if total_passes > 0 else 0

        # Forward passes
        passes_with_loc = passes.dropna(subset=['location', 'pass_end_location'])
        if not passes_with_loc.empty:
            locations = passes_with_loc['location'].tolist()
            end_locations = passes_with_loc['pass_end_location'].tolist()
            forward_passes = sum(1 for i, loc in enumerate(locations)
                               if end_locations[i][0] > loc[0])
        else:
            forward_passes = 0

        # Shots
        shots = player_events[player_events['type'] == 'Shot']
        total_shots = len(shots)
        goals = len(shots[shots['shot_outcome'] == 'Goal'])
        xg = shots['shot_statsbomb_xg'].sum() if not shots.empty else 0

        # Dribbles
        dribbles = player_events[player_events['type'] == 'Dribble']
        total_dribbles = len(dribbles)
        successful_dribbles = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])
        dribble_success = round((successful_dribbles / total_dribbles * 100), 1) if total_dribbles > 0 else 0

        # Carries
        carries = player_events[player_events['type'] == 'Carry'].dropna(subset=['location', 'carry_end_location'])
        total_carries = len(carries)
        if not carries.empty:
            locations = carries['location'].tolist()
            end_locations = carries['carry_end_location'].tolist()
            progressive_carries = sum(1 for i, loc in enumerate(locations)
                                     if end_locations[i][0] > loc[0])
        else:
            progressive_carries = 0

        # Ball recoveries
        ball_recoveries = len(player_events[player_events['type'] == 'Ball Recovery'])

        # Defensive actions (tackles, interceptions, clearances)
        defensive_actions = len(player_events[player_events['type'].isin(['Tackle', 'Interception', 'Clearance'])])

        return {
            'Passes': completed_passes,
            'Pass Accuracy': pass_accuracy,
            'Forward Passes': forward_passes,
            'Shots': total_shots,
            'Goals': goals,
            'xG': round(xg, 2),
            'Dribbles Won': successful_dribbles,
            'Dribble %': dribble_success,
            'Carries': total_carries,
            'Progressive Carries': progressive_carries,
            'Ball Recoveries': ball_recoveries,
            'Defensive Actions': defensive_actions
        }

    # Calculate stats for both players
    stats1 = calculate_player_stats(df, player1, team1)
    stats2 = calculate_player_stats(df, player2, team2)

    # Select metrics for radar (excluding percentages that need different scaling)
    radar_metrics = ['Passes', 'Forward Passes', 'Shots', 'Goals', 'Dribbles Won',
                    'Carries', 'Progressive Carries', 'Ball Recoveries', 'Defensive Actions']

    values1 = [stats1[m] for m in radar_metrics]
    values2 = [stats2[m] for m in radar_metrics]

    # Calculate ranges for radar (min=0, max=max of both players + buffer)
    low = [0] * len(radar_metrics)
    high = [max(v1, v2, 1) * 1.2 for v1, v2 in zip(values1, values2)]  # 20% buffer

    # Create radar chart
    radar = Radar(radar_metrics, low, high,
                  round_int=[True] * len(radar_metrics),
                  num_rings=4,
                  ring_width=1,
                  center_circle_radius=1)

    # Create figure
    fig, axs = radar.setup_axis()
    fig.set_facecolor('#1a1a2e')

    # Plot both players
    rings_inner = radar.draw_circles(ax=axs, facecolor='#1a1a2e', edgecolor='#ffffff', alpha=0.1)
    radar_output1 = radar.draw_radar(values1, ax=axs,
                                      kwargs_radar={'facecolor': '#E74C3C', 'alpha': 0.6},
                                      kwargs_rings={'facecolor': '#E74C3C', 'alpha': 0.1})
    radar_output2 = radar.draw_radar(values2, ax=axs,
                                      kwargs_radar={'facecolor': '#3498DB', 'alpha': 0.6},
                                      kwargs_rings={'facecolor': '#3498DB', 'alpha': 0.1})

    # Draw range labels and parameter labels
    radar.draw_range_labels(ax=axs, fontsize=8, color='#ffffff', alpha=0.7)
    radar.draw_param_labels(ax=axs, fontsize=10, color='#ffffff')

    # Add title
    title = f'{player1} vs {player2}'
    fig.text(0.5, 0.97, title, ha='center', va='top', fontsize=16,
             color='#ffffff', fontweight='bold')
    if match:
        fig.text(0.5, 0.93, match, ha='center', va='top', fontsize=11, color='#ffffff', alpha=0.8)

    # Add legend
    fig.text(0.15, 0.05, f'● {player1.split()[-1]}', ha='left', va='bottom',
             fontsize=11, color='#E74C3C', fontweight='bold')
    fig.text(0.85, 0.05, f'● {player2.split()[-1]}', ha='right', va='bottom',
             fontsize=11, color='#3498DB', fontweight='bold')

    # Add endnote
    fig.text(0.5, 0.02, '@alex.mrl38', ha='center', va='bottom',
             fontsize=9, color='#ffffff', alpha=0.5)
    add_statsbomb_credit(fig, color='#ffffff', alpha=0.5)

    # Display detailed stats comparison
    st.markdown("##### Detailed Comparison")
    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        st.markdown(f"**{player1}** ({team1})")
    with col2:
        st.markdown("**Metric**")
    with col3:
        st.markdown(f"**{player2}** ({team2})")

    for metric in radar_metrics + ['Pass Accuracy', 'Dribble %', 'xG']:
        col1, col2, col3 = st.columns([2, 1, 2])
        v1, v2 = stats1[metric], stats2[metric]

        # Highlight winner
        if v1 > v2:
            col1.markdown(f"**:green[{v1}]**")
            col3.markdown(f"{v2}")
        elif v2 > v1:
            col1.markdown(f"{v1}")
            col3.markdown(f"**:green[{v2}]**")
        else:
            col1.markdown(f"{v1}")
            col3.markdown(f"{v2}")
        col2.markdown(f"*{metric}*")

    return fig, axs

# Fonction pour vérifier les colonnes requises
def check_required_columns(df, required_cols):
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return False, missing_detail(missing_cols)
    return True, None

# Fonction pour détailler les colonnes manquantes
def missing_detail(cols):
    return f"Missing columns: {', '.join(cols)}"

def try_read_json(uploaded_file):
    """ Tente de lire un fichier JSON et gère les erreurs potentielles. """
    try:
        df = pd.read_json(uploaded_file)
        return df
    except ValueError as e:
        # Gestion d'erreurs spécifiques à la lecture JSON, e.g., données malformées
        st.error(f"Failed to read JSON file. The file format might be incorrect. Error: {e}")
        st.stop()  # Stop further execution if columns are missing
    except Exception as e:
        # Gestion de toute autre exception non prévue
        st.error(f"An unexpected error occurred: {e}")
        st.stop()  # Stop further execution if columns are missing

# ==================== STATSBOMB OPEN DATA ====================

# Le catalogue (compétitions, calendriers) bouge rarement : cache d'une journée.
# Les évènements d'un match donné ne changent jamais : cache sans expiration.
CATALOG_TTL = 60 * 60 * 24

# Téléchargements simultanés en mode Multi-Match : au-delà, l'API open data
# ne va pas plus vite et on multiplie les risques de throttling.
MAX_PARALLEL_DOWNLOADS = 6


def _sb_call(func, **kwargs):
    """ Appelle statsbombpy en masquant le NoAuthWarning (accès open data sans identifiants). """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return func(**kwargs)


def competition_label(row):
    """ Nom lisible d'une compétition, ex: 'England - FA Women's Super League (women)'. """
    label = f"{row['country_name']} - {row['competition_name']}"
    tags = []
    if row.get('competition_gender') == 'female':
        tags.append('women')
    if row.get('competition_youth'):
        tags.append('youth')
    return f"{label} ({', '.join(tags)})" if tags else label


def match_label(row):
    """ Nom lisible d'un match, ex: 'Barcelona 4-1 Huesca (2021-03-15)'. """
    if pd.notna(row['home_score']) and pd.notna(row['away_score']):
        score = f"{int(row['home_score'])}-{int(row['away_score'])}"
    else:
        score = 'vs'
    return f"{row['home_team']} {score} {row['away_team']} ({str(row['match_date'])[:10]})"


@st.cache_data(ttl=CATALOG_TTL, show_spinner=False)
def load_competitions():
    """
    Récupère tous les couples compétition/saison disponibles en open data.

    Returns:
        DataFrame avec une colonne 'competition_label' prête à afficher,
        ou un DataFrame vide si l'API est injoignable.
    """
    try:
        df = _sb_call(sb.competitions)
    except Exception as e:
        st.error(f"Could not load StatsBomb competitions: {e}")
        return pd.DataFrame()

    df['competition_label'] = df.apply(competition_label, axis=1)
    return df


@st.cache_data(ttl=CATALOG_TTL, show_spinner=False)
def load_matches(competition_id, season_id):
    """
    Récupère le calendrier d'une saison, du match le plus récent au plus ancien.

    Returns:
        DataFrame avec une colonne 'match_label', ou un DataFrame vide en cas d'échec.
    """
    try:
        df = _sb_call(sb.matches, competition_id=competition_id, season_id=season_id)
    except Exception as e:
        st.error(f"Could not load matches for this season: {e}")
        return pd.DataFrame()

    df = df.sort_values('match_date', ascending=False).reset_index(drop=True)
    df['match_label'] = df.apply(match_label, axis=1)
    return df


def _fetch_events(match_id):
    """
    Télécharge les évènements d'un match sans toucher à Streamlit, ce qui rend
    l'appel utilisable depuis un thread.

    Returns:
        Tuple (match_id, DataFrame), ou (match_id, None) en cas d'échec.
    """
    try:
        return match_id, _sb_call(sb.events, match_id=int(match_id))
    except Exception:
        return match_id, None


@st.cache_data(show_spinner=False)
def load_events(match_id):
    """ Récupère les évènements d'un match, ou un DataFrame vide en cas d'échec. """
    _, df = _fetch_events(match_id)
    if df is None:
        st.error(f"Could not load events for match {match_id}")
        return pd.DataFrame()
    return df


def load_events_parallel(match_ids):
    """
    Charge plusieurs matchs de front (le téléchargement pèse ~80% du temps de chargement).

    Les workers ne touchent à aucune API Streamlit : ils ne font que du réseau, le cache
    et les messages d'erreur restent sur le thread principal.

    Un match pèse ~12 Mo en mémoire : le cache est réduit à la sélection courante pour
    que la session ne grossisse pas au fil de la navigation. Conséquence assumée,
    re-cocher un match désélectionné le retélécharge.

    Returns:
        Liste de (match_id, DataFrame) dans l'ordre de match_ids ; les matchs en échec
        sont signalés à l'utilisateur et exclus.
    """
    if not match_ids:
        return []

    if 'events_cache' not in st.session_state:
        st.session_state['events_cache'] = {}
    cache = st.session_state['events_cache']

    missing = [match_id for match_id in match_ids if match_id not in cache]
    if missing:
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_DOWNLOADS, len(missing))) as pool:
            for match_id, df in pool.map(_fetch_events, missing):
                if df is not None:  # un échec n'est pas mis en cache, il sera réessayé
                    cache[match_id] = df

    for stale in set(cache) - set(match_ids):
        del cache[stale]

    failed = [match_id for match_id in match_ids if match_id not in cache]
    if failed:
        st.warning(f"{len(failed)} of {len(match_ids)} matches could not be loaded and were skipped.")

    return [(match_id, cache[match_id]) for match_id in match_ids if match_id in cache]


def ensure_columns(df, cols):
    """
    Ajoute les colonnes absentes en NaN.

    StatsBomb ne renvoie une colonne que si l'évènement correspondant existe :
    un match sans dribble arrive sans 'dribble_outcome', que les visualisations attendent.
    """
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    return df

# ==================== MULTI-MATCH AGGREGATION ====================

def aggregate_matches(dataframes, match_names=None):
    """
    Aggregate multiple match dataframes into one with match_id tracking.

    Args:
        dataframes: List of DataFrames from different matches
        match_names: Optional list of match names for identification

    Returns:
        Combined DataFrame with match_id column
    """
    combined_dfs = []

    for i, df in enumerate(dataframes):
        df_copy = df.copy()
        df_copy['match_id'] = i
        df_copy['match_name'] = match_names[i] if match_names and i < len(match_names) else f"Match {i+1}"
        combined_dfs.append(df_copy)

    return pd.concat(combined_dfs, ignore_index=True)


def player_season_summary(df, player, team, num_matches=None):
    """
    Create a radar chart showing aggregated player stats across multiple matches.
    Stats are normalized per 90 minutes for fair comparison.
    """
    player_events = df[(df['player'] == player) & (df['team'] == team)]

    if player_events.empty:
        st.warning(f"No data available for {player}")
        fig, ax = plt.subplots(figsize=(10, 10))
        return fig, ax

    # Calculate total minutes (approximate from match data)
    if num_matches is None:
        num_matches = df['match_id'].nunique() if 'match_id' in df.columns else 1

    # Approximate minutes played (90 per match as default)
    total_minutes = num_matches * 90

    # Calculate raw stats
    # Passes
    passes = player_events[player_events['type'] == 'Pass']
    total_passes = len(passes)
    completed_passes = len(passes[passes['pass_outcome'].isnull()])
    pass_accuracy = round((completed_passes / total_passes * 100), 1) if total_passes > 0 else 0

    # Forward passes
    passes_with_loc = passes.dropna(subset=['location', 'pass_end_location'])
    if not passes_with_loc.empty:
        locations = passes_with_loc['location'].tolist()
        end_locations = passes_with_loc['pass_end_location'].tolist()
        forward_passes = sum(1 for i, loc in enumerate(locations) if end_locations[i][0] > loc[0])
    else:
        forward_passes = 0

    # Shots & Goals
    shots = player_events[player_events['type'] == 'Shot']
    total_shots = len(shots)
    goals = len(shots[shots['shot_outcome'] == 'Goal'])
    xg = shots['shot_statsbomb_xg'].sum() if not shots.empty else 0

    # Dribbles
    dribbles = player_events[player_events['type'] == 'Dribble']
    total_dribbles = len(dribbles)
    successful_dribbles = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])

    # Carries
    carries = player_events[player_events['type'] == 'Carry'].dropna(subset=['location', 'carry_end_location'])
    total_carries = len(carries)
    if not carries.empty:
        locations = carries['location'].tolist()
        end_locations = carries['carry_end_location'].tolist()
        progressive_carries = sum(1 for i, loc in enumerate(locations) if end_locations[i][0] > loc[0])
    else:
        progressive_carries = 0

    # Defensive actions
    ball_recoveries = len(player_events[player_events['type'] == 'Ball Recovery'])
    defensive_actions = len(player_events[player_events['type'].isin(['Tackle', 'Interception', 'Clearance'])])

    # Calculate per 90 stats
    per_90_multiplier = 90 / total_minutes if total_minutes > 0 else 1

    stats_per_90 = {
        'Passes': round(completed_passes * per_90_multiplier, 1),
        'Forward Passes': round(forward_passes * per_90_multiplier, 1),
        'Shots': round(total_shots * per_90_multiplier, 2),
        'Goals': round(goals * per_90_multiplier, 2),
        'xG': round(xg * per_90_multiplier, 2),
        'Dribbles Won': round(successful_dribbles * per_90_multiplier, 1),
        'Carries': round(total_carries * per_90_multiplier, 1),
        'Prog. Carries': round(progressive_carries * per_90_multiplier, 1),
        'Ball Recoveries': round(ball_recoveries * per_90_multiplier, 1),
        'Def. Actions': round(defensive_actions * per_90_multiplier, 1),
    }

    # Raw totals for display
    raw_stats = {
        'Matches': num_matches,
        'Minutes (approx)': total_minutes,
        'Total Passes': completed_passes,
        'Pass Accuracy': f"{pass_accuracy}%",
        'Total Goals': goals,
        'Total xG': round(xg, 2),
        'xG Difference': f"{'+' if goals - xg > 0 else ''}{round(goals - xg, 2)}",
    }

    # Create radar chart
    radar_metrics = list(stats_per_90.keys())
    values = list(stats_per_90.values())

    # Set ranges (min=0, max based on reasonable benchmarks with buffer)
    low = [0] * len(radar_metrics)
    high = [max(v * 1.5, 1) for v in values]  # 50% buffer above actual values

    radar = Radar(radar_metrics, low, high,
                  round_int=[False] * len(radar_metrics),
                  num_rings=4,
                  ring_width=1,
                  center_circle_radius=1)

    fig, axs = radar.setup_axis()
    fig.set_facecolor('#1a1a2e')

    rings_inner = radar.draw_circles(ax=axs, facecolor='#1a1a2e', edgecolor='#ffffff', alpha=0.1)
    radar_output = radar.draw_radar(values, ax=axs,
                                     kwargs_radar={'facecolor': '#E74C3C', 'alpha': 0.6},
                                     kwargs_rings={'facecolor': '#E74C3C', 'alpha': 0.1})

    radar.draw_range_labels(ax=axs, fontsize=8, color='#ffffff', alpha=0.7)
    radar.draw_param_labels(ax=axs, fontsize=10, color='#ffffff')

    # Title
    title = f'{player} - Season Summary'
    fig.text(0.5, 0.97, title, ha='center', va='top', fontsize=16,
             color='#ffffff', fontweight='bold')
    fig.text(0.5, 0.93, f'{num_matches} matches | Stats per 90 minutes',
             ha='center', va='top', fontsize=11, color='#ffffff', alpha=0.8)

    # Endnote
    fig.text(0.5, 0.02, '@alex.mrl38', ha='center', va='bottom',
             fontsize=9, color='#ffffff', alpha=0.5)
    add_statsbomb_credit(fig, color='#ffffff', alpha=0.5)

    # Display metrics in Streamlit
    st.markdown("##### Season Totals")
    cols = st.columns(4)
    for i, (key, value) in enumerate(raw_stats.items()):
        cols[i % 4].metric(key, value)

    st.markdown("##### Per 90 Minutes")
    cols2 = st.columns(5)
    for i, (key, value) in enumerate(stats_per_90.items()):
        cols2[i % 5].metric(key, value)

    return fig, axs


def performance_trend(df, player, team, stat_type='xG'):
    """
    Create a line chart showing player performance trend across matches.

    Args:
        df: DataFrame with match_id column
        player: Player name
        team: Team name
        stat_type: 'xG', 'Goals', 'Passes', 'Dribbles'
    """
    if 'match_id' not in df.columns:
        st.warning("Match tracking not available. Upload multiple matches for trend analysis.")
        fig, ax = plt.subplots(figsize=(12, 6))
        return fig, ax

    player_events = df[(df['player'] == player) & (df['team'] == team)]

    if player_events.empty:
        st.warning(f"No data available for {player}")
        fig, ax = plt.subplots(figsize=(12, 6))
        return fig, ax

    # Group by match
    match_stats = []
    for match_id in sorted(df['match_id'].unique()):
        match_events = player_events[player_events['match_id'] == match_id]
        match_name = df[df['match_id'] == match_id]['match_name'].iloc[0] if 'match_name' in df.columns else f"M{match_id+1}"

        if stat_type == 'xG':
            shots = match_events[match_events['type'] == 'Shot']
            value = shots['shot_statsbomb_xg'].sum() if not shots.empty else 0
        elif stat_type == 'Goals':
            shots = match_events[match_events['type'] == 'Shot']
            value = len(shots[shots['shot_outcome'] == 'Goal'])
        elif stat_type == 'Passes':
            passes = match_events[match_events['type'] == 'Pass']
            value = len(passes[passes['pass_outcome'].isnull()])
        elif stat_type == 'Dribbles':
            dribbles = match_events[match_events['type'] == 'Dribble']
            value = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])
        else:
            value = 0

        match_stats.append({
            'match_id': match_id,
            'match_name': match_name,
            'value': value
        })

    stats_df = pd.DataFrame(match_stats)

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    # Plot line
    ax.plot(range(len(stats_df)), stats_df['value'], color='#E74C3C', linewidth=2.5, marker='o', markersize=8)

    # Add average line
    avg = stats_df['value'].mean()
    ax.axhline(y=avg, color='#3498DB', linestyle='--', alpha=0.7, label=f'Average: {avg:.2f}')

    # Fill area under curve
    ax.fill_between(range(len(stats_df)), stats_df['value'], alpha=0.3, color='#E74C3C')

    # Styling
    ax.set_xlabel('Match', color='#ffffff', fontsize=12)
    ax.set_ylabel(stat_type, color='#ffffff', fontsize=12)
    ax.set_xticks(range(len(stats_df)))
    ax.set_xticklabels([f"M{i+1}" for i in range(len(stats_df))], color='#ffffff', fontsize=9)
    ax.tick_params(colors='#ffffff')
    ax.spines['bottom'].set_color('#ffffff')
    ax.spines['left'].set_color('#ffffff')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.2, color='#ffffff')
    ax.legend(loc='upper right', facecolor='#1a1a2e', edgecolor='#ffffff', labelcolor='#ffffff')

    # Title
    ax.set_title(f'{player} - {stat_type} Trend', color='#ffffff', fontsize=16, fontweight='bold', pad=15)

    # Endnote
    fig.text(0.95, 0.02, '@alex.mrl38', ha='right', va='bottom', fontsize=9, color='#ffffff', alpha=0.5)

    plt.tight_layout()

    # Après tight_layout, qui ne doit pas prendre l'axe du logo dans son calcul
    add_statsbomb_credit(fig, x=0.04, width=0.11, color='#ffffff', alpha=0.5)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", round(stats_df['value'].sum(), 2))
    col2.metric("Average", round(avg, 2))
    col3.metric("Best", round(stats_df['value'].max(), 2))
    col4.metric("Matches", len(stats_df))

    return fig, ax


# ==================== PDF EXPORT ====================

def generate_pdf_report(fig, df, match, analysis_type, player=None, team=None,
                        player2=None, team2=None, time_range=None):
    """Generate a PDF report with the current visualization and match statistics."""

    if not PDF_AVAILABLE:
        st.error("PDF export requires fpdf2. Install it with: pip install fpdf2")
        return None

    # Save figure to temporary buffer
    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    img_buffer.seek(0)

    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 15, 'Football Performance Report', ln=True, align='C')

    # Match info
    pdf.set_font('Helvetica', '', 12)
    pdf.set_text_color(100, 100, 100)
    if match and match != "Uploaded Data":
        pdf.cell(0, 8, f'Match: {match}', ln=True, align='C')

    # Date
    pdf.cell(0, 8, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', ln=True, align='C')

    # Analysis type and player/team info
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 10, f'Analysis: {analysis_type}', ln=True, align='C')

    if player and team and analysis_type != "Player Radar":
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 8, f'Player: {player} ({team})', ln=True, align='C')
    elif analysis_type == "Player Radar" and player and player2:
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 8, f'{player} ({team}) vs {player2} ({team2})', ln=True, align='C')
    elif team and analysis_type in ["Pass Network", "Defensive Shape"]:
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 8, f'Team: {team}', ln=True, align='C')

    # Time range
    if time_range and time_range != (0, 90):
        pdf.set_font('Helvetica', 'I', 10)
        pdf.cell(0, 6, f"Period: {time_range[0]}' - {time_range[1]}'", ln=True, align='C')

    pdf.ln(5)

    # Add visualization image
    # Save to temp file for fpdf
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
        tmp.write(img_buffer.getvalue())
        tmp_path = tmp.name

    # Calculate image dimensions to fit page
    page_width = pdf.w - 40  # margins
    pdf.image(tmp_path, x=20, w=page_width)

    # Clean up temp file
    os.unlink(tmp_path)

    pdf.ln(10)

    # Add statistics summary based on analysis type
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, 'Key Statistics', ln=True)
    pdf.set_font('Helvetica', '', 10)

    if analysis_type in ['Passes', 'Shots', 'Carries', 'Dribbles', 'Defensive Actions'] and player:
        stats = _get_player_stats_for_pdf(df, player, team, analysis_type)
        for key, value in stats.items():
            pdf.cell(0, 6, f'{key}: {value}', ln=True)

    elif analysis_type == "Defensive Shape" and team:
        stats = _get_defensive_stats_for_pdf(df, team)
        for key, value in stats.items():
            pdf.cell(0, 6, f'{key}: {value}', ln=True)

    elif analysis_type == "Match Summary":
        teams = df['team'].unique()
        if len(teams) >= 2:
            stats = _get_match_stats_for_pdf(df, teams[0], teams[1])
            pdf.cell(0, 6, f'{teams[0]} vs {teams[1]}', ln=True)
            for key, value in stats.items():
                pdf.cell(0, 6, f'{key}: {value}', ln=True)

    elif analysis_type == "xG Timeline":
        teams = df['team'].unique()
        if len(teams) >= 2:
            stats = _get_xg_stats_for_pdf(df, teams[0], teams[1])
            for key, value in stats.items():
                pdf.cell(0, 6, f'{key}: {value}', ln=True)

    elif analysis_type == "Player Radar" and player and player2:
        stats = _get_comparison_stats_for_pdf(df, player, team, player2, team2)
        for key, value in stats.items():
            pdf.cell(0, 6, f'{key}: {value}', ln=True)

    # Footer
    pdf.ln(10)

    # Logo StatsBomb exigé par la clause 1.4 de la licence, centré au-dessus du crédit texte
    if STATSBOMB_LOGO_PATH.exists():
        logo_width = 35
        pdf.image(str(STATSBOMB_LOGO_PATH), x=(pdf.w - logo_width) / 2, w=logo_width)
        pdf.ln(2)

    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, 'Data source: StatsBomb Open Data', ln=True, align='C')
    pdf.cell(0, 5, 'Generated by Football Analytics - @alex.mrl38', ln=True, align='C')

    # Output PDF to bytes
    pdf_output = BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)

    return pdf_output

def _get_player_stats_for_pdf(df, player, team, analysis_type):
    """Get player statistics for PDF export."""
    player_events = df[(df['player'] == player) & (df['team'] == team)]
    stats = {}

    if analysis_type == 'Passes':
        passes = player_events[player_events['type'] == 'Pass']
        total = len(passes)
        completed = len(passes[passes['pass_outcome'].isnull()])
        stats['Total Passes'] = total
        stats['Completed'] = f"{completed} ({round(completed/total*100) if total > 0 else 0}%)"

    elif analysis_type == 'Shots':
        shots = player_events[player_events['type'] == 'Shot']
        goals = len(shots[shots['shot_outcome'] == 'Goal'])
        xg = round(shots['shot_statsbomb_xg'].sum(), 2) if not shots.empty else 0
        stats['Shots'] = len(shots)
        stats['Goals'] = goals
        stats['xG'] = xg

    elif analysis_type == 'Carries':
        carries = player_events[player_events['type'] == 'Carry']
        stats['Total Carries'] = len(carries)

    elif analysis_type == 'Dribbles':
        dribbles = player_events[player_events['type'] == 'Dribble']
        successful = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])
        total = len(dribbles)
        stats['Total Dribbles'] = total
        stats['Successful'] = f"{successful} ({round(successful/total*100) if total > 0 else 0}%)"

    elif analysis_type == 'Defensive Actions':
        actions = player_events[player_events['type'].isin(DEFENSIVE_ACTIONS)].dropna(subset=['location'])
        duels = actions[actions['type'] == 'Duel']
        duels_won = int(duels['duel_outcome'].isin(DUEL_WON_OUTCOMES).sum())
        x = _action_x(actions)
        stats['Defensive Actions'] = len(actions)
        stats['Duels Won'] = f"{duels_won}/{len(duels)} ({round(duels_won/len(duels)*100) if len(duels) > 0 else 0}%)"
        if not actions.empty:
            stats['Avg Height'] = f"{round(x.mean() / PITCH_LENGTH * 100)}%"
            stats['In Final Third'] = int((x >= FINAL_THIRD_START).sum())

    return stats


def _get_defensive_stats_for_pdf(df, team):
    """Get team defensive statistics for PDF export."""
    actions = df[(df['team'] == team) & (df['type'].isin(DEFENSIVE_ACTIONS))].dropna(subset=['location'])
    stats = {'Defensive Actions': len(actions)}

    if actions.empty:
        return stats

    x = _action_x(actions)
    ppda = compute_ppda(df, team)
    stats['PPDA'] = round(ppda, 1) if ppda is not None else 'N/A'
    stats['Avg Height'] = f"{round(x.mean() / PITCH_LENGTH * 100)}%"
    stats['In Opponent Half'] = f"{round((x >= PITCH_LENGTH / 2).sum() / len(x) * 100)}%"

    for action_type in DEFENSIVE_ACTIONS:
        count = int((actions['type'] == action_type).sum())
        if count:
            stats[action_type] = count

    return stats

def _get_match_stats_for_pdf(df, team1, team2):
    """Get match statistics for PDF export."""
    stats = {}

    for team in [team1, team2]:
        team_events = df[df['team'] == team]
        shots = team_events[team_events['type'] == 'Shot']
        goals = len(shots[shots['shot_outcome'] == 'Goal'])
        xg = round(shots['shot_statsbomb_xg'].sum(), 2)
        passes = team_events[team_events['type'] == 'Pass']
        completed = len(passes[passes['pass_outcome'].isnull()])

        stats[f'{team} Goals'] = goals
        stats[f'{team} xG'] = xg
        stats[f'{team} Passes'] = completed

    return stats

def _get_xg_stats_for_pdf(df, team1, team2):
    """Get xG timeline statistics for PDF export."""
    stats = {}
    shots = df[df['type'] == 'Shot']

    for team in [team1, team2]:
        team_shots = shots[shots['team'] == team]
        xg = round(team_shots['shot_statsbomb_xg'].sum(), 2)
        goals = len(team_shots[team_shots['shot_outcome'] == 'Goal'])
        stats[f'{team} xG'] = xg
        stats[f'{team} Goals'] = goals

    return stats

def _get_comparison_stats_for_pdf(df, player1, team1, player2, team2):
    """Get player comparison statistics for PDF export."""
    stats = {}

    for player, team in [(player1, team1), (player2, team2)]:
        player_events = df[(df['player'] == player) & (df['team'] == team)]

        passes = player_events[player_events['type'] == 'Pass']
        completed_passes = len(passes[passes['pass_outcome'].isnull()])

        shots = player_events[player_events['type'] == 'Shot']
        goals = len(shots[shots['shot_outcome'] == 'Goal'])

        dribbles = player_events[player_events['type'] == 'Dribble']
        successful_dribbles = len(dribbles[dribbles['dribble_outcome'] == 'Complete'])

        name = player.split()[-1]
        stats[f'{name} - Passes'] = completed_passes
        stats[f'{name} - Goals'] = goals
        stats[f'{name} - Dribbles Won'] = successful_dribbles

    return stats