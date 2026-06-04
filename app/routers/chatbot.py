"""Chatbot residencial com interpretação de comandos via Gemini."""

import logging
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.integrations.gemini import GeminiIntegration
from app.routers.automations import _prepare_automation_payload, _validate_actions, _validate_condition, _validate_conditions
from app.routers.common import error, get_db, verify_token
from app.services.action_service import ActionService
from app.services.automation_learning_service import AutomationLearningService
from app.services.automation_service import AutomationService
from app.services.device_service import DeviceService
from app.services.environment_service import EnvironmentService
from app.services.presence_service import PresenceService

blueprint = Blueprint("chatbot", __name__, url_prefix="/chatbot")
logger = logging.getLogger(__name__)

AUTOMATION_CREATION_PATTERN = re.compile(
    r"\b(cri(e|ar|a)|salv(e|ar|a)|ativ(e|ar|a)|aceit(o|ar|a)|automatiz(e|ar|a)|gere|gerar)\b",
    re.IGNORECASE,
)


def _device_catalog(devices):
    return [
        {
            "id": device.id,
            "name": device.name,
            "room": device.room,
            "type": device.type,
            "entity_id": (device.device_metadata or {}).get("entity_id")
            or (device.device_metadata or {}).get("external_id"),
            "actions": ActionService.get_available_actions(device),
        }
        for device in devices
    ]


def _automation_context(db, devices):
    return {
        "triggers": ["time", "device_status", "presence", "sun", "weather", "calendar", "manual"],
        "condition_modes": ["all", "any"],
        "device_states": ["on", "off", "online", "offline", "playing", "paused", "idle", "buffering"],
        "presence_users": [presence.user for presence in PresenceService.get_all_presence(db)],
        "weather_fields": [
            "temperature",
            "apparent_temperature",
            "humidity",
            "precipitation_probability",
            "precipitation",
            "rain",
            "wind_speed",
            "cloud_cover",
            "is_raining",
        ],
        "weather_operators": ["gte", "gt", "lte", "lt", "eq", "neq"],
        "calendar_modes": ["day_type", "weekday", "date", "month_day"],
        "environment": EnvironmentService.get_context(),
        "learned_suggestions": AutomationLearningService.get_suggestions(db, limit=5),
        "existing_automations": [
            {
                "id": automation.id,
                "name": automation.name,
                "trigger": automation.trigger,
                "condition": automation.condition,
                "actions": automation.actions,
                "active": automation.active,
            }
            for automation in AutomationService.get_automations(db, limit=100)
        ],
        "devices": _device_catalog(devices),
    }


def _update_power_state(db, device, action):
    if device.type != "tuya":
        return
    metadata = dict(device.device_metadata or {})
    current_state = metadata.get("power_state") or metadata.get("ha_state")
    next_state = None
    if action == "turn_on":
        next_state = "on"
    elif action == "turn_off":
        next_state = "off"
    elif action == "toggle" and current_state in {"on", "off"}:
        next_state = "off" if current_state == "on" else "on"
    if next_state:
        metadata["power_state"] = next_state
        metadata["pending_power_state"] = next_state
        metadata["pending_power_state_until"] = (datetime.utcnow() + timedelta(seconds=12)).isoformat()
        DeviceService.update_device(db, device.id, {"device_metadata": metadata})


def _execute_command(db, command):
    device = DeviceService.get_device(db, command.get("device_id"))
    if not device:
        return {"success": False, "message": "O Gemini indicou um dispositivo que não existe."}

    action = command.get("action", "")
    params = command.get("params") or {}
    validation_error = ActionService.validate_action_params(device, action, params)
    if validation_error:
        return {"success": False, "device_name": device.name, "action": action, "message": validation_error}

    result = ActionService.execute_action(device, action, params)
    if result.get("success"):
        _update_power_state(db, device, action)
    try:
        ActionService.log_action(
            db,
            device_id=device.id,
            action=action,
            params=params or None,
            status="success" if result.get("success") else "failed",
            response=result.get("data"),
        )
    except Exception:
        db.rollback()
        logger.exception("Falha ao registrar ação do chatbot para o dispositivo %s", device.id)
    return {
        "success": bool(result.get("success")),
        "device_id": device.id,
        "device_name": device.name,
        "action": action,
        "message": result.get("message") or "Comando processado.",
    }


