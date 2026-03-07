import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .coordinator import ESPNCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors from a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        _LOGGER.error("Coordinator not found for entry %s", entry.entry_id)
        return

    tracked = entry.data.get("tracked", [])
    entities = []
    for idx, item in enumerate(tracked):
        entities.append(MyScoreboardSensor(coordinator, entry.entry_id, idx, item))
    async_add_entities(entities, True)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up sensors from YAML configuration.

    Example configuration.yaml:

    sensor:
      - platform: myscoreboard
        tracked:
          - league: "NHL"
            name: "NHL Today"
            teams: ["BOS", "NYR"]
          - league: "ENG_PREMIER_LEAGUE"
            name: "Premier League"
    """
    tracked = config.get("tracked", [])
    if not tracked:
        return

    session = aiohttp_client.async_get_clientsession(hass)
    coordinator = ESPNCoordinator(hass, session, tracked)

    # Use async_refresh for YAML-based setup (not config entry)
    await coordinator.async_refresh()

    if coordinator.last_update_success is False:
        _LOGGER.warning("Initial scoreboard fetch had errors, will retry on next interval")

    hass.data.setdefault(DOMAIN, {})["yaml"] = coordinator

    entities = []
    for idx, item in enumerate(tracked):
        entities.append(MyScoreboardSensor(coordinator, "yaml", idx, item))
    async_add_entities(entities, True)


class MyScoreboardSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing one tracked league/sport."""

    def __init__(self, coordinator, entry_id, idx, config):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._idx = idx
        self._config = config
        self._league = config.get("league", "")
        self._sensor_name = config.get("name") or f"MyScoreboard {self._league}"
        self._attr_unique_id = f"myscoreboard_{entry_id}_{idx}"

    @property
    def name(self):
        return self._sensor_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def icon(self):
        return "mdi:scoreboard"

    @property
    def native_value(self):
        """State is the number of games, or 'error'/'unavailable'."""
        data = self._get_league_data()
        if data is None:
            return None
        if "error" in data:
            return "error"
        return data.get("game_count", 0)

    @property
    def extra_state_attributes(self):
        data = self._get_league_data()
        if data is None:
            return {"league": self._league}

        games = data.get("games", [])
        live_count = sum(1 for g in games if g.get("game_state") == 1)
        final_count = sum(1 for g in games if g.get("game_state") == 2)
        pre_count = sum(1 for g in games if g.get("game_state") == 0)

        return {
            "league": self._league,
            "game_count": len(games),
            "live_count": live_count,
            "final_count": final_count,
            "pre_count": pre_count,
            "games": games,
        }

    def _get_league_data(self):
        """Get this sensor's league data from the coordinator."""
        if self.coordinator.data is None:
            return None
        name = self._config.get("name") or self._league
        return self.coordinator.data.get(name)
