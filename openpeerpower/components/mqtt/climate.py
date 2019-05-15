"""Support for MQTT climate devices."""
import logging

import voluptuous as vol

from openpeerpower.components import climate, mqtt
from openpeerpower.components.climate import (
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA, ClimateDevice)
from openpeerpower.components.climate.const import (
    ATTR_OPERATION_MODE, DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, STATE_AUTO,
    STATE_COOL, STATE_DRY, STATE_FAN_ONLY, STATE_HEAT, SUPPORT_AUX_HEAT,
    SUPPORT_AWAY_MODE, SUPPORT_FAN_MODE, SUPPORT_HOLD_MODE,
    SUPPORT_OPERATION_MODE, SUPPORT_SWING_MODE, SUPPORT_TARGET_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH, SUPPORT_TARGET_TEMPERATURE_LOW,
    SUPPORT_TARGET_TEMPERATURE_HIGH)
from openpeerpower.components.fan import SPEED_HIGH, SPEED_LOW, SPEED_MEDIUM
from openpeerpower.const import (
    ATTR_TEMPERATURE, CONF_DEVICE, CONF_NAME, CONF_VALUE_TEMPLATE, STATE_OFF,
    STATE_ON)
from openpeerpower.core import callback
import openpeerpower.helpers.config_validation as cv
from openpeerpower.helpers.dispatcher import async_dispatcher_connect
from openpeerpower.helpers.typing import ConfigType, OpenPeerPowerType

from . import (
    ATTR_DISCOVERY_HASH, CONF_QOS, CONF_RETAIN, CONF_UNIQUE_ID,
    MQTT_BASE_PLATFORM_SCHEMA, MqttAttributes, MqttAvailability,
    MqttDiscoveryUpdate, MqttEntityDeviceInfo, subscription)
from .discovery import MQTT_DISCOVERY_NEW, clear_discovery_hash

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'MQTT HVAC'

CONF_AUX_COMMAND_TOPIC = 'aux_command_topic'
CONF_AUX_STATE_TEMPLATE = 'aux_state_template'
CONF_AUX_STATE_TOPIC = 'aux_state_topic'
CONF_AWAY_MODE_COMMAND_TOPIC = 'away_mode_command_topic'
CONF_AWAY_MODE_STATE_TEMPLATE = 'away_mode_state_template'
CONF_AWAY_MODE_STATE_TOPIC = 'away_mode_state_topic'
CONF_CURRENT_TEMP_TEMPLATE = 'current_temperature_template'
CONF_CURRENT_TEMP_TOPIC = 'current_temperature_topic'
CONF_FAN_MODE_COMMAND_TOPIC = 'fan_mode_command_topic'
CONF_FAN_MODE_LIST = 'fan_modes'
CONF_FAN_MODE_STATE_TEMPLATE = 'fan_mode_state_template'
CONF_FAN_MODE_STATE_TOPIC = 'fan_mode_state_topic'
CONF_HOLD_COMMAND_TOPIC = 'hold_command_topic'
CONF_HOLD_STATE_TEMPLATE = 'hold_state_template'
CONF_HOLD_STATE_TOPIC = 'hold_state_topic'
CONF_MODE_COMMAND_TOPIC = 'mode_command_topic'
CONF_MODE_LIST = 'modes'
CONF_MODE_STATE_TEMPLATE = 'mode_state_template'
CONF_MODE_STATE_TOPIC = 'mode_state_topic'
CONF_PAYLOAD_OFF = 'payload_off'
CONF_PAYLOAD_ON = 'payload_on'
CONF_POWER_COMMAND_TOPIC = 'power_command_topic'
CONF_POWER_STATE_TEMPLATE = 'power_state_template'
CONF_POWER_STATE_TOPIC = 'power_state_topic'
CONF_SEND_IF_OFF = 'send_if_off'
CONF_SWING_MODE_COMMAND_TOPIC = 'swing_mode_command_topic'
CONF_SWING_MODE_LIST = 'swing_modes'
CONF_SWING_MODE_STATE_TEMPLATE = 'swing_mode_state_template'
CONF_SWING_MODE_STATE_TOPIC = 'swing_mode_state_topic'
CONF_TEMP_COMMAND_TOPIC = 'temperature_command_topic'
CONF_TEMP_HIGH_COMMAND_TOPIC = 'temperature_high_command_topic'
CONF_TEMP_HIGH_STATE_TEMPLATE = 'temperature_high_state_template'
CONF_TEMP_HIGH_STATE_TOPIC = 'temperature_high_state_topic'
CONF_TEMP_LOW_COMMAND_TOPIC = 'temperature_low_command_topic'
CONF_TEMP_LOW_STATE_TEMPLATE = 'temperature_low_state_template'
CONF_TEMP_LOW_STATE_TOPIC = 'temperature_low_state_topic'
CONF_TEMP_STATE_TEMPLATE = 'temperature_state_template'
CONF_TEMP_STATE_TOPIC = 'temperature_state_topic'
CONF_TEMP_INITIAL = 'initial'
CONF_TEMP_MAX = 'max_temp'
CONF_TEMP_MIN = 'min_temp'
CONF_TEMP_STEP = 'temp_step'

