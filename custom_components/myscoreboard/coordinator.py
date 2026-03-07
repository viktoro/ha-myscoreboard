from datetime import datetime, timedelta
import logging
import async_timeout

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DEFAULT_SCAN_INTERVAL,
    LEAGUE_PATHS,
    GAME_STATE_PRE,
    GAME_STATE_LIVE,
    GAME_STATE_FINAL,
)

_LOGGER = logging.getLogger(__name__)

ESPN_BASE = "https://site.web.api.espn.com/apis/site/v2/sports"


def resolve_league_path(league: str) -> str | None:
    """Resolve a league code to its ESPN API path.

    Accepts either a league code (e.g. 'NHL') or a raw ESPN path
    (e.g. 'soccer/eng.1') for backwards compatibility.
    """
    if league in LEAGUE_PATHS:
        return LEAGUE_PATHS[league]
    # Allow raw ESPN paths as fallback
    if "/" in league:
        return league
    return None


def build_espn_url(league: str, date_str: str) -> str | None:
    """Build the ESPN scoreboard URL for a league and date."""
    path = resolve_league_path(league)
    if path is None:
        return None

    if "scorepanel" in path:
        url = f"{ESPN_BASE}/{path}?dates={date_str}&limit=200"
    else:
        url = f"{ESPN_BASE}/{path}/scoreboard?dates={date_str}&limit=200"

    # Special group parameters for college sports
    if league == "NCAAF":
        url += "&groups=80"
    elif league == "NCAAM":
        url += "&groups=50"
    elif league == "NCAAM_MM":
        url += "&groups=100"

    return url


def parse_game_state(status_type_id: str) -> int:
    """Map ESPN status.type.id to game state integer."""
    pre = {"0", "1", "5", "6", "8"}
    live = {"2", "21", "22", "23", "24", "25", "26", "43", "44", "48", "49", "7", "17"}
    final = {"3", "28", "45", "46", "47", "4", "9", "10"}

    if status_type_id in pre:
        return GAME_STATE_PRE
    if status_type_id in live:
        return GAME_STATE_LIVE
    if status_type_id in final:
        return GAME_STATE_FINAL
    return GAME_STATE_PRE


def parse_status_text(status_type_id: str, status_obj: dict) -> str:
    """Derive human-readable status text from ESPN status object."""
    type_info = status_obj.get("type", {})

    match status_type_id:
        case "0":
            return "TBD"
        case "1":
            short = type_info.get("shortDetail", "")
            if not short or short == "Scheduled":
                return "Scheduled"
            return short
        case "5" | "6":
            return type_info.get("detail", "Postponed")
        case "8":
            return "Suspended"
        case "2" | "21" | "22" | "24" | "25" | "26" | "43" | "44" | "48":
            return type_info.get("shortDetail", "In Progress")
        case "23":
            return type_info.get("description", "Halftime")
        case "7" | "17":
            return type_info.get("description", "Delayed")
        case "49":
            return "Halftime (ET)"
        case "3" | "28":
            return type_info.get("shortDetail", "Final")
        case "45" | "46":
            return "FT (AET)"
        case "47":
            return "FT (PK)"
        case "4" | "9" | "10":
            return "Forfeit"
        case _:
            return type_info.get("detail", "Unknown")


