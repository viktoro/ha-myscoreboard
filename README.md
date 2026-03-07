# MyScoreboard

A Home Assistant custom integration that displays live sports scores from ESPN.

Inspired by [MMM-MyScoreboard](https://github.com/dathbe/MMM-MyScoreboard).

## Features

- Real-time scores from the ESPN API
- 190+ supported leagues (NFL, NHL, NBA, MLB, Premier League, La Liga, and many more)
- Filter by specific teams
- Configurable polling interval
- Config flow UI for easy setup

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Search for "MyScoreboard" and install
3. Restart Home Assistant

### Manual

Copy the `custom_components/myscoreboard` directory into your Home Assistant `config/custom_components/` directory.

## Configuration

### UI (Config Flow)

Go to **Settings > Devices & Services > Add Integration** and search for **MyScoreboard**.

You can configure:
- **League** — pick from 190+ supported leagues
- **Display name** — optional custom name for the sensor
- **Filter teams** — comma-separated team abbreviations (e.g. `BOS, NYR`)
- **Poll interval** — how often to fetch scores (30–3600 seconds, default 120)

### YAML

```yaml
sensor:
  - platform: myscoreboard
    tracked:
      - league: "NHL"
        name: "NHL Today"
        teams: ["BOS", "NYR"]
      - league: "ENG_PREMIER_LEAGUE"
        name: "Premier League"
```

## Lovelace Card

A companion Lovelace card is available in a separate repository for displaying scores on your dashboard.

## Sensor Data

Each sensor exposes the following attributes:

| Attribute | Description |
|-----------|-------------|
| `league` | League code |
| `game_count` | Total number of games |
| `live_count` | Games currently in progress |
| `final_count` | Completed games |
| `pre_count` | Upcoming games |
| `games` | List of game objects with scores, teams, logos, status, etc. |