TEMPLATE_KEYS = (
    CONF_AUX_STATE_TEMPLATE,
    CONF_AWAY_MODE_STATE_TEMPLATE,
    CONF_CURRENT_TEMP_TEMPLATE,
    CONF_FAN_MODE_STATE_TEMPLATE,
    CONF_HOLD_STATE_TEMPLATE,
    CONF_MODE_STATE_TEMPLATE,
    CONF_POWER_STATE_TEMPLATE,
    CONF_SWING_MODE_STATE_TEMPLATE,
    CONF_TEMP_HIGH_STATE_TEMPLATE,
    CONF_TEMP_LOW_STATE_TEMPLATE,
    CONF_TEMP_STATE_TEMPLATE,
)

TOPIC_KEYS = (
    CONF_AUX_COMMAND_TOPIC,
    CONF_AUX_STATE_TOPIC,
    CONF_AWAY_MODE_COMMAND_TOPIC,
    CONF_AWAY_MODE_STATE_TOPIC,
    CONF_CURRENT_TEMP_TOPIC,
    CONF_FAN_MODE_COMMAND_TOPIC,
    CONF_FAN_MODE_STATE_TOPIC,
    CONF_HOLD_COMMAND_TOPIC,
    CONF_HOLD_STATE_TOPIC,
    CONF_MODE_COMMAND_TOPIC,
    CONF_MODE_STATE_TOPIC,
    CONF_POWER_COMMAND_TOPIC,
    CONF_POWER_STATE_TOPIC,
    CONF_SWING_MODE_COMMAND_TOPIC,
    CONF_SWING_MODE_STATE_TOPIC,
    CONF_TEMP_COMMAND_TOPIC,
    CONF_TEMP_HIGH_COMMAND_TOPIC,
    CONF_TEMP_HIGH_STATE_TOPIC,
    CONF_TEMP_LOW_COMMAND_TOPIC,
    CONF_TEMP_LOW_STATE_TOPIC,
    CONF_TEMP_STATE_TOPIC,
)

