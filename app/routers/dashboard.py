from datetime import datetime

from flask import Blueprint, jsonify

from app.routers.common import get_db, serialize
from app.services.action_service import ActionService
from app.services.automation_service import AutomationService
from app.services.device_service import DeviceService
from app.services.energy_service import EnergyService
from app.services.presence_service import PresenceService
from app.integrations.home_assistant import HomeAssistantIntegration
from app.services.environment_service import EnvironmentService
from app.services.roku_status_service import RokuStatusService
from app.services.room_service import RoomService

blueprint = Blueprint("dashboard", __name__)

UNAVAILABLE_STATES = {"unavailable", "unknown"}


def _get_entity_domain(metadata):
    entity_id = metadata.get("entity_id") or metadata.get("external_id") or ""
    return entity_id.split(".", 1)[0] if "." in entity_id else ""


def _resolve_power_state(metadata, live_state):
    """Mantém o estado solicitado brevemente enquanto o HA converge."""
    pending_state = metadata.get("pending_power_state")
    pending_until = metadata.get("pending_power_state_until")
    if pending_state not in {"on", "off"} or pending_state == live_state or not pending_until:
        return live_state
    try:
        if datetime.fromisoformat(pending_until) > datetime.utcnow():
            return pending_state
    except ValueError:
        pass
    return live_state


def _get_home_assistant_config(devices):
    for device in devices:
        metadata = device.device_metadata or {}
        if metadata.get("ha_token") or metadata.get("ha_url"):
            return {
                "ha_url": metadata.get("ha_url"),
                "ha_token": metadata.get("ha_token"),
            }
    return {}


def _get_live_device_data(devices):
    """Lê disponibilidade e energia mantendo os dois conceitos separados."""
    live_data = {}
    integrations = {}
    ha_config = _get_home_assistant_config(devices)

    for device in devices:
        if device.type == "roku" and device.ip:
            status = RokuStatusService.get_status(device, ha_config=ha_config)
            live_data[device.id] = {
                "status": "online" if status.get("online") else "offline",
                "power_state": "on" if status.get("powered_on") else "off",
                "playback_state": status.get("playback_state"),
                "now_playing": status.get("now_playing"),
            }
            continue
        if device.type != "tuya":
            continue
        metadata = device.device_metadata or {}
        stored_state = metadata.get("power_state") or metadata.get("ha_state")
        live_data[device.id] = {
            "status": device.status,
            "power_state": stored_state if stored_state in {"on", "off"} else None,
            "ha_state": metadata.get("ha_state"),
            "brightness": metadata.get("brightness"),
            "rgb_color": metadata.get("rgb_color"),
        }
        if metadata.get("source") != "home_assistant":
            continue
        entity_id = metadata.get("entity_id") or metadata.get("external_id")
        if not entity_id:
            continue
        config = (metadata.get("ha_url") or "", metadata.get("ha_token") or "")
        integrations.setdefault(config, []).append((device.id, entity_id, metadata))

    for (ha_url, ha_token), configured_devices in integrations.items():
        integration = HomeAssistantIntegration(base_url=ha_url or None, token=ha_token)
        result = integration.get_states([entity_id for _, entity_id, _ in configured_devices])
        if not result.get("success"):
            continue
        states = result.get("states", {})
        for device_id, entity_id, metadata in configured_devices:
            entity = states.get(entity_id)
            if not entity:
                continue
            state = entity.get("state")
            attributes = entity.get("attributes") or {}
            live_power_state = state if state in {"on", "off"} else None
            live_data[device_id] = {
                "status": "offline" if state in UNAVAILABLE_STATES else "online",
                "power_state": _resolve_power_state(metadata, live_power_state),
                "ha_state": state,
                "brightness": attributes.get("brightness"),
                "rgb_color": attributes.get("rgb_color"),
            }

    return live_data


