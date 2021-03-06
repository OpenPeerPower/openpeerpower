"""The tests for the Script component."""
# pylint: disable=protected-access
import unittest
from unittest.mock import Mock, patch

import pytest

from openpeerpower.components import script
from openpeerpower.components.script import DOMAIN
from openpeerpower.const import (
    ATTR_ENTITY_ID,
    ATTR_NAME,
    EVENT_SCRIPT_STARTED,
    SERVICE_RELOAD,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from openpeerpower.core import Context, callback, split_entity_id
from openpeerpower.exceptions import ServiceNotFound
from openpeerpower.helpers.service import async_get_all_descriptions
from openpeerpower.loader import bind_opp
from openpeerpower.setup import async_setup_component, setup_component

from tests.common import get_test_open_peer_power

ENTITY_ID = "script.test"


@bind_opp
def turn_on(opp, entity_id, variables=None, context=None):
    """Turn script on.

    This is a legacy helper method. Do not use it for new tests.
    """
    _, object_id = split_entity_id(entity_id)

    opp.services.call(DOMAIN, object_id, variables, context=context)


@bind_opp
def turn_off(opp, entity_id):
    """Turn script on.

    This is a legacy helper method. Do not use it for new tests.
    """
    opp.services.call(DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id})


@bind_opp
def toggle(opp, entity_id):
    """Toggle the script.

    This is a legacy helper method. Do not use it for new tests.
    """
    opp.services.call(DOMAIN, SERVICE_TOGGLE, {ATTR_ENTITY_ID: entity_id})


@bind_opp
def reload(opp):
    """Reload script component.

    This is a legacy helper method. Do not use it for new tests.
    """
    opp.services.call(DOMAIN, SERVICE_RELOAD)


class TestScriptComponent(unittest.TestCase):
    """Test the Script component."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up things to be run when tests are started."""
        self.opp = get_test_open_peer_power()

    # pylint: disable=invalid-name
    def tearDown(self):
        """Stop down everything that was started."""
        self.opp.stop()

    def test_setup_with_invalid_configs(self):
        """Test setup with invalid configs."""
        for value in (
            {"test": {}},
            {"test hello world": {"sequence": [{"event": "bla"}]}},
            {
                "test": {
                    "sequence": {
                        "event": "test_event",
                        "service": "openpeerpower.turn_on",
                    }
                }
            },
        ):
            assert not setup_component(
                self.opp, "script", {"script": value}
            ), "Script loaded with wrong config {}".format(value)

            assert 0 == len(self.opp.states.entity_ids("script"))

    def test_turn_on_service(self):
        """Verify that the turn_on service."""
        event = "test_event"
        events = []

        @callback
        def record_event(event):
            """Add recorded event to set."""
            events.append(event)

        self.opp.bus.listen(event, record_event)

        assert setup_component(
            self.opp,
            "script",
            {
                "script": {
                    "test": {"sequence": [{"delay": {"seconds": 5}}, {"event": event}]}
                }
            },
        )

        turn_on(self.opp, ENTITY_ID)
        self.opp.block_till_done()
        assert script.is_on(self.opp, ENTITY_ID)
        assert 0 == len(events)

        # Calling turn_on a second time should not advance the script
        turn_on(self.opp, ENTITY_ID)
        self.opp.block_till_done()
        assert 0 == len(events)

        turn_off(self.opp, ENTITY_ID)
        self.opp.block_till_done()
        assert not script.is_on(self.opp, ENTITY_ID)
        assert 0 == len(events)

    def test_toggle_service(self):
        """Test the toggling of a service."""
        event = "test_event"
        events = []

        @callback
        def record_event(event):
            """Add recorded event to set."""
            events.append(event)

        self.opp.bus.listen(event, record_event)

        assert setup_component(
            self.opp,
            "script",
            {
                "script": {
                    "test": {"sequence": [{"delay": {"seconds": 5}}, {"event": event}]}
                }
            },
        )

        toggle(self.opp, ENTITY_ID)
        self.opp.block_till_done()
        assert script.is_on(self.opp, ENTITY_ID)
        assert 0 == len(events)

        toggle(self.opp, ENTITY_ID)
        self.opp.block_till_done()
        assert not script.is_on(self.opp, ENTITY_ID)
        assert 0 == len(events)

    def test_passing_variables(self):
        """Test different ways of passing in variables."""
        calls = []
        context = Context()

        @callback
        def record_call(service):
            """Add recorded event to set."""
            calls.append(service)

        self.opp.services.register("test", "script", record_call)

        assert setup_component(
            self.opp,
            "script",
            {
                "script": {
                    "test": {
                        "sequence": {
                            "service": "test.script",
                            "data_template": {"hello": "{{ greeting }}"},
                        }
                    }
                }
            },
        )

        turn_on(self.opp, ENTITY_ID, {"greeting": "world"}, context=context)

        self.opp.block_till_done()

        assert len(calls) == 1
        assert calls[0].context is context
        assert calls[0].data["hello"] == "world"

        self.opp.services.call(
            "script", "test", {"greeting": "universe"}, context=context
        )

        self.opp.block_till_done()

        assert len(calls) == 2
        assert calls[1].context is context
        assert calls[1].data["hello"] == "universe"

    def test_reload_service(self):
        """Verify that the turn_on service."""
        assert setup_component(
            self.opp,
            "script",
            {"script": {"test": {"sequence": [{"delay": {"seconds": 5}}]}}},
        )

        assert self.opp.states.get(ENTITY_ID) is not None
        assert self.opp.services.has_service(script.DOMAIN, "test")

        with patch(
            "openpeerpower.config.load_yaml_config_file",
            return_value={
                "script": {"test2": {"sequence": [{"delay": {"seconds": 5}}]}}
            },
        ):
            reload(self.opp)
            self.opp.block_till_done()

        assert self.opp.states.get(ENTITY_ID) is None
        assert not self.opp.services.has_service(script.DOMAIN, "test")

        assert self.opp.states.get("script.test2") is not None
        assert self.opp.services.has_service(script.DOMAIN, "test2")


