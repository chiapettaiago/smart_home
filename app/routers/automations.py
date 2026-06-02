from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.action_service import ActionService
from app.services.automation_service import AutomationService
from app.services.device_service import DeviceService
from app.services.presence_service import PresenceService

blueprint = Blueprint("automations", __name__, url_prefix="/automations")
TRIGGERS = {"time", "device_status", "presence", "manual"}
DEVICE_STATES = {"on", "off", "online", "offline"}


def _validate_actions(db, actions):
    if not isinstance(actions, list) or not actions:
        return "Informe pelo menos uma acao"
    for item in actions:
        if not isinstance(item, dict):
            return "Cada acao deve ser um objeto"
        device = DeviceService.get_device(db, item.get("device_id"))
        if not device:
            return "Dispositivo da acao nao encontrado"
        action_name = item.get("action", "")
        if not isinstance(action_name, str):
            return "Nome da acao invalido"
        if not ActionService.is_action_available_for_device(device, action_name):
            return f"Acao '{action_name}' nao disponivel para o dispositivo '{device.name}'"
        available_action = next(
            action for action in ActionService.get_available_actions(device)
            if action["name"] == action_name
        )
        params = item.get("params") or {}
        if not isinstance(params, dict):
            return f"Parametros invalidos para a acao '{available_action['label']}'"
        for param in available_action.get("params", []):
            value = params.get(param["name"])
            if value is None or value == "":
                return f"Informe '{param['label']}' para a acao '{available_action['label']}'"
            if param["type"] == "select" and value not in param["options"]:
                return f"Valor invalido para '{param['label']}'"
            if param["type"] == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return f"Valor invalido para '{param['label']}'"
                if value < param.get("min", value) or value > param.get("max", value):
                    return f"Valor fora do intervalo para '{param['label']}'"
            if param["type"] == "color":
                if not isinstance(value, list) or len(value) != 3 or not all(
                    isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255
                    for channel in value
                ):
                    return f"Valor invalido para '{param['label']}'"
    return None


def _validate_condition(db, trigger, condition):
    if trigger not in TRIGGERS:
        return "Gatilho invalido"
    if not isinstance(condition, dict):
        return "Condicao invalida"
    if trigger == "manual":
        return None
    if trigger == "time":
        time_value = condition.get("time", "")
        if not isinstance(time_value, str) or len(time_value) != 5 or time_value[2] != ":":
            return "Informe um horario valido"
        try:
            hours, minutes = (int(value) for value in time_value.split(":"))
        except ValueError:
            return "Informe um horario valido"
        if hours not in range(24) or minutes not in range(60):
            return "Informe um horario valido"
        return None
    if trigger == "device_status":
        if not DeviceService.get_device(db, condition.get("device_id")):
            return "Dispositivo da condicao nao encontrado"
        if condition.get("state") not in DEVICE_STATES:
            return "Estado da condicao invalido"
        return None
    if trigger == "presence":
        users = {presence.user for presence in PresenceService.get_all_presence(db)}
        if condition.get("user") not in users:
            return "Usuario da condicao nao encontrado"
        if not isinstance(condition.get("is_home"), bool):
            return "Estado de presenca invalido"
    return None


@blueprint.get("")
def get_automations():
    db = get_db()
    try:
        return jsonify(
            serialize(
                AutomationService.get_automations(
                    db,
                    skip=request.args.get("skip", 0, type=int),
                    limit=request.args.get("limit", 100, type=int),
                )
            )
        )
    finally:
        db.close()


@blueprint.get("/action-catalog")
def get_action_catalog():
    db = get_db()
    try:
        devices = DeviceService.get_devices(db, limit=1000)
        presence_users = [presence.user for presence in PresenceService.get_all_presence(db)]
        return jsonify(
            {
                "devices": [
                    {
                        "id": device.id,
                        "name": device.name,
                        "type": device.type,
                        "entity_id": (device.device_metadata or {}).get("entity_id")
                        or (device.device_metadata or {}).get("external_id"),
                        "actions": ActionService.get_available_actions(device),
                    }
                    for device in devices
                ],
                "conditions": {
                    "device_states": [
                        {"value": "on", "label": "Ligado"},
                        {"value": "off", "label": "Desligado"},
                        {"value": "online", "label": "Online"},
                        {"value": "offline", "label": "Offline"},
                    ],
                    "presence_users": presence_users,
                },
            }
        )
    finally:
        db.close()


@blueprint.post("")
def create_automation():
    token_error = verify_token()
    if token_error:
        return token_error
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("trigger") or not payload.get("actions"):
        return error("Informe name, trigger e actions", 422)
    db = get_db()
    try:
        condition_error = _validate_condition(db, payload["trigger"], payload.get("condition") or {})
        if condition_error:
            return error(condition_error, 422)
        action_error = _validate_actions(db, payload["actions"])
        if action_error:
            return error(action_error, 422)
        return jsonify(serialize(AutomationService.create_automation(db, payload)))
    finally:
        db.close()


@blueprint.get("/active/list")
def get_active_automations():
    db = get_db()
    try:
        automations = AutomationService.get_active_automations(db)
        return jsonify(serialize({"count": len(automations), "automations": automations}))
    finally:
        db.close()


@blueprint.get("/<int:automation_id>")
def get_automation(automation_id):
    db = get_db()
    try:
        automation = AutomationService.get_automation(db, automation_id)
        return jsonify(serialize(automation)) if automation else error("Automacao nao encontrada", 404)
    finally:
        db.close()


@blueprint.put("/<int:automation_id>")
def update_automation(automation_id):
    token_error = verify_token()
    if token_error:
        return token_error
    payload = request.get_json(silent=True) or {}
    db = get_db()
    try:
        if "trigger" in payload or "condition" in payload:
            automation = AutomationService.get_automation(db, automation_id)
            if not automation:
                return error("Automacao nao encontrada", 404)
            condition_error = _validate_condition(
                db,
                payload.get("trigger", automation.trigger),
                payload.get("condition", automation.condition) or {},
            )
            if condition_error:
                return error(condition_error, 422)
        if "actions" in payload:
            action_error = _validate_actions(db, payload["actions"])
            if action_error:
                return error(action_error, 422)
        automation = AutomationService.update_automation(db, automation_id, payload)
        return jsonify(serialize(automation)) if automation else error("Automacao nao encontrada", 404)
    finally:
        db.close()


@blueprint.delete("/<int:automation_id>")
def delete_automation(automation_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        if not AutomationService.delete_automation(db, automation_id):
            return error("Automacao nao encontrada", 404)
        return jsonify({"message": "Automacao deletada com sucesso"})
    finally:
        db.close()


@blueprint.get("/<int:automation_id>/logs")
def get_automation_logs(automation_id):
    db = get_db()
    try:
        if not AutomationService.get_automation(db, automation_id):
            return error("Automacao nao encontrada", 404)
        logs = AutomationService.get_execution_logs(
            db,
            automation_id=automation_id,
            limit=request.args.get("limit", 50, type=int),
        )
        return jsonify(serialize({"automation_id": automation_id, "logs": logs}))
    finally:
        db.close()
