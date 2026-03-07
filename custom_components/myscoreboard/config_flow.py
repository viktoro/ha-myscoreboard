import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, LEAGUE_PATHS, LEAGUE_NAMES, DEFAULT_SCAN_INTERVAL


def _league_options() -> dict[str, str]:
    """Build {code: "Display Name"} for the league selector, sorted by name."""
    opts = {}
    for code in LEAGUE_PATHS:
        opts[code] = LEAGUE_NAMES.get(code, code)
    return dict(sorted(opts.items(), key=lambda x: x[1]))


class MyScoreboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyScoreboard."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Step 1: Pick a league and optionally filter teams."""
        errors = {}

        if user_input is not None:
            league = user_input["league"]
            name = user_input.get("name", "").strip()
            if not name:
                name = LEAGUE_NAMES.get(league, league)
            teams_raw = user_input.get("teams", "").strip()
            teams = (
                [t.strip().upper() for t in teams_raw.split(",") if t.strip()]
                if teams_raw
                else None
            )

            scan_interval = user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL)

            # Build the tracked list (single entry per config entry)
            tracked = [{"league": league, "name": name}]
            if teams:
                tracked[0]["teams"] = teams

            # Use name as unique id to prevent exact duplicates
            await self.async_set_unique_id(f"{DOMAIN}_{league}_{name}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=name,
                data={"tracked": tracked, "scan_interval": scan_interval},
            )

        league_opts = _league_options()

        schema = vol.Schema(
            {
                vol.Required("league"): vol.In(league_opts),
                vol.Optional("name", default=""): str,
                vol.Optional("teams", default=""): str,
                vol.Optional(
                    "scan_interval", default=DEFAULT_SCAN_INTERVAL
                ): vol.All(int, vol.Range(min=30, max=3600)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "leagues_count": str(len(LEAGUE_PATHS)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MyScoreboardOptionsFlow(config_entry)


class MyScoreboardOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing MyScoreboard entry."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Edit the league settings."""
        tracked = self.config_entry.data.get("tracked", [{}])
        current = tracked[0] if tracked else {}

        if user_input is not None:
            league = user_input["league"]
            name = user_input.get("name", "").strip()
            if not name:
                name = LEAGUE_NAMES.get(league, league)
            teams_raw = user_input.get("teams", "").strip()
            teams = (
                [t.strip().upper() for t in teams_raw.split(",") if t.strip()]
                if teams_raw
                else None
            )

            scan_interval = user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL)

            new_tracked = [{"league": league, "name": name}]
            if teams:
                new_tracked[0]["teams"] = teams

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=name,
                data={"tracked": new_tracked, "scan_interval": scan_interval},
            )
            return self.async_create_entry(title="", data={})

        league_opts = _league_options()
        current_teams = current.get("teams", [])
        teams_str = ", ".join(current_teams) if current_teams else ""

        schema = vol.Schema(
            {
                vol.Required("league", default=current.get("league", "")): vol.In(
                    league_opts
                ),
                vol.Optional("name", default=current.get("name", "")): str,
                vol.Optional("teams", default=teams_str): str,
                vol.Optional(
                    "scan_interval",
                    default=self.config_entry.data.get(
                        "scan_interval", DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=30, max=3600)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
