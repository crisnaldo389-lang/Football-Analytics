# -*- coding: utf-8 -*-
"""
Created on Sun Jun  5 11:39:54 2022

@author: alexa
"""

import time
import streamlit as st
from statsbombpy import sb
from io import BytesIO
from helpers import (passes_map, heatmap, shots_map, carries_map, dribbles_map,
                     pass_network, xg_timeline, match_summary, player_comparison_radar,
                     check_required_columns, try_read_json, generate_pdf_report, PDF_AVAILABLE)

# Set page config
st.set_page_config(page_title='Football Data Analysis', page_icon=':soccer:', initial_sidebar_state='expanded')

# Drop-down menu 1
st.sidebar.markdown('## Match Selection')

# Colonnes nécessaires définies pour les différentes analyses
required_columns = ['team', 'player', 'location',
                    'pass_end_location', 'type', 'pass_outcome',
                    'shot_outcome', 'shot_end_location', 'shot_statsbomb_xg',
                    'carry_end_location', 'dribble_outcome', 'pass_recipient']

# Define statistics by level
PLAYER_STATS = ['Passes', 'Shots', 'Heatmap', 'Carries', 'Dribbles']
TEAM_STATS = ['Match Summary', 'Pass Network', 'xG Timeline']
COMPARISON_STATS = ['Player Radar']

# File upload
uploaded_file = st.sidebar.file_uploader("Upload your own data", type='json')
if uploaded_file is not None:
    df_uploaded = try_read_json(uploaded_file)

    if df_uploaded is not None:
        # Vérification des colonnes
        is_valid, missing_info = check_required_columns(df_uploaded, required_columns)

        if not is_valid:
            st.error(f"Data Error: {missing_info}")
            st.stop()  # Stop further execution if columns are missing
        else:
            # Extraction des équipes et joueurs
            teams_uploaded = df_uploaded['team'].dropna().unique()
            players_uploaded = df_uploaded[df_uploaded['team'] == teams_uploaded[0]]['player'].dropna().unique()

            # Choose analysis level
            analysis_level = st.sidebar.radio('Analysis Level', ['Player', 'Team', 'Comparison'], horizontal=True)

            # Team selection
            menu_team = st.sidebar.selectbox('Select a Team', teams_uploaded)

            # Player selection (only for Player level)
            if analysis_level == 'Player':
                menu_player = st.sidebar.selectbox('Select a Player', df_uploaded[df_uploaded['team'] == menu_team]['player'].dropna().unique())
                menu_activity = st.sidebar.selectbox('Select a Statistic', PLAYER_STATS)
                menu_player2 = None
                menu_team2 = None
            elif analysis_level == 'Team':
                menu_player = None
                menu_player2 = None
                menu_team2 = None
                menu_activity = st.sidebar.selectbox('Select a Statistic', TEAM_STATS)
            else:  # Comparison
                menu_activity = st.sidebar.selectbox('Select a Statistic', COMPARISON_STATS)
                st.sidebar.markdown("#### Player 1")
                menu_team = st.sidebar.selectbox('Team', teams_uploaded, key='team1_uploaded')
                menu_player = st.sidebar.selectbox('Player', df_uploaded[df_uploaded['team'] == menu_team]['player'].dropna().unique(), key='player1_uploaded')
                st.sidebar.markdown("#### Player 2")
                menu_team2 = st.sidebar.selectbox('Team', teams_uploaded, key='team2_uploaded')
                menu_player2 = st.sidebar.selectbox('Player', df_uploaded[df_uploaded['team'] == menu_team2]['player'].dropna().unique(), key='player2_uploaded')

            df_events = df_uploaded
            menu_game = "Uploaded Data" 

