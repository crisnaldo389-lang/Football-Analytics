# Football Analytics

Interactive data visualization application for football match analysis. Built with Streamlit and powered by StatsBomb open data.

## Features

### Data Selection
- **StatsBomb catalog browser**: pick any competition → season → match from the full open data catalog (80 competition/season combinations, no download required)
- **JSON upload**: use your own StatsBomb-format event files

### Single Match Analysis
- **Player Statistics**: Passes, Shots, Heatmap, Carries, Dribbles, Defensive Actions
- **Team Statistics**: Match Summary, Pass Network, xG Timeline, Defensive Shape
- **Comparison**: Player Radar (compare two players side-by-side)

### Multi-Match Analysis
- **Season Summary**: Aggregated player stats normalized per 90 minutes
- **Performance Trend**: Track player metrics evolution across matches

### Export Options
- PNG image export
- PDF report generation with statistics

## Quick Start

### Prerequisites
- Python 3.10+ (tested with Python 3.13)
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/Football-Analytics.git
   cd Football-Analytics
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   streamlit run main.py
   ```

5. **Open your browser** at `http://localhost:8501`

## Usage

### Browsing StatsBomb Open Data
With `Data Source` set to **StatsBomb Open Data** (default), the sidebar offers three cascading selectors:

1. **Competition** — e.g. `Spain - La Liga`, `International - FIFA World Cup`, `England - FA Women's Super League (women)`
2. **Season** — most recent first
3. **Match** — displayed as `Home 4-1 Away (date)`, most recent first

Data is fetched from the StatsBomb public API and cached: competition and match lists for 24 hours, match events for the whole session. Switching back to an already-viewed match is instant.

### Using Your Own Data
Set `Data Source` to **Upload JSON** and upload a file with StatsBomb event data format. Required columns:
- `player`, `team`, `location`, `minute`
- `pass_end_location`, `type`, `pass_outcome`, `pass_recipient`
- `shot_outcome`, `shot_end_location`, `shot_statsbomb_xg`
- `carry_end_location`, `dribble_outcome`

Optional columns, used by the defensive analyses when present: `duel_outcome`, `duel_type`. A file without them still loads — the duel counters simply read zero.

### Multi-Match Mode
1. Select "Multi-Match" in the Data Mode selector
2. Pick the matches to aggregate:
   - **StatsBomb Open Data**: choose a competition and season, optionally filter by team, then multi-select matches (the 5 most recent are pre-selected)
   - **Upload JSON**: upload 2+ JSON files, one per match
3. Select a player and view aggregated statistics

## Project Structure

```
Football-Analytics/
├── main.py              # Streamlit application entry point
├── helpers.py           # Visualization and utility functions
├── requirements.txt     # Python dependencies
├── docs/                # StatsBomb data specifications
├── exploration/         # Jupyter notebooks for data exploration
├── assets/              # Static assets (images, etc.)
└── .devcontainer/       # VS Code Dev Container configuration
```

## Visualizations

| Visualization | Description |
|--------------|-------------|
| **Passes Map** | All player passes with success/fail indicators |
| **Shots Map** | Shot locations with xG values |
| **Heatmap** | Player position frequency on the pitch |
| **Carries Map** | Ball progression with feet |
| **Dribbles Map** | 1v1 attempts with success rate |
| **Defensive Actions** | Pressures, recoveries, duels, interceptions, blocks and clearances of a player |
| **Pass Network** | Team passing connections and average positions |
| **xG Timeline** | Match progression with expected goals |
| **Defensive Shape** | Zone grid of where a team defends, with PPDA and average line height |
| **Match Summary** | Side-by-side team comparison |
| **Player Radar** | Multi-metric player comparison |
| **Season Summary** | Aggregated stats per 90 minutes |
| **Performance Trend** | Metric evolution across matches |

## Data Source

Event data provided by [StatsBomb Open Data](https://github.com/statsbomb/open-data).

Documentation available in the `docs/` folder:
- [Events v4.0.0](docs/Open%20Data%20Events%20v4.0.0.pdf)
- [Matches v3.0.0](docs/Open%20Data%20Matches%20v3.0.0.pdf)
- [Competitions v2.0.0](docs/Open%20Data%20Competitions%20v2.0.0.pdf)
- [Lineups v2.0.0](docs/Open%20Data%20Lineups%20v2.0.0.pdf)

## Development

### Running with Dev Container
This project includes a Dev Container configuration for VS Code. Open the project in VS Code and use "Reopen in Container" for a pre-configured development environment.

### Jupyter Notebooks
Explore the data interactively using the notebooks in `exploration/`:
- `exploration.ipynb` - General data exploration
- `heatmap.ipynb` - Heatmap visualizations
- `shots.ipynb` - Shot analysis

## Tech Stack

- **[Streamlit](https://streamlit.io/)** - Web application framework
- **[mplsoccer](https://mplsoccer.readthedocs.io/)** - Football pitch visualizations
- **[statsbombpy](https://github.com/statsbomb/statsbombpy)** - StatsBomb data API
- **[matplotlib](https://matplotlib.org/)** / **[seaborn](https://seaborn.pydata.org/)** - Plotting
- **[pandas](https://pandas.pydata.org/)** - Data manipulation
- **[fpdf2](https://py-pdf.github.io/fpdf2/)** - PDF generation

## License

This project uses StatsBomb open data which is free to use under the [StatsBomb Public Data License](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).

### Attribution requirements

Clause 1.4 of the agreement: *"The User is required to accredit any publication of analysis formed from StatsBomb Data with the StatsBomb brand logo."*

The official logo (`assets/SB - Icon Lockup - Colour positive.png`, from the StatsBomb media pack) is drawn on **every visualisation** and in the **PDF report footer**. It is placed on the matplotlib figure itself, not just in the interface, so exported PNGs carry it too. If the logo file is missing, the figures fall back to a `Data: StatsBomb` text credit — never to nothing.

Keep this in place: removing it puts the project in breach of the licence.

Clause 1.2.2 also forbids commercially exploiting the data or any analysis derived from it.

## Author

[@alex.mrl38](https://github.com/AlexandreMorel)

---

*Built with data from StatsBomb*
