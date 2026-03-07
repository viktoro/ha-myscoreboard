"""Unit tests for coordinator pure functions."""

import pytest
from myscoreboard.coordinator import (
    resolve_league_path,
    build_espn_url,
    parse_game_state,
    parse_status_text,
    parse_event,
)
from myscoreboard.const import GAME_STATE_PRE, GAME_STATE_LIVE, GAME_STATE_FINAL


class TestResolveLeaguePath:
    def test_known_league(self):
        assert resolve_league_path("NHL") == "hockey/nhl"

    def test_soccer_league(self):
        assert resolve_league_path("ENG_PREMIER_LEAGUE") == "soccer/eng.1"

    def test_raw_path(self):
        assert resolve_league_path("soccer/eng.1") == "soccer/eng.1"

    def test_unknown_league(self):
        assert resolve_league_path("FAKE_LEAGUE") is None


class TestBuildEspnUrl:
    def test_standard_league(self):
        url = build_espn_url("NHL", "20260305")
        assert url is not None
        assert "hockey/nhl/scoreboard" in url
        assert "dates=20260305" in url
        assert "limit=200" in url

    def test_ncaaf_groups(self):
        url = build_espn_url("NCAAF", "20260305")
        assert url is not None
        assert "groups=80" in url

    def test_ncaam_groups(self):
        url = build_espn_url("NCAAM", "20260305")
        assert url is not None
        assert "groups=50" in url

    def test_ncaam_mm_groups(self):
        url = build_espn_url("NCAAM_MM", "20260305")
        assert url is not None
        assert "groups=100" in url

    def test_rugby_scorepanel(self):
        url = build_espn_url("RUGBY", "20260305")
        assert url is not None
        assert "scorepanel" in url
        assert "/scoreboard" not in url

    def test_unknown_returns_none(self):
        assert build_espn_url("FAKE", "20260305") is None


class TestParseGameState:
    @pytest.mark.parametrize("status_id", ["0", "1", "5", "6", "8"])
    def test_pre_game(self, status_id):
        assert parse_game_state(status_id) == GAME_STATE_PRE

    @pytest.mark.parametrize("status_id", ["2", "21", "22", "23", "7", "17"])
    def test_live(self, status_id):
        assert parse_game_state(status_id) == GAME_STATE_LIVE

    @pytest.mark.parametrize("status_id", ["3", "28", "45", "46", "47", "4", "9", "10"])
    def test_final(self, status_id):
        assert parse_game_state(status_id) == GAME_STATE_FINAL

    def test_unknown_defaults_to_pre(self):
        assert parse_game_state("999") == GAME_STATE_PRE


class TestParseStatusText:
    def test_tbd(self):
        assert parse_status_text("0", {}) == "TBD"

    def test_scheduled_with_shortdetail(self):
        status = {"type": {"shortDetail": "7:00 PM ET"}}
        assert parse_status_text("1", status) == "7:00 PM ET"

    def test_scheduled_no_detail(self):
        assert parse_status_text("1", {}) == "Scheduled"

    def test_scheduled_detail_is_scheduled(self):
        status = {"type": {"shortDetail": "Scheduled"}}
        assert parse_status_text("1", status) == "Scheduled"

    def test_live_in_progress(self):
        status = {"type": {"shortDetail": "3rd 5:42"}}
        assert parse_status_text("2", status) == "3rd 5:42"

    def test_final(self):
        status = {"type": {"shortDetail": "Final"}}
        assert parse_status_text("3", status) == "Final"

    def test_pk(self):
        assert parse_status_text("47", {}) == "FT (PK)"

    def test_forfeit(self):
        assert parse_status_text("4", {}) == "Forfeit"


def _make_event(
    home_abbr="BOS",
    away_abbr="NYR",
    home_score=3,
    away_score=1,
    status_id="3",
    event_id="401",
    date="2026-03-05T00:00Z",
):
    return {
        "id": event_id,
        "date": date,
        "status": {"type": {"id": status_id, "shortDetail": "Final"}},
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": str(home_score),
                        "team": {
                            "abbreviation": home_abbr,
                            "displayName": f"{home_abbr} Team",
                            "shortDisplayName": home_abbr,
                            "logo": f"https://example.com/{home_abbr}.png",
                        },
                    },
                    {
                        "homeAway": "away",
                        "score": str(away_score),
                        "team": {
                            "abbreviation": away_abbr,
                            "displayName": f"{away_abbr} Team",
                            "shortDisplayName": away_abbr,
                            "logo": f"https://example.com/{away_abbr}.png",
                        },
                    },
                ],
                "broadcasts": [{"names": ["ESPN"]}],
            }
        ],
    }


class TestParseEvent:
    def test_basic_parse(self):
        event = _make_event()
        result = parse_event(event, "NHL")
        assert result is not None
        assert result["game_id"] == "401"
        assert result["home_abbr"] == "BOS"
        assert result["away_abbr"] == "NYR"
        assert result["home_score"] == 3
        assert result["away_score"] == 1
        assert result["game_state"] == GAME_STATE_FINAL
        assert result["broadcasts"] == ["ESPN"]

    def test_team_filter_match(self):
        event = _make_event()
        result = parse_event(event, "NHL", teams_filter=["BOS"])
        assert result is not None

    def test_team_filter_no_match(self):
        event = _make_event()
        result = parse_event(event, "NHL", teams_filter=["TOR"])
        assert result is None

    def test_swapped_home_away(self):
        event = _make_event()
        # Swap the homeAway values
        comps = event["competitions"][0]["competitors"]
        comps[0]["homeAway"] = "away"
        comps[1]["homeAway"] = "home"
        result = parse_event(event, "NHL")
        assert result is not None
        assert result["home_abbr"] == "NYR"
        assert result["away_abbr"] == "BOS"

    def test_no_competitions(self):
        event = {"id": "1", "competitions": []}
        assert parse_event(event, "NHL") is None

    def test_pre_game_scores_none(self):
        event = _make_event(status_id="1")
        # Pre-game: ESPN may not include score
        event["competitions"][0]["competitors"][0].pop("score")
        event["competitions"][0]["competitors"][1].pop("score")
        result = parse_event(event, "NHL")
        assert result is not None
        assert result["home_score"] is None
        assert result["away_score"] is None
        assert result["game_state"] == GAME_STATE_PRE