else: 
    # List of games and JSON files as dictionary
    games_dict = {
        'Barcelona - Huesca 4:1 (Round 27)': '3773369',
        'Barcelona - Real Madrid 1:3 (Round 7)': '3773585'
    }

    games_list = list(games_dict.keys())
    games_id_list = list(games_dict.values())

    menu_game = st.sidebar.selectbox('Or use our samples data', games_list, index=0)

    # Get Statsbomb events data based on selected game
    df_events = sb.events(match_id=games_dict.get(menu_game))
    df_events.to_json("df_test.json")

    # Get teams and players names
    team_1 = df_events['team'].unique()[0]
    team_2 = df_events['team'].unique()[1]
    mask_1 = df_events.loc[df_events['team'] == team_1]
    mask_2 = df_events.loc[df_events['team'] == team_2]
    player_names_1 = mask_1['player'].dropna().unique()
    player_names_2 = mask_2['player'].dropna().unique()

    # Drop-down menu 2
    st.sidebar.markdown('## Analysis Selection')

    # Choose analysis level
    analysis_level = st.sidebar.radio('Analysis Level', ['Player', 'Team', 'Comparison'], horizontal=True)

    # Player selection (only for Player level)
    if analysis_level == 'Player':
        menu_team = st.sidebar.selectbox('Select a Team', (team_1, team_2))
        if menu_team == team_1:
            menu_player = st.sidebar.selectbox('Select a Player', player_names_1)
        else:
            menu_player = st.sidebar.selectbox('Select a Player', player_names_2)
        menu_activity = st.sidebar.selectbox('Select a Statistic', PLAYER_STATS)
        menu_player2 = None
        menu_team2 = None
    elif analysis_level == 'Team':
        menu_team = st.sidebar.selectbox('Select a Team', (team_1, team_2))
        menu_player = None
        menu_player2 = None
        menu_team2 = None
        menu_activity = st.sidebar.selectbox('Select a Statistic', TEAM_STATS)
    else:  # Comparison
        menu_activity = st.sidebar.selectbox('Select a Statistic', COMPARISON_STATS)
        st.sidebar.markdown("#### Player 1")
        menu_team = st.sidebar.selectbox('Team', (team_1, team_2), key='team1')
        if menu_team == team_1:
            menu_player = st.sidebar.selectbox('Player', player_names_1, key='player1')
        else:
            menu_player = st.sidebar.selectbox('Player', player_names_2, key='player1')
        st.sidebar.markdown("#### Player 2")
        menu_team2 = st.sidebar.selectbox('Team', (team_1, team_2), key='team2')
        if menu_team2 == team_1:
            menu_player2 = st.sidebar.selectbox('Player', player_names_1, key='player2')
        else:
            menu_player2 = st.sidebar.selectbox('Player', player_names_2, key='player2')

# Time filter section
st.sidebar.markdown('## Time Filter')
max_minute = int(df_events['minute'].max()) if 'minute' in df_events.columns else 90

time_filter = st.sidebar.radio('Period', ['Full Match', '1st Half', '2nd Half', 'Custom'], horizontal=True)

if time_filter == '1st Half':
    time_range = (0, 45)
elif time_filter == '2nd Half':
    time_range = (45, max_minute)
elif time_filter == 'Custom':
    time_range = st.sidebar.slider('Select time range (minutes)', 0, max_minute, (0, max_minute))
else:  # Full Match
    time_range = (0, max_minute)

# Filter dataframe by time
df_events = df_events[(df_events['minute'] >= time_range[0]) & (df_events['minute'] <= time_range[1])]

# Display selected time range
if time_filter != 'Full Match':
    st.sidebar.caption(f"Showing: {time_range[0]}' - {time_range[1]}'")

st.sidebar.divider()

# Help section in sidebar
with st.sidebar.expander("Need help?"):
    st.markdown("""
    **Tips:**
    - Hover over metrics for explanations
    - Expand "How to read this chart?" below visualizations
    - Use time filters to analyze specific periods

    **Data source:**
    [StatsBomb Open Data](https://github.com/statsbomb/open-data)

    **Found a bug?**
    [Report on GitHub](https://github.com/AlexandreMorel/Football-Analytics/issues)
    """)

st.sidebar.markdown('### Made with :heart: by [Alexandre Morel](https://fr.linkedin.com/in/alexandre-morel-38590am)')
st.sidebar.markdown('#### [View source](https://github.com/AlexandreMorel/Football-Analytics):computer:')

# Titles and text above the pitch
st.header('Welcome to my Performance Analysis tool!:dart:', divider='red')

# Collapsible guide section
with st.expander("Quick Start Guide", expanded=False):
    st.markdown("""
    ### How to use this tool

    **1. Select your data** (sidebar)
    - Upload your own StatsBomb JSON file, or
    - Use one of the sample matches (Barcelona games)

    **2. Choose analysis level**
    - **Player**: Individual player statistics and visualizations
    - **Team**: Team-wide analysis (Pass Network, xG Timeline, Match Summary)
    - **Comparison**: Compare two players head-to-head with radar charts

    **3. Select visualization**

    | Level | Visualization | What it shows |
    |-------|--------------|---------------|
    | Player | Passes | Pass map with completion, direction, assists |
    | Player | Shots | Shot locations with outcomes and xG |
    | Player | Heatmap | Activity zones on the pitch |
    | Player | Carries | Ball progression with feet |
    | Player | Dribbles | 1v1 success/failure locations |
    | Team | Match Summary | Complete stats comparison dashboard |
    | Team | Pass Network | Passing connections between players |
    | Team | xG Timeline | Shot quality over time |
    | Compare | Player Radar | Head-to-head statistical comparison |

    **4. Filter by time** (optional)
    - Analyze full match, first/second half, or custom time ranges

    **5. Export**
    - Download any visualization as PNG

    ---
    *Tip: Click "How to read this chart?" below each visualization for detailed explanations!*
    """)