def parse_event(event: dict, league: str, teams_filter: list | None = None) -> dict | None:
    """Parse a single ESPN event into a structured game dict."""
    comps = event.get("competitions", [])
    if not comps:
        return None
    comp = comps[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    home = competitors[0]
    away = competitors[1]
    if home.get("homeAway") == "away":
        home, away = away, home

    home_team = home.get("team", {})
    away_team = away.get("team", {})

    home_abbr = home_team.get("abbreviation", "")
    away_abbr = away_team.get("abbreviation", "")

    # Team filtering
    if teams_filter:
        matched = False
        for t in teams_filter:
            if t == "@T25":
                home_rank = (home.get("curatedRank") or {}).get("current", 99)
                away_rank = (away.get("curatedRank") or {}).get("current", 99)
                if 1 <= home_rank <= 25 or 1 <= away_rank <= 25:
                    matched = True
                    break
            elif t in (home_abbr, away_abbr):
                matched = True
                break
        if not matched:
            return None

    status_obj = event.get("status", {})
    status_type_id = str(status_obj.get("type", {}).get("id", "0"))
    game_state = parse_game_state(status_type_id)
    status_text = parse_status_text(status_type_id, status_obj)

    # For college sports, use abbreviation + name
    is_college = league.startswith("NCAA")
    if is_college:
        home_long = f"{home_abbr} {home_team.get('name', '')}" if home_abbr else home_team.get("name", "")
        away_long = f"{away_abbr} {away_team.get('name', '')}" if away_abbr else away_team.get("name", "")
    else:
        home_long = home_team.get("shortDisplayName", home_team.get("displayName", ""))
        away_long = away_team.get("shortDisplayName", away_team.get("displayName", ""))

    # Penalty shootout score
    pk_score = None
    if status_type_id == "47":
        h_pk = home.get("shootoutScore", "")
        a_pk = away.get("shootoutScore", "")
        pk_score = f"{h_pk}x{a_pk}"

    # Broadcast channels
    broadcasts = []
    for market in comp.get("broadcasts", []):
        for name in market.get("names", []):
            if name not in broadcasts:
                broadcasts.append(name)

    # Playoff / series info
    playoff_status = ""
    series = comp.get("series")
    if series:
        parts = []
        notes = comp.get("notes", [])
        if notes and notes[0].get("headline"):
            parts.append(notes[0]["headline"])
        elif comp.get("leg", {}).get("displayValue"):
            parts.append(comp["leg"]["displayValue"])
        if series.get("summary"):
            parts.append(series["summary"])
        elif series.get("title"):
            parts.insert(0, series["title"])
        playoff_status = " - ".join(parts)

    # NCAA rankings
    home_rank = None
    away_rank = None
    if is_college:
        hr = (home.get("curatedRank") or {}).get("current", 99)
        ar = (away.get("curatedRank") or {}).get("current", 99)
        if 1 <= hr <= 25:
            home_rank = hr
        if 1 <= ar <= 25:
            away_rank = ar

    home_score_raw = home.get("score")
    away_score_raw = away.get("score")

    return {
        "game_id": event.get("id"),
        "start_time": event.get("date"),
        "game_state": game_state,  # 0=pre, 1=live, 2=final
        "status": status_text,
        "home_team": home_team.get("displayName", ""),
        "away_team": away_team.get("displayName", ""),
        "home_abbr": home_abbr,
        "away_abbr": away_abbr,
        "home_short": home_long,
        "away_short": away_long,
        "home_score": int(home_score_raw) if home_score_raw is not None else None,
        "away_score": int(away_score_raw) if away_score_raw is not None else None,
        "home_logo": home_team.get("logo", ""),
        "away_logo": away_team.get("logo", ""),
        "home_rank": home_rank,
        "away_rank": away_rank,
        "broadcasts": broadcasts,
        "playoff_status": playoff_status,
        "pk_score": pk_score,
    }


class ESPNCoordinator(DataUpdateCoordinator):
    """Fetches scoreboard data from ESPN for configured leagues."""

    def __init__(self, hass, session, tracked, scan_interval=None):
        super().__init__(
            hass,
            _LOGGER,
            name="myscoreboard",
            update_interval=timedelta(seconds=scan_interval or DEFAULT_SCAN_INTERVAL),
        )
        self.session = session
        self.tracked = tracked  # list of dicts with league, name, teams, date keys

    async def _async_update_data(self):
        results = {}
        today = datetime.utcnow().strftime("%Y%m%d")

        for item in self.tracked:
            league = item.get("league", "")
            date_str = item.get("date") or today
            teams_filter = item.get("teams")
            name = item.get("name", league)

            url = build_espn_url(league, date_str)
            if url is None:
                _LOGGER.warning("Unknown league code: %s", league)
                results[name] = {"league": league, "error": f"Unknown league: {league}", "games": []}
                continue

            try:
                async with async_timeout.timeout(15):
                    async with self.session.get(url) as resp:
                        if resp.status != 200:
                            _LOGGER.error("ESPN returned %s for %s", resp.status, url)
                            results[name] = {"league": league, "error": f"HTTP {resp.status}", "games": []}
                            continue
                        body = await resp.json()
            except Exception as err:
                _LOGGER.error("Error fetching %s: %s", url, err)
                results[name] = {"league": league, "error": str(err), "games": []}
                continue

            # Rugby scorepanel has a different response structure
            path = resolve_league_path(league) or ""
            if "scorepanel" in path:
                events = []
                for score_block in body.get("scores", []):
                    events.extend(score_block.get("events", []))
            else:
                events = body.get("events", [])

            games = []
            for ev in events:
                parsed = parse_event(ev, league, teams_filter)
                if parsed is not None:
                    games.append(parsed)

            # Sort by start time, then away team abbreviation
            games.sort(key=lambda g: (g.get("start_time", ""), g.get("away_abbr", "")))

            results[name] = {
                "league": league,
                "game_count": len(games),
                "games": games,
            }
            _LOGGER.debug("Fetched %d games for %s (%s)", len(games), name, league)

        return results
