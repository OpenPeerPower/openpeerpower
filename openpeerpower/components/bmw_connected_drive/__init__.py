"""Reads vehicle status from BMW connected drive portal."""
import logging

from bimmer_connected.account import ConnectedDriveAccount
from bimmer_connected.country_selector import get_region_from_name
import voluptuous as vol

from openpeerpower.const import CONF_PASSWORD, CONF_USERNAME
from openpeerpower.helpers import discovery
import openpeerpower.helpers.config_validation as cv
from openpeerpower.helpers.event import track_utc_time_change
import openpeerpower.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bmw_connected_drive"
CONF_REGION = "region"
CONF_READ_ONLY = "read_only"
ATTR_VIN = "vin"

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_REGION): vol.Any("north_america", "china", "rest_of_world"),
        vol.Optional(CONF_READ_ONLY, default=False): cv.boolean,
    }
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: {cv.string: ACCOUNT_SCHEMA}}, extra=vol.ALLOW_EXTRA)

SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_VIN): cv.string})


BMW_COMPONENTS = ["binary_sensor", "device_tracker", "lock", "sensor"]
UPDATE_INTERVAL = 5  # in minutes

SERVICE_UPDATE_STATE = "update_state"

_SERVICE_MAP = {
    "light_flash": "trigger_remote_light_flash",
    "sound_horn": "trigger_remote_horn",
    "activate_air_conditioning": "trigger_remote_air_conditioning",
}


def setup(opp, config: dict):
    """Set up the BMW connected drive components."""
    accounts = []
    for name, account_config in config[DOMAIN].items():
        accounts.append(setup_account(account_config, opp, name))

    opp.data[DOMAIN] = accounts

    def _update_all(call) -> None:
        """Update all BMW accounts."""
        for cd_account in opp.data[DOMAIN]:
            cd_account.update()

    # Service to manually trigger updates for all accounts.
    opp.services.register(DOMAIN, SERVICE_UPDATE_STATE, _update_all)

    _update_all(None)

    for component in BMW_COMPONENTS:
        discovery.load_platform(opp, component, DOMAIN, {}, config)

    return True


def setup_account(account_config: dict, opp, name: str) -> "BMWConnectedDriveAccount":
    """Set up a new BMWConnectedDriveAccount based on the config."""
    username = account_config[CONF_USERNAME]
    password = account_config[CONF_PASSWORD]
    region = account_config[CONF_REGION]
    read_only = account_config[CONF_READ_ONLY]

    _LOGGER.debug("Adding new account %s", name)
    cd_account = BMWConnectedDriveAccount(username, password, region, name, read_only)

    def execute_service(call):
        """Execute a service for a vehicle.

        This must be a member function as we need access to the cd_account
        object here.
        """
        vin = call.data[ATTR_VIN]
        vehicle = cd_account.account.get_vehicle(vin)
        if not vehicle:
            _LOGGER.error("Could not find a vehicle for VIN %s", vin)
            return
        function_name = _SERVICE_MAP[call.service]
        function_call = getattr(vehicle.remote_services, function_name)
        function_call()

    if not read_only:
        # register the remote services
        for service in _SERVICE_MAP:
            opp.services.register(
                DOMAIN, service, execute_service, schema=SERVICE_SCHEMA
            )

    # update every UPDATE_INTERVAL minutes, starting now
    # this should even out the load on the servers
    now = dt_util.utcnow()
    track_utc_time_change(
        opp,
        cd_account.update,
        minute=range(now.minute % UPDATE_INTERVAL, 60, UPDATE_INTERVAL),
        second=now.second,
    )

    return cd_account


class BMWConnectedDriveAccount:
    """Representation of a BMW vehicle."""

    def __init__(
        self, username: str, password: str, region_str: str, name: str, read_only
    ) -> None:
        """Initialize account."""

        region = get_region_from_name(region_str)

        self.read_only = read_only
        self.account = ConnectedDriveAccount(username, password, region)
        self.name = name
        self._update_listeners = []

    def update(self, *_):
        """Update the state of all vehicles.

        Notify all listeners about the update.
        """
        _LOGGER.debug(
            "Updating vehicle state for account %s, notifying %d listeners",
            self.name,
            len(self._update_listeners),
        )
        try:
            self.account.update_vehicle_states()
            for listener in self._update_listeners:
                listener()
        except OSError as exception:
            _LOGGER.error(
                "Could not connect to the BMW Connected Drive portal. "
                "The vehicle state could not be updated."
            )
            _LOGGER.exception(exception)

    def add_update_listener(self, listener):
        """Add a listener for update notifications."""
        self._update_listeners.append(listener)