st.write("""* Events data labelled by [StatsBomb](https://github.com/statsbomb/statsbombpy) - [Specification](https://github.com/statsbomb/statsbombpy/blob/master/doc/Open%20Data%20Events%20v4.0.0.pdf)""")
st.divider()

# Display title based on statistic type
if menu_activity in ["Pass Network", "xG Timeline", "Heatmap", "Player Radar", "Match Summary"]:
    st.write('###', menu_activity)
else:
    st.write('###', menu_activity, 'Map')

if menu_game != "Uploaded Data":
    st.write('###### Match:', menu_game)

# Display time filter info
if time_filter != 'Full Match':
    st.write(f"###### Period: {time_range[0]}' - {time_range[1]}'")

# Display player or team info based on analysis level
if menu_activity == "Player Radar":
    st.write(f'###### {menu_player} ({menu_team}) vs {menu_player2} ({menu_team2})')
elif menu_player is not None:
    st.write('###### Player:', menu_player, '(', menu_team ,')')
elif menu_activity not in ["xG Timeline", "Match Summary"]:
    st.write('###### Team:', menu_team) 

# Get plot function based on selected activity
if menu_activity == 'Passes':
    if menu_game != "Uploaded Data": 
        fig, ax = passes_map(player=menu_player, df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = passes_map(player=menu_player, df=df_events, team=menu_team)
elif menu_activity == "Heatmap":
    if menu_game != "Uploaded Data": 
        fig, ax = heatmap(player=menu_player, df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = heatmap(player=menu_player, df=df_events, team=menu_team)
elif menu_activity == "Shots":
    if menu_game != "Uploaded Data":
        fig, ax = shots_map(player=menu_player, df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = shots_map(player=menu_player, df=df_events, team=menu_team)
elif menu_activity == "Carries":
    if menu_game != "Uploaded Data":
        fig, ax = carries_map(player=menu_player, df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = carries_map(player=menu_player, df=df_events, team=menu_team)
elif menu_activity == "Dribbles":
    if menu_game != "Uploaded Data":
        fig, ax = dribbles_map(player=menu_player, df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = dribbles_map(player=menu_player, df=df_events, team=menu_team)
# Team statistics
elif menu_activity == "Match Summary":
    if menu_game != "Uploaded Data":
        fig, ax = match_summary(df=df_events, match=menu_game)
    else:
        fig, ax = match_summary(df=df_events)
elif menu_activity == "Pass Network":
    if menu_game != "Uploaded Data":
        fig, ax = pass_network(df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = pass_network(df=df_events, team=menu_team)
elif menu_activity == "xG Timeline":
    if menu_game != "Uploaded Data":
        fig, ax = xg_timeline(df=df_events, team=menu_team, match=menu_game)
    else:
        fig, ax = xg_timeline(df=df_events, team=menu_team)
# Comparison statistics
elif menu_activity == "Player Radar":
    if menu_game != "Uploaded Data":
        fig, ax = player_comparison_radar(df=df_events, player1=menu_player, player2=menu_player2,
                                          team1=menu_team, team2=menu_team2, match=menu_game)
    else:
        fig, ax = player_comparison_radar(df=df_events, player1=menu_player, player2=menu_player2,
                                          team1=menu_team, team2=menu_team2)

st.pyplot(fig)

# Add contextual explanations for each visualization type
if menu_activity == "Passes":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Green arrows** = Completed passes (successful)
        - **Yellow arrows** = Assists (passes leading directly to a goal)
        - **Red arrows** = Missed passes (intercepted, out of play, etc.)

        **Metrics explained:**
        - **Completed passes**: Total successful passes / Total attempted passes
        - **Completed forward passes**: Passes that move the ball toward the opponent's goal
        - **Forward play %**: Ratio of forward passes to total passes - indicates attacking intent

        **Key insights to look for:**
        - *High forward play %* = Player is progressive, pushing the team forward
        - *Clusters of red arrows* = Areas where the player struggles or faces pressure
        - *Yellow arrows* = Key creative moments in the match
        """)

elif menu_activity == "Shots":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Green arrows** = Goals scored
        - **Yellow arrows** = Shots on target (saved by goalkeeper)
        - **Orange arrows** = Blocked shots (by defenders)
        - **Red arrows** = Shots off target (missed the goal)

        **Metrics explained:**
        - **Goals**: Actual goals scored by the player
        - **xG (Expected Goals)**: Statistical probability of scoring based on shot position, angle, body part, etc.
        - **Delta** (green/red number): Goals - xG
            - *Positive* = Clinical finisher, scoring above expectations
            - *Negative* = Underperforming, missing chances

        **Key insights:**
        - *Shots from central areas* have higher xG than wide angles
        - *Many blocked shots* may indicate good positioning but predictable shooting
        - Compare xG to goals to assess finishing quality
        """)

elif menu_activity == "Heatmap":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Hot colors (yellow/red)** = High activity zones - player spent most time here
        - **Cold colors (dark)** = Low activity zones - player rarely present

        **How to interpret:**
        - The heatmap shows WHERE on the pitch the player was involved in actions
        - Brighter areas = more touches, passes, dribbles, etc.

        **Key insights by position:**
        - *Striker*: Should have heat in the box and attacking third
        - *Midfielder*: Heat spread across the middle, connecting defense to attack
        - *Winger*: Heat concentrated on the flanks
        - *Defender*: Heat in defensive third, potentially one side for fullbacks

        **Tactical insights:**
        - *Heat drifting inward* = Player cutting inside
        - *Heat spread wide* = Player stretching the play
        - *Heat in unusual zones* = Tactical role change or pressing triggers
        """)

elif menu_activity == "Carries":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Green arrows** = Progressive carries (moving toward opponent's goal)
        - **Blue arrows** = Non-progressive carries (sideways or backward)

        **Metrics explained:**
        - **Total Carries**: Number of times the player moved with the ball at their feet
        - **Progressive Carries**: Carries that advance the ball toward the goal
        - **Total Distance**: Sum of all carry distances in meters

        **Key insights:**
        - *High progressive %* = Player is a ball-progressor, driving the team forward
        - *Long carries* = Player comfortable running with the ball
        - *Carries from deep* = Ball-playing defender or deep-lying playmaker
        - *Carries into the box* = Dangerous, goal-threatening runs

        **Compare with dribbles:** Carries are moving with the ball, dribbles are beating opponents
        """)

elif menu_activity == "Dribbles":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Green circles** = Successful dribbles (beat the defender)
        - **Red circles** = Failed dribbles (lost possession)

        **Metrics explained:**
        - **Total Dribbles**: Number of 1v1 attempts against defenders
        - **Successful**: Dribbles where the player kept possession
        - **Success rate %**: Successful / Total - indicates skill level

        **Key insights:**
        - *High success rate (>60%)* = Skillful dribbler, hard to dispossess
        - *Dribbles in final third* = Creating chances, beating defenders in dangerous areas
        - *Dribbles in own half* = Risky but can relieve pressure
        - *Clusters of failed dribbles* = Area where player struggles or faces tough opponents

        **Tactical note:** Some coaches prefer safe play (fewer dribbles), others encourage risk-taking
        """)

elif menu_activity == "Match Summary":
    with st.expander("How to read this dashboard?", expanded=False):
        st.markdown("""
        **Overview:**
        This dashboard provides a complete statistical comparison between both teams.

        **Key metrics explained:**
        - **xG**: Expected Goals - quality of chances created (higher = better chances)
        - **Possession**: Approximation based on touches, passes, and carries
        - **Pass Accuracy**: Percentage of successful passes
        - **Shots on Target**: Shots that would have gone in without a save

        **How to read the bars:**
        - Bars show the relative comparison between teams
        - Longer bar = team dominated that metric

        **Insights to look for:**
        - *Higher xG but fewer goals* = Unlucky or poor finishing
        - *High possession, low shots* = Sterile possession, lacking final ball
        - *Low possession, high xG* = Efficient counter-attacking
        - *Many fouls* = Physical approach or frustration
        """)

elif menu_activity == "Pass Network":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Blue circles** = Players (size based on number of passes)
        - **Red lines** = Pass connections (thickness based on frequency)
        - **Player position** = Average position during the match

        **Metrics explained:**
        - **Total Passes**: Completed passes within the team
        - **Unique Connections**: Number of different player-to-player passing combinations
        - **Avg Passes/Connection**: How often each connection was used

        **Key insights:**
        - *Thick lines* = Strong partnerships, frequent passing combinations
        - *Central player with many connections* = Playmaker, ball distributor
        - *Isolated player* = May be out of the game or playing a specific role
        - *Forward positions* = Team was pushing high and attacking
        - *Deep positions* = Team was defending or building from the back

        **Tactical patterns:**
        - *Triangle patterns* = Good passing structure
        - *One dominant connection* = Over-reliance on specific partnership
        """)

elif menu_activity == "xG Timeline":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Lines** show cumulative xG (Expected Goals) over time for each team
        - **● Circles** represent shots - bigger circle = higher xG (better chance)
        - **★ Stars** indicate goals scored

        **Metrics explained:**
        - **xG**: Probability that a shot will result in a goal (0.5 xG = 50% chance)
        - **Goals delta** (green/red): Actual goals minus xG
            - *Positive* = Scored more than expected (clinical/lucky)
            - *Negative* = Scored less than expected (wasteful/unlucky)

        **Reading the match story:**
        - *Steep rise* = Period of high-quality chances
        - *Flat line* = No shots during that period
        - *Star without big jump* = Goal from low-xG chance (wonder goal or scrappy finish)
        - *Big jump without star* = Big miss (should have scored)

        **Who deserved to win?**
        Compare final xG values - the team with higher xG created better chances overall
        """)

elif menu_activity == "Player Radar":
    with st.expander("How to read this chart?", expanded=False):
        st.markdown("""
        **Visual elements:**
        - **Red area** = Player 1's stats
        - **Blue area** = Player 2's stats
        - **Outer edge** = Maximum value (scales to highest performer)

        **Metrics on the radar:**
        - **Passes**: Completed passes
        - **Forward Passes**: Passes advancing toward goal
        - **Shots/Goals**: Attacking output
        - **Dribbles Won**: Successful 1v1s
        - **Carries**: Ball progression with feet
        - **Progressive Carries**: Advancing carries
        - **Ball Recoveries**: Winning the ball back
        - **Defensive Actions**: Tackles + Interceptions + Clearances

        **How to compare:**
        - *Larger area* = More overall contribution
        - *Spikes* = Player's strengths
        - *Dips* = Areas where opponent is better

        **The detailed table below shows:**
        - Exact values for each metric
        - **Green** highlights the winner of each category
        - Additional metrics: Pass Accuracy %, Dribble Success %, xG
        """)

# Time filter tip
if time_filter != 'Full Match':
    with st.expander("About Time Filtering", expanded=False):
        st.markdown(f"""
        **Currently showing: {time_range[0]}' - {time_range[1]}'**

        Time filtering allows you to analyze specific periods:
        - **1st Half**: See how the team/player performed before halftime
        - **2nd Half**: Analyze second-half performance (fatigue, tactical changes)
        - **Custom**: Focus on specific moments (e.g., after a red card, after a substitution)

        **Ideas for analysis:**
        - Compare 1st vs 2nd half performance
        - Analyze the last 15 minutes (closing out games)
        - Look at the first 15 minutes (starting intensity)
        - Focus on periods after tactical changes
        """)

# Export section
st.markdown("---")
st.markdown("##### Export Options")

col_export1, col_export2 = st.columns(2)

# Sauvegarder le graphique au format PNG
buffer = BytesIO()
fig.savefig(buffer, format="png")
buffer.seek(0)

# Afficher une boîte de dialogue pour télécharger le fichier PNG
with col_export1:
    st.download_button(
        label="Export as PNG",
        data=buffer,
        file_name="soccer_plot.png",
        mime="image/png",
    )

# PDF Export button
with col_export2:
    if PDF_AVAILABLE:
        pdf_buffer = generate_pdf_report(
            fig=fig,
            df=df_events,
            match=menu_game,
            analysis_type=menu_activity,
            player=menu_player,
            team=menu_team,
            player2=menu_player2 if 'menu_player2' in dir() else None,
            team2=menu_team2 if 'menu_team2' in dir() else None,
            time_range=time_range
        )
        if pdf_buffer:
            st.download_button(
                label="Export as PDF",
                data=pdf_buffer,
                file_name="football_report.pdf",
                mime="application/pdf",
            )
    else:
        st.button("Export as PDF", disabled=True, help="Install fpdf2: pip install fpdf2")