def _create_automation_from_ai(db, automation_data):
    if not isinstance(automation_data, dict):
        return {"success": False, "message": "Automação sugerida em formato inválido."}
    required = {"name", "trigger", "condition", "actions"}
    if not required.issubset(automation_data):
        return {"success": False, "message": "Automação sugerida sem campos obrigatórios."}
    condition_error = _validate_condition(db, automation_data["trigger"], automation_data.get("condition") or {})
    if condition_error:
        return {"success": False, "name": automation_data.get("name"), "message": condition_error}
    conditions_error = _validate_conditions(db, automation_data.get("conditions"))
    if conditions_error:
        return {"success": False, "name": automation_data.get("name"), "message": conditions_error}
    action_error = _validate_actions(db, automation_data.get("actions"))
    if action_error:
        return {"success": False, "name": automation_data.get("name"), "message": action_error}
    payload = _prepare_automation_payload(
        {
            "name": str(automation_data["name"])[:255],
            "trigger": automation_data["trigger"],
            "condition": automation_data.get("condition") or {},
            "conditions": automation_data.get("conditions"),
            "actions": automation_data.get("actions"),
            "active": bool(automation_data.get("active", True)),
        }
    )
    automation = AutomationService.create_automation(db, payload)
    return {
        "success": True,
        "automation_id": automation.id,
        "name": automation.name,
        "message": f"Automação '{automation.name}' criada.",
    }


def _allows_automation_creation(message: str) -> bool:
    return bool(AUTOMATION_CREATION_PATTERN.search(message or ""))


@blueprint.get("/status")
def get_chatbot_status():
    return jsonify({"configured": bool(GEMINI_API_KEY), "model": GEMINI_MODEL})


@blueprint.get("/automation-suggestions")
def get_automation_suggestions():
    db = get_db()
    try:
        return jsonify({"suggestions": AutomationLearningService.get_suggestions(db, limit=10)})
    finally:
        db.close()


@blueprint.post("/message")
def send_chatbot_message():
    token_error = verify_token()
    if token_error:
        return token_error

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not message:
        return error("Digite uma mensagem para o assistente.", 422)
    if len(message) > 1000:
        return error("A mensagem deve ter no máximo 1000 caracteres.", 422)
    if not isinstance(history, list):
        return error("Histórico de conversa inválido.", 422)

    db = get_db()
    try:
        devices = DeviceService.get_devices(db, limit=1000)
        interpretation = GeminiIntegration().interpret_command(
            message,
            _device_catalog(devices),
            history,
            automation_context=_automation_context(db, devices),
        )
        if not interpretation.get("success"):
            return error(interpretation.get("message", "Não foi possível consultar o Gemini."), 502)

        results = [_execute_command(db, command) for command in interpretation.get("commands", [])]
        requested_automations = interpretation.get("automations", [])
        can_create_automations = _allows_automation_creation(message)
        automation_results = [
            _create_automation_from_ai(db, automation)
            for automation in requested_automations
            if can_create_automations
        ]
        failed = [result for result in results if not result.get("success")]
        failed.extend(result for result in automation_results if not result.get("success"))
        reply = interpretation.get("reply") or "Pedido processado."
        if requested_automations and not can_create_automations:
            reply = f"{reply}\n\nEu identifiquei uma automação possível, mas não criei nada porque o pedido não foi explícito."
        if results:
            summary = "; ".join(
                f"{result.get('device_name', 'Dispositivo')}: {result['message']}"
                for result in results
            )
            reply = f"{reply}\n\nResultado: {summary}"
        if automation_results:
            summary = "; ".join(result["message"] for result in automation_results)
            reply = f"{reply}\n\nAutomações: {summary}"
        return jsonify({"reply": reply, "commands": results, "automations": automation_results, "success": not failed})
    finally:
        db.close()
