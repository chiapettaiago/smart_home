"""Chatbot residencial com interpretação de comandos via Gemini."""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.integrations.gemini import GeminiIntegration
from app.routers.common import error, get_db, verify_token
from app.services.action_service import ActionService
from app.services.device_service import DeviceService

blueprint = Blueprint("chatbot", __name__, url_prefix="/chatbot")
logger = logging.getLogger(__name__)


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


@blueprint.get("/status")
def get_chatbot_status():
    return jsonify({"configured": bool(GEMINI_API_KEY), "model": GEMINI_MODEL})


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
        interpretation = GeminiIntegration().interpret_command(message, _device_catalog(devices), history)
        if not interpretation.get("success"):
            return error(interpretation.get("message", "Não foi possível consultar o Gemini."), 502)

        results = [_execute_command(db, command) for command in interpretation.get("commands", [])]
        failed = [result for result in results if not result.get("success")]
        reply = interpretation.get("reply") or "Pedido processado."
        if results:
            summary = "; ".join(
                f"{result.get('device_name', 'Dispositivo')}: {result['message']}"
                for result in results
            )
            reply = f"{reply}\n\nResultado: {summary}"
        return jsonify({"reply": reply, "commands": results, "success": not failed})
    finally:
        db.close()