SCHEMA_BASE = CLIMATE_PLATFORM_SCHEMA.extend(MQTT_BASE_PLATFORM_SCHEMA.schema)
PLATFORM_SCHEMA = SCHEMA_BASE.extend({
    vol.Optional(CONF_AUX_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_AUX_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_AUX_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_AWAY_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_AWAY_MODE_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_AWAY_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_CURRENT_TEMP_TEMPLATE): cv.template,
    vol.Optional(CONF_CURRENT_TEMP_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_DEVICE): mqtt.MQTT_ENTITY_DEVICE_INFO_SCHEMA,
    vol.Optional(CONF_FAN_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_FAN_MODE_LIST,
                 default=[STATE_AUTO, SPEED_LOW,
                          SPEED_MEDIUM, SPEED_HIGH]): cv.ensure_list,
    vol.Optional(CONF_FAN_MODE_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_FAN_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_HOLD_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_HOLD_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_HOLD_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_MODE_LIST,
                 default=[STATE_AUTO, STATE_OFF, STATE_COOL, STATE_HEAT,
                          STATE_DRY, STATE_FAN_ONLY]): cv.ensure_list,
    vol.Optional(CONF_MODE_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PAYLOAD_ON, default="ON"): cv.string,
    vol.Optional(CONF_PAYLOAD_OFF, default="OFF"): cv.string,
    vol.Optional(CONF_POWER_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_POWER_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_POWER_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_RETAIN, default=mqtt.DEFAULT_RETAIN): cv.boolean,
    vol.Optional(CONF_SEND_IF_OFF, default=True): cv.boolean,
    vol.Optional(CONF_SWING_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_SWING_MODE_LIST,
                 default=[STATE_ON, STATE_OFF]): cv.ensure_list,
    vol.Optional(CONF_SWING_MODE_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_SWING_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_TEMP_INITIAL, default=21): cv.positive_int,
    vol.Optional(CONF_TEMP_MIN, default=DEFAULT_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_TEMP_MAX, default=DEFAULT_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_TEMP_STEP, default=1.0): vol.Coerce(float),
    vol.Optional(CONF_TEMP_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_TEMP_HIGH_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_TEMP_HIGH_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_TEMP_LOW_COMMAND_TOPIC): mqtt.valid_publish_topic,
    vol.Optional(CONF_TEMP_LOW_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_TEMP_STATE_TEMPLATE): cv.template,
    vol.Optional(CONF_TEMP_STATE_TOPIC): mqtt.valid_subscribe_topic,
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
}).extend(mqtt.MQTT_AVAILABILITY_SCHEMA.schema).extend(
    mqtt.MQTT_JSON_ATTRS_SCHEMA.schema)


async def async_setup_platform(opp: OpenPeerPowerType, config: ConfigType,
                               async_add_entities, discovery_info=None):
    """Set up MQTT climate device through configuration.yaml."""
    await _async_setup_entity(opp, config, async_add_entities)


async def async_setup_entry(opp, config_entry, async_add_entities):
    """Set up MQTT climate device dynamically through MQTT discovery."""
    async def async_discover(discovery_payload):
        """Discover and add a MQTT climate device."""
        try:
            discovery_hash = discovery_payload.pop(ATTR_DISCOVERY_HASH)
            config = PLATFORM_SCHEMA(discovery_payload)
            await _async_setup_entity(opp, config, async_add_entities,
                                      config_entry, discovery_hash)
        except Exception:
            if discovery_hash:
                clear_discovery_hash(opp, discovery_hash)
            raise

    async_dispatcher_connect(
        opp, MQTT_DISCOVERY_NEW.format(climate.DOMAIN, 'mqtt'),
        async_discover)


async def _async_setup_entity(opp, config, async_add_entities,
                              config_entry=None, discovery_hash=None):
    """Set up the MQTT climate devices."""
    async_add_entities([MqttClimate(opp, config, config_entry,
                                    discovery_hash,)])


