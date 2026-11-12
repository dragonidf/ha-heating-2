"""Versioned native HA WebSocket API; UI cannot issue an authority witness."""
import probatio
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.decorators import websocket_command, async_response
from .const import DOMAIN


def register(hass):
    @websocket_command({
        'type': 'heating_ai_v2/backend', probatio.Required('entry_id'): str,
        probatio.Required('version'): [int], probatio.Required('operation'): str,
        probatio.Optional('payload', default={}): dict,
    })
    @async_response
    async def handle(hass, connection, msg):
        if connection.user is None:
            connection.send_error(msg['id'], 'unauthorized', 'HA authentication required')
            return
        runtime = hass.data.get(DOMAIN, {}).get(msg['entry_id'])
        if msg['version'] != [2, 0] or runtime is None or not getattr(runtime, 'native', None):
            connection.send_error(msg['id'], 'unavailable', 'Native backend/version unavailable')
            return
        try:
            result = await runtime.native.dispatch(msg['operation'], msg['payload'], connection.user.is_admin)
            runtime.refresh()
            connection.send_result(msg['id'], result)
        except PermissionError:
            connection.send_error(msg['id'], 'forbidden', 'Administrator required')
        except Exception:
            connection.send_error(msg['id'], 'failed_closed', 'Native operation unavailable; no device command')
    websocket_api.async_register_command(hass, handle)
