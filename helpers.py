import streamlit as st
from mplsoccer import Pitch, Radar
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy.ndimage import gaussian_filter
from io import BytesIO
from datetime import datetime

# PDF generation imports
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

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
    TITLE_TEXT = f'Dribbles of {player} ({team})'
    axs['title'].text(0.5, 0.7, TITLE_TEXT, color='#000000',
                    va='center', ha='center', fontsize=25)
    axs['title'].text(0.5, 0.25, match, color='#000000',
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
    elif team and analysis_type in ["Pass Network"]:
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

    if analysis_type in ['Passes', 'Shots', 'Carries', 'Dribbles'] and player:
        stats = _get_player_stats_for_pdf(df, player, team, analysis_type)
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