async def test_service_descriptions(opp):
    """Test that service descriptions are loaded and reloaded correctly."""
    # Test 1: has "description" but no "fields"
    assert await async_setup_component(
        opp,
        "script",
        {
            "script": {
                "test": {
                    "description": "test description",
                    "sequence": [{"delay": {"seconds": 5}}],
                }
            }
        },
    )

    descriptions = await async_get_all_descriptions(opp)

    assert descriptions[DOMAIN]["test"]["description"] == "test description"
    assert not descriptions[DOMAIN]["test"]["fields"]

    # Test 2: has "fields" but no "description"
    with patch(
        "openpeerpower.config.load_yaml_config_file",
        return_value={
            "script": {
                "test": {
                    "fields": {
                        "test_param": {
                            "description": "test_param description",
                            "example": "test_param example",
                        }
                    },
                    "sequence": [{"delay": {"seconds": 5}}],
                }
            }
        },
    ):
        await opp.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)

    descriptions = await async_get_all_descriptions(opp)

    assert descriptions[script.DOMAIN]["test"]["description"] == ""
    assert (
        descriptions[script.DOMAIN]["test"]["fields"]["test_param"]["description"]
        == "test_param description"
    )
    assert (
        descriptions[script.DOMAIN]["test"]["fields"]["test_param"]["example"]
        == "test_param example"
    )


async def test_shared_context(opp):
    """Test that the shared context is passed down the chain."""
    event = "test_event"
    context = Context()

    event_mock = Mock()
    run_mock = Mock()

    opp.bus.async_listen(event, event_mock)
    opp.bus.async_listen(EVENT_SCRIPT_STARTED, run_mock)

    assert await async_setup_component(
        opp, "script", {"script": {"test": {"sequence": [{"event": event}]}}}
    )

    await opp.services.async_call(
        DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, context=context
    )
    await opp.async_block_till_done()

    assert event_mock.call_count == 1
    assert run_mock.call_count == 1

    args, kwargs = run_mock.call_args
    assert args[0].context == context
    # Ensure event data has all attributes set
    assert args[0].data.get(ATTR_NAME) == "test"
    assert args[0].data.get(ATTR_ENTITY_ID) == "script.test"

    # Ensure context carries through the event
    args, kwargs = event_mock.call_args
    assert args[0].context == context

    # Ensure the script state shares the same context
    state = opp.states.get("script.test")
    assert state is not None
    assert state.context == context