class MqttClimate(MqttAttributes, MqttAvailability, MqttDiscoveryUpdate,
                  MqttEntityDeviceInfo, ClimateDevice):
    """Representation of an MQTT climate device."""

    def __init__(self, opp, config, config_entry, discovery_hash):
        """Initialize the climate device."""
        self._config = config
        self._unique_id = config.get(CONF_UNIQUE_ID)
        self._sub_state = None

        self.opp = opp
        self._aux = False
        self._away = False
        self._current_fan_mode = None
        self._current_operation = None
        self._current_swing_mode = None
        self._current_temp = None
        self._hold = None
        self._target_temp = None
        self._target_temp_high = None
        self._target_temp_low = None
        self._topic = None
        self._unit_of_measurement = opp.config.units.temperature_unit
        self._value_templates = None

        self._setup_from_config(config)

        device_config = config.get(CONF_DEVICE)

        MqttAttributes.__init__(self, config)
        MqttAvailability.__init__(self, config)
        MqttDiscoveryUpdate.__init__(self, discovery_hash,
                                     self.discovery_update)
        MqttEntityDeviceInfo.__init__(self, device_config, config_entry)

    async def async_added_to_opp(self):
        """Handle being added to open peer power."""
        await super().async_added_to_opp()
        await self._subscribe_topics()

    async def discovery_update(self, discovery_payload):
        """Handle updated discovery message."""
        config = PLATFORM_SCHEMA(discovery_payload)
        self._config = config
        self._setup_from_config(config)
        await self.attributes_discovery_update(config)
        await self.availability_discovery_update(config)
        await self.device_info_discovery_update(config)
        await self._subscribe_topics()
        self.async_write_ha_state()

    def _setup_from_config(self, config):
        """(Re)Setup the entity."""
        self._topic = {
            key: config.get(key) for key in TOPIC_KEYS
        }

        # set to None in non-optimistic mode
        self._target_temp = self._current_fan_mode = \
            self._current_operation = self._current_swing_mode = None
        self._target_temp_low = None
        self._target_temp_high = None

        if self._topic[CONF_TEMP_STATE_TOPIC] is None:
            self._target_temp = config[CONF_TEMP_INITIAL]
        if self._topic[CONF_TEMP_LOW_STATE_TOPIC] is None:
            self._target_temp_low = config[CONF_TEMP_INITIAL]
        if self._topic[CONF_TEMP_HIGH_STATE_TOPIC] is None:
            self._target_temp_high = config[CONF_TEMP_INITIAL]

        if self._topic[CONF_FAN_MODE_STATE_TOPIC] is None:
            self._current_fan_mode = SPEED_LOW
        if self._topic[CONF_SWING_MODE_STATE_TOPIC] is None:
            self._current_swing_mode = STATE_OFF
        if self._topic[CONF_MODE_STATE_TOPIC] is None:
            self._current_operation = STATE_OFF
        self._away = False
        self._hold = None
        self._aux = False

        value_templates = {}
        for key in TEMPLATE_KEYS:
            value_templates[key] = lambda value: value
        if CONF_VALUE_TEMPLATE in config:
            value_template = config.get(CONF_VALUE_TEMPLATE)
            value_template.opp = self.opp
            value_templates = {
                key: value_template.async_render_with_possible_json_value
                for key in TEMPLATE_KEYS}
        for key in TEMPLATE_KEYS & config.keys():
            tpl = config[key]
            value_templates[key] = tpl.async_render_with_possible_json_value
            tpl.opp = self.opp
        self._value_templates = value_templates

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""
        topics = {}
        qos = self._config[CONF_QOS]

        def add_subscription(topics, topic, msg_callback):
            if self._topic[topic] is not None:
                topics[topic] = {
                    'topic': self._topic[topic],
                    'msg_callback': msg_callback,
                    'qos': qos}

        def render_template(msg, template_name):
            template = self._value_templates[template_name]
            return template(msg.payload)

        @callback
        def handle_temperature_received(msg, template_name, attr):
            """Handle temperature coming via MQTT."""
            payload = render_template(msg, template_name)

            try:
                setattr(self, attr, float(payload))
                self.async_write_ha_state()
            except ValueError:
                _LOGGER.error("Could not parse temperature from %s", payload)

        @callback
        def handle_current_temperature_received(msg):
            """Handle current temperature coming via MQTT."""
            handle_temperature_received(
                msg, CONF_CURRENT_TEMP_TEMPLATE, '_current_temp')

        add_subscription(topics, CONF_CURRENT_TEMP_TOPIC,
                         handle_current_temperature_received)

        @callback
        def handle_target_temperature_received(msg):
            """Handle target temperature coming via MQTT."""
            handle_temperature_received(
                msg, CONF_TEMP_STATE_TEMPLATE, '_target_temp')

        add_subscription(topics, CONF_TEMP_STATE_TOPIC,
                         handle_target_temperature_received)

        @callback
        def handle_temperature_low_received(msg):
            """Handle target temperature low coming via MQTT."""
            handle_temperature_received(
                msg, CONF_TEMP_LOW_STATE_TEMPLATE, '_target_temp_low')

        add_subscription(topics, CONF_TEMP_LOW_STATE_TOPIC,
                         handle_temperature_low_received)

        @callback
        def handle_temperature_high_received(msg):
            """Handle target temperature high coming via MQTT."""
            handle_temperature_received(
                msg, CONF_TEMP_HIGH_STATE_TEMPLATE, '_target_temp_high')

        add_subscription(topics, CONF_TEMP_HIGH_STATE_TOPIC,
                         handle_temperature_high_received)

        @callback
        def handle_mode_received(msg, template_name, attr, mode_list):
            """Handle receiving listed mode via MQTT."""
            payload = render_template(msg, template_name)

            if payload not in self._config[mode_list]:
                _LOGGER.error("Invalid %s mode: %s", mode_list, payload)
            else:
                setattr(self, attr, payload)
                self.async_write_ha_state()

        @callback
        def handle_current_mode_received(msg):
            """Handle receiving mode via MQTT."""
            handle_mode_received(msg, CONF_MODE_STATE_TEMPLATE,
                                 '_current_operation', CONF_MODE_LIST)

        add_subscription(topics, CONF_MODE_STATE_TOPIC,
                         handle_current_mode_received)

        @callback
        def handle_fan_mode_received(msg):
            """Handle receiving fan mode via MQTT."""
            handle_mode_received(msg, CONF_FAN_MODE_STATE_TEMPLATE,
                                 '_current_fan_mode', CONF_FAN_MODE_LIST)

        add_subscription(topics, CONF_FAN_MODE_STATE_TOPIC,
                         handle_fan_mode_received)

        @callback
        def handle_swing_mode_received(msg):
            """Handle receiving swing mode via MQTT."""
            handle_mode_received(msg, CONF_SWING_MODE_STATE_TEMPLATE,
                                 '_current_swing_mode', CONF_SWING_MODE_LIST)

        add_subscription(topics, CONF_SWING_MODE_STATE_TOPIC,
                         handle_swing_mode_received)

        @callback
        def handle_onoff_mode_received(msg, template_name, attr):
            """Handle receiving on/off mode via MQTT."""
            payload = render_template(msg, template_name)
            payload_on = self._config[CONF_PAYLOAD_ON]
            payload_off = self._config[CONF_PAYLOAD_OFF]

            if payload == "True":
                payload = payload_on
            elif payload == "False":
                payload = payload_off

            if payload == payload_on:
                setattr(self, attr, True)
            elif payload == payload_off:
                setattr(self, attr, False)
            else:
                _LOGGER.error("Invalid %s mode: %s", attr, payload)

            self.async_write_ha_state()

        @callback
        def handle_away_mode_received(msg):
            """Handle receiving away mode via MQTT."""
            handle_onoff_mode_received(
                msg, CONF_AWAY_MODE_STATE_TEMPLATE, '_away')

        add_subscription(topics, CONF_AWAY_MODE_STATE_TOPIC,
                         handle_away_mode_received)

        @callback
        def handle_aux_mode_received(msg):
            """Handle receiving aux mode via MQTT."""
            handle_onoff_mode_received(
                msg, CONF_AUX_STATE_TEMPLATE, '_aux')

        add_subscription(topics, CONF_AUX_STATE_TOPIC,
                         handle_aux_mode_received)

        @callback
        def handle_hold_mode_received(msg):
            """Handle receiving hold mode via MQTT."""
            payload = render_template(msg, CONF_HOLD_STATE_TEMPLATE)

            self._hold = payload
            self.async_write_ha_state()

        add_subscription(topics, CONF_HOLD_STATE_TOPIC,
                         handle_hold_mode_received)

        self._sub_state = await subscription.async_subscribe_topics(
            self.opp, self._sub_state,
            topics)

    async def async_will_remove_from_opp(self):
        """Unsubscribe when removed."""
        self._sub_state = await subscription.async_unsubscribe_topics(
            self.opp, self._sub_state)
        await MqttAttributes.async_will_remove_from_opp(self)
        await MqttAvailability.async_will_remove_from_opp(self)

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._config[CONF_NAME]

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def target_temperature_low(self):
        """Return the low target temperature we try to reach."""
        return self._target_temp_low

    @property
    def target_temperature_high(self):
        """Return the high target temperature we try to reach."""
        return self._target_temp_high

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return self._config[CONF_MODE_LIST]

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._config[CONF_TEMP_STEP]

    @property
    def is_away_mode_on(self):
        """Return if away mode is on."""
        return self._away

    @property
    def current_hold_mode(self):
        """Return hold mode setting."""
        return self._hold

    @property
    def is_aux_heat_on(self):
        """Return true if away mode is on."""
        return self._aux

    @property
    def current_fan_mode(self):
        """Return the fan setting."""
        return self._current_fan_mode

    @property
    def fan_list(self):
        """Return the list of available fan modes."""
        return self._config[CONF_FAN_MODE_LIST]

    def _publish(self, topic, payload):
        if self._topic[topic] is not None:
            mqtt.async_publish(
                self.opp, self._topic[topic], payload,
                self._config[CONF_QOS], self._config[CONF_RETAIN])

    def _set_temperature(self, temp, cmnd_topic, state_topic, attr):
        if temp is not None:
            if self._topic[state_topic] is None:
                # optimistic mode
                setattr(self, attr, temp)

            if (self._config[CONF_SEND_IF_OFF] or
                    self._current_operation != STATE_OFF):
                self._publish(cmnd_topic, temp)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_OPERATION_MODE) is not None:
            operation_mode = kwargs.get(ATTR_OPERATION_MODE)
            await self.async_set_operation_mode(operation_mode)

        self._set_temperature(
            kwargs.get(ATTR_TEMPERATURE), CONF_TEMP_COMMAND_TOPIC,
            CONF_TEMP_STATE_TOPIC, '_target_temp')

        self._set_temperature(
            kwargs.get(ATTR_TARGET_TEMP_LOW), CONF_TEMP_LOW_COMMAND_TOPIC,
            CONF_TEMP_LOW_STATE_TOPIC, '_target_temp_low')

        self._set_temperature(
            kwargs.get(ATTR_TARGET_TEMP_HIGH), CONF_TEMP_HIGH_COMMAND_TOPIC,
            CONF_TEMP_HIGH_STATE_TOPIC, '_target_temp_high')

        # Always optimistic?
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        if (self._config[CONF_SEND_IF_OFF] or
                self._current_operation != STATE_OFF):
            self._publish(CONF_SWING_MODE_COMMAND_TOPIC,
                          swing_mode)

        if self._topic[CONF_SWING_MODE_STATE_TOPIC] is None:
            self._current_swing_mode = swing_mode
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set new target temperature."""
        if (self._config[CONF_SEND_IF_OFF] or
                self._current_operation != STATE_OFF):
            self._publish(CONF_FAN_MODE_COMMAND_TOPIC,
                          fan_mode)

        if self._topic[CONF_FAN_MODE_STATE_TOPIC] is None:
            self._current_fan_mode = fan_mode
            self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode) -> None:
        """Set new operation mode."""
        if (self._current_operation == STATE_OFF and
                operation_mode != STATE_OFF):
            self._publish(CONF_POWER_COMMAND_TOPIC,
                          self._config[CONF_PAYLOAD_ON])
        elif (self._current_operation != STATE_OFF and
              operation_mode == STATE_OFF):
            self._publish(CONF_POWER_COMMAND_TOPIC,
                          self._config[CONF_PAYLOAD_OFF])

        self._publish(CONF_MODE_COMMAND_TOPIC,
                      operation_mode)

        if self._topic[CONF_MODE_STATE_TOPIC] is None:
            self._current_operation = operation_mode
            self.async_write_ha_state()

    @property
    def current_swing_mode(self):
        """Return the swing setting."""
        return self._current_swing_mode

    @property
    def swing_list(self):
        """List of available swing modes."""
        return self._config[CONF_SWING_MODE_LIST]

    def _set_away_mode(self, state):
        self._publish(CONF_AWAY_MODE_COMMAND_TOPIC,
                      self._config[CONF_PAYLOAD_ON] if state
                      else self._config[CONF_PAYLOAD_OFF])

        if self._topic[CONF_AWAY_MODE_STATE_TOPIC] is None:
            self._away = state
            self.async_write_ha_state()

    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        self._set_away_mode(True)

    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        self._set_away_mode(False)

    async def async_set_hold_mode(self, hold_mode):
        """Update hold mode on."""
        self._publish(CONF_HOLD_COMMAND_TOPIC, hold_mode)

        if self._topic[CONF_HOLD_STATE_TOPIC] is None:
            self._hold = hold_mode
            self.async_write_ha_state()

    def _set_aux_heat(self, state):
        self._publish(CONF_AUX_COMMAND_TOPIC,
                      self._config[CONF_PAYLOAD_ON] if state
                      else self._config[CONF_PAYLOAD_OFF])

        if self._topic[CONF_AUX_STATE_TOPIC] is None:
            self._aux = state
            self.async_write_ha_state()

    async def async_turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        self._set_aux_heat(True)

    async def async_turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        self._set_aux_heat(False)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        support = 0

        if (self._topic[CONF_TEMP_STATE_TOPIC] is not None) or \
           (self._topic[CONF_TEMP_COMMAND_TOPIC] is not None):
            support |= SUPPORT_TARGET_TEMPERATURE

        if (self._topic[CONF_TEMP_LOW_STATE_TOPIC] is not None) or \
           (self._topic[CONF_TEMP_LOW_COMMAND_TOPIC] is not None):
            support |= SUPPORT_TARGET_TEMPERATURE_LOW

        if (self._topic[CONF_TEMP_HIGH_STATE_TOPIC] is not None) or \
           (self._topic[CONF_TEMP_HIGH_COMMAND_TOPIC] is not None):
            support |= SUPPORT_TARGET_TEMPERATURE_HIGH

        if (self._topic[CONF_MODE_COMMAND_TOPIC] is not None) or \
           (self._topic[CONF_MODE_STATE_TOPIC] is not None):
            support |= SUPPORT_OPERATION_MODE

        if (self._topic[CONF_FAN_MODE_STATE_TOPIC] is not None) or \
           (self._topic[CONF_FAN_MODE_COMMAND_TOPIC] is not None):
            support |= SUPPORT_FAN_MODE

        if (self._topic[CONF_SWING_MODE_STATE_TOPIC] is not None) or \
           (self._topic[CONF_SWING_MODE_COMMAND_TOPIC] is not None):
            support |= SUPPORT_SWING_MODE

        if (self._topic[CONF_AWAY_MODE_STATE_TOPIC] is not None) or \
           (self._topic[CONF_AWAY_MODE_COMMAND_TOPIC] is not None):
            support |= SUPPORT_AWAY_MODE

        if (self._topic[CONF_HOLD_STATE_TOPIC] is not None) or \
           (self._topic[CONF_HOLD_COMMAND_TOPIC] is not None):
            support |= SUPPORT_HOLD_MODE

        if (self._topic[CONF_AUX_STATE_TOPIC] is not None) or \
           (self._topic[CONF_AUX_COMMAND_TOPIC] is not None):
            support |= SUPPORT_AUX_HEAT

        return support

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._config[CONF_TEMP_MIN]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._config[CONF_TEMP_MAX]
