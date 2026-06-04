from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.action_service import ActionService
from app.services.automation_service import AutomationService
from app.services.device_service import DeviceService
from app.services.environment_service import EnvironmentService
from app.services.presence_service import PresenceService

blueprint = Blueprint("automations", __name__, url_prefix="/automations")
TRIGGERS = {"time", "device_status", "presence", "manual", "sun", "weather", "calendar"}
DEVICE_STATES = {"on", "off", "online", "offline"}
WEATHER_FIELDS = {"temperature", "apparent_temperature", "humidity", "precipitation", "rain", "precipitation_probability", "wind_speed", "cloud_cover", "is_raining"}
WEATHER_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "neq"}
SUN_EVENTS = {"sunrise", "sunset"}
CALENDAR_MODES = {"day_type", "weekday", "date", "month_day"}


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
    if trigger == "sun":
        if condition.get("event") not in SUN_EVENTS:
            return "Evento solar invalido"
        offset = condition.get("offset_minutes", 0)
        if not isinstance(offset, int) or offset < -240 or offset > 240:
            return "Offset solar invalido"
        return None
    if trigger == "weather":
        field = condition.get("field")
        if field not in WEATHER_FIELDS:
            return "Campo de clima invalido"
        if field == "is_raining":
            if not isinstance(condition.get("is_raining"), bool):
                return "Estado de chuva invalido"
            return None
        if condition.get("operator") not in WEATHER_OPERATORS:
            return "Operador de clima invalido"
        if not isinstance(condition.get("value"), (int, float)) or isinstance(condition.get("value"), bool):
            return "Valor de clima invalido"
        return None
    if trigger == "calendar":
        mode = condition.get("mode")
        if mode not in CALENDAR_MODES:
            return "Modo de calendario invalido"
        if mode == "day_type" and condition.get("day_type") not in {"weekday", "weekend"}:
            return "Tipo de dia invalido"
        if mode == "weekday" and condition.get("weekday") not in range(7):
            return "Dia da semana invalido"
        if mode == "date":
            date_value = condition.get("date", "")
            if not isinstance(date_value, str) or len(date_value) != 10:
                return "Data invalida"
        if mode == "month_day":
            if condition.get("month") not in range(1, 13) or condition.get("day") not in range(1, 32):
                return "Dia do mes invalido"
    return None


def _validate_conditions(db, conditions_payload):
    if conditions_payload is None:
        return None
    if not isinstance(conditions_payload, dict):
        return "Condicoes adicionais invalidas"
    mode = conditions_payload.get("mode", "all")
    if mode not in {"all", "any"}:
        return "Modo das condicoes adicionais invalido"
    items = conditions_payload.get("items") or []
    if not isinstance(items, list):
        return "Lista de condicoes adicionais invalida"
    for item in items:
        if not isinstance(item, dict):
            return "Cada condicao adicional deve ser um objeto"
        condition_type = item.get("type")
        condition_error = _validate_condition(db, condition_type, item.get("condition") or {})
        if condition_error:
            return condition_error
    return None


def _prepare_automation_payload(payload):
    prepared = dict(payload)
    additional = prepared.pop("conditions", None)
    if additional is not None:
        condition = prepared.get("condition") or {}
        condition["_conditions"] = additional
        prepared["condition"] = condition
    return prepared


def _primary_condition(condition):
    primary = dict(condition or {})
    primary.pop("_conditions", None)
    return primary


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
        environment = EnvironmentService.get_context()
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
                    "weather_fields": [
                        {"value": "temperature", "label": "Temperatura"},
                        {"value": "apparent_temperature", "label": "Sensação térmica"},
                        {"value": "humidity", "label": "Umidade"},
                        {"value": "precipitation_probability", "label": "Probabilidade de chuva"},
                        {"value": "precipitation", "label": "Precipitação"},
                        {"value": "rain", "label": "Chuva"},
                        {"value": "wind_speed", "label": "Vento"},
                        {"value": "cloud_cover", "label": "Nuvens"},
                        {"value": "is_raining", "label": "Está chovendo"},
                    ],
                    "weather_operators": [
                        {"value": "gte", "label": "maior ou igual"},
                        {"value": "gt", "label": "maior que"},
                        {"value": "lte", "label": "menor ou igual"},
                        {"value": "lt", "label": "menor que"},
                        {"value": "eq", "label": "igual"},
                        {"value": "neq", "label": "diferente"},
                    ],
                    "weekdays": [
                        {"value": 0, "label": "Segunda"},
                        {"value": 1, "label": "Terça"},
                        {"value": 2, "label": "Quarta"},
                        {"value": 3, "label": "Quinta"},
                        {"value": 4, "label": "Sexta"},
                        {"value": 5, "label": "Sábado"},
                        {"value": 6, "label": "Domingo"},
                    ],
                    "environment": environment,
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
        conditions_error = _validate_conditions(db, payload.get("conditions"))
        if conditions_error:
            return error(conditions_error, 422)
        action_error = _validate_actions(db, payload["actions"])
        if action_error:
            return error(action_error, 422)
        return jsonify(serialize(AutomationService.create_automation(db, _prepare_automation_payload(payload))))
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
        if "trigger" in payload or "condition" in payload or "conditions" in payload:
            automation = AutomationService.get_automation(db, automation_id)
            if not automation:
                return error("Automacao nao encontrada", 404)
            condition_error = _validate_condition(
                db,
                payload.get("trigger", automation.trigger),
                payload.get("condition", _primary_condition(automation.condition)) or {},
            )
            if condition_error:
                return error(condition_error, 422)
            conditions_error = _validate_conditions(db, payload.get("conditions"))
            if conditions_error:
                return error(conditions_error, 422)
        if "actions" in payload:
            action_error = _validate_actions(db, payload["actions"])
            if action_error:
                return error(action_error, 422)
        automation = AutomationService.update_automation(db, automation_id, _prepare_automation_payload(payload))
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