async def test_logging_script_error(opp, caplog):
    """Test logging script error."""
    assert await async_setup_component(
        opp,
        "script",
        {"script": {"hello": {"sequence": [{"service": "non.existing"}]}}},
    )
    with pytest.raises(ServiceNotFound) as err:
        await opp.services.async_call("script", "hello", blocking=True)

    assert err.value.domain == "non"
    assert err.value.service == "existing"
    assert "Error executing script" in caplog.text


async def test_turning_no_scripts_off(opp):
    """Test it is possible to turn two scripts off."""
    assert await async_setup_component(opp, "script", {})

    # Testing it doesn't raise
    await opp.services.async_call(
        DOMAIN, SERVICE_TURN_OFF, {"entity_id": []}, blocking=True
    )


async def test_async_get_descriptions_script(opp):
    """Test async_set_service_schema for the script integration."""
    script_config = {
        DOMAIN: {
            "test1": {"sequence": [{"service": "openpeerpower.restart"}]},
            "test2": {
                "description": "test2",
                "fields": {
                    "param": {
                        "description": "param_description",
                        "example": "param_example",
                    }
                },
                "sequence": [{"service": "openpeerpower.restart"}],
            },
        }
    }

    await async_setup_component(opp, DOMAIN, script_config)
    descriptions = await opp.helpers.service.async_get_all_descriptions()

    assert descriptions[DOMAIN]["test1"]["description"] == ""
    assert not descriptions[DOMAIN]["test1"]["fields"]

    assert descriptions[DOMAIN]["test2"]["description"] == "test2"
    assert (
        descriptions[DOMAIN]["test2"]["fields"]["param"]["description"]
        == "param_description"
    )
    assert (
        descriptions[DOMAIN]["test2"]["fields"]["param"]["example"] == "param_example"
    )


async def test_extraction_functions(opp):
    """Test extraction functions."""
    assert await async_setup_component(
        opp,
        DOMAIN,
        {
            DOMAIN: {
                "test1": {
                    "sequence": [
                        {
                            "service": "test.script",
                            "data": {"entity_id": "light.in_both"},
                        },
                        {
                            "service": "test.script",
                            "data": {"entity_id": "light.in_first"},
                        },
                        {"domain": "light", "device_id": "device-in-both"},
                    ]
                },
                "test2": {
                    "sequence": [
                        {
                            "service": "test.script",
                            "data": {"entity_id": "light.in_both"},
                        },
                        {
                            "condition": "state",
                            "entity_id": "sensor.condition",
                            "state": "100",
                        },
                        {"scene": "scene.hello"},
                        {"domain": "light", "device_id": "device-in-both"},
                        {"domain": "light", "device_id": "device-in-last"},
                    ],
                },
            }
        },
    )

    assert set(script.scripts_with_entity(opp, "light.in_both")) == {
        "script.test1",
        "script.test2",
    }
    assert set(script.entities_in_script(opp, "script.test1")) == {
        "light.in_both",
        "light.in_first",
    }
    assert set(script.scripts_with_device(opp, "device-in-both")) == {
        "script.test1",
        "script.test2",
    }
    assert set(script.devices_in_script(opp, "script.test2")) == {
        "device-in-both",
        "device-in-last",
    }


async def test_config(opp):
    """Test passing info in config."""
    assert await async_setup_component(
        opp,
        "script",
        {
            "script": {
                "test_script": {
                    "alias": "Script Name",
                    "icon": "mdi:party",
                    "sequence": [],
                }
            }
        },
    )

    test_script = opp.states.get("script.test_script")
    assert test_script.name == "Script Name"
    assert test_script.attributes["icon"] == "mdi:party"