def _format_action_label(action_name, params):
    action_name = (action_name or "").lower()
    if action_name == "turn_on":
        return "Ligou dispositivo"
    if action_name == "turn_off":
        return "Desligou dispositivo"
    if action_name == "restart":
        return "Reiniciou dispositivo"
    if action_name == "lock":
        return "Bloqueou dispositivo"
    if action_name == "unlock":
        return "Desbloqueou dispositivo"
    if action_name == "open_app":
        app_name = (params or {}).get("app_name")
        return f"Abriu app {app_name}" if app_name else "Abriu aplicativo"
    if action_name == "close_app":
        return "Fechou app / voltou para Home"
    if action_name == "play":
        return "Reproduziu mídia"
    if action_name == "pause":
        return "Pausou mídia"
    if action_name == "get_status":
        return "Consultou status"
    if action_name == "toggle":
        return "Alternou estado do dispositivo"
    if action_name == "set_brightness":
        return "Ajustou brilho"
    if action_name == "set_color_temp":
        return "Ajustou temperatura de cor"
    if action_name == "set_hs_color":
        return "Ajustou cor (HS)"
    if action_name == "set_rgb_color":
        return "Ajustou cor (RGB)"
    if action_name == "set_percentage":
        return "Ajustou percentual"
    if action_name == "set_temperature":
        return "Ajustou temperatura"
    if action_name == "set_hvac_mode":
        return "Alterou modo HVAC"
    if action_name == "set_preset_mode":
        return "Alterou preset"
    if action_name == "set_fan_mode":
        return "Alterou modo do ventilador"
    if action_name == "set_swing_mode":
        return "Alterou oscilação"
    if action_name == "tuya_command":
        return "Executou comando Tuya personalizado"
    return action_name or "Ação executada"


@blueprint.get("/api/dashboard/data")
def get_dashboard_data():
    db = get_db()
    try:
        devices = DeviceService.get_devices(db, limit=1000)
        live_device_data = _get_live_device_data(devices)
        online_count = sum(
            1
            for device in devices
            if live_device_data.get(device.id, {}).get("status", device.status) == "online"
        )
        energy_stats = EnergyService.get_total_consumption(db, hours=24)
        recent_actions = ActionService.get_recent_actions(db, limit=10)
        PresenceService.refresh_from_vivo_router(db)
        presence_list = PresenceService.get_all_presence(db)
        automations = AutomationService.get_automations(db)
        active_automations = AutomationService.get_active_automations(db)

        return jsonify(
            serialize(
                {
                    "devices": {
                        "total": len(devices),
                        "online": online_count,
                        "offline": len(devices) - online_count,
                        "list": [
                            {
                                "id": device.id,
                                "name": device.name,
                                "type": device.type,
                                "room": device.room,
                                "ip": device.ip,
                                "status": live_device_data.get(device.id, {}).get("status", device.status),
                                "power_state": live_device_data.get(device.id, {}).get("power_state"),
                                "ha_state": live_device_data.get(device.id, {}).get("ha_state"),
                                "entity_domain": _get_entity_domain(device.device_metadata or {}),
                                "brightness": live_device_data.get(device.id, {}).get("brightness"),
                                "rgb_color": live_device_data.get(device.id, {}).get("rgb_color"),
                                "playback_state": live_device_data.get(device.id, {}).get("playback_state"),
                                "updated_at": device.updated_at,
                                "now_playing": (
                                    live_device_data.get(device.id, {}).get("now_playing")
                                ),
                            }
                            for device in devices
                        ],
                    },
                    "rooms": RoomService.get_rooms(db),
                    "energy": {
                        **energy_stats,
                        "by_device": EnergyService.get_consumption_by_device(db, hours=24),
                    },
                    "actions": {
                        "recent": [
                            {
                                "id": action.id,
                                "device_id": action.device_id,
                                "device_name": action.device.name if action.device else f"Dispositivo {action.device_id}",
                                "action": action.action,
                                "action_label": _format_action_label(action.action, action.params),
                                "params": action.params,
                                "status": action.status,
                                "executed_at": action.executed_at,
                            }
                            for action in recent_actions
                        ]
                    },
                    "presence": {
                        "users": {presence.user: presence.is_home for presence in presence_list},
                        "anyone_home": any(presence.is_home for presence in presence_list),
                    },
                    "automations": {
                        "total": len(automations),
                        "active": len(active_automations),
                        "inactive": len(automations) - len(active_automations),
                        "automations": automations,
                    },
                    "environment": EnvironmentService.get_context(),
                }
            )
        )
    finally:
        db.close()
