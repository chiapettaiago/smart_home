from datetime import datetime, timedelta
import logging

from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.action_service import ActionService
from app.services.device_service import DeviceService

blueprint = Blueprint("devices", __name__, url_prefix="/devices")
logger = logging.getLogger(__name__)


@blueprint.get("")
def get_devices():
    db = get_db()
    try:
        devices = DeviceService.get_devices(
            db,
            skip=request.args.get("skip", 0, type=int),
            limit=request.args.get("limit", 100, type=int),
        )
        return jsonify(serialize(devices))
    finally:
        db.close()


@blueprint.post("")
def create_device():
    token_error = verify_token()
    if token_error:
        return token_error
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("type"):
        return error("Informe name e type", 422)
    db = get_db()
    try:
        return jsonify(serialize(DeviceService.create_device(db, payload)))
    finally:
        db.close()


@blueprint.get("/<int:device_id>")
def get_device(device_id):
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        return jsonify(serialize(device)) if device else error("Dispositivo nao encontrado", 404)
    finally:
        db.close()


@blueprint.put("/<int:device_id>")
def update_device(device_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        device = DeviceService.update_device(db, device_id, request.get_json(silent=True) or {})
        return jsonify(serialize(device)) if device else error("Dispositivo nao encontrado", 404)
    finally:
        db.close()


@blueprint.delete("/<int:device_id>")
def delete_device(device_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        if not DeviceService.delete_device(db, device_id):
            return error("Dispositivo nao encontrado", 404)
        return jsonify({"message": "Dispositivo deletado com sucesso"})
    finally:
        db.close()


@blueprint.get("/<int:device_id>/action/history")
def get_device_actions(device_id):
    db = get_db()
    try:
        if not DeviceService.get_device(db, device_id):
            return error("Dispositivo nao encontrado", 404)
        actions = ActionService.get_action_logs(
            db,
            device_id=device_id,
            limit=request.args.get("limit", 50, type=int),
        )
        return jsonify(serialize({"device_id": device_id, "actions": actions}))
    finally:
        db.close()


@blueprint.post("/<int:device_id>/action")
def execute_device_action(device_id):
    token_error = verify_token()
    if token_error:
        return token_error

    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device:
            return error("Dispositivo nao encontrado", 404)
        if not ActionService.is_action_allowed(action):
            return error(f"Acao '{action}' nao permitida", 400)

        result = ActionService.execute_action(device, action, payload.get("params"))
        try:
            if result["success"] and device.type == "tuya":
                metadata = dict(device.device_metadata or {})
                current_state = metadata.get("power_state") or metadata.get("ha_state")
                next_state = None
                if action.lower() == "turn_on":
                    next_state = "on"
                elif action.lower() == "turn_off":
                    next_state = "off"
                elif action.lower() == "toggle" and current_state in {"on", "off"}:
                    next_state = "off" if current_state == "on" else "on"
                if next_state:
                    metadata["power_state"] = next_state
                    metadata["pending_power_state"] = next_state
                    metadata["pending_power_state_until"] = (datetime.utcnow() + timedelta(seconds=12)).isoformat()
                    DeviceService.update_device(db, device_id, {"device_metadata": metadata})
        except Exception:
            db.rollback()
            logger.exception("Falha ao atualizar estado local do dispositivo %s", device_id)

        try:
            ActionService.log_action(
                db,
                device_id=device_id,
                action=action,
                params=payload.get("params"),
                status="success" if result["success"] else "failed",
                response=result["data"],
            )
        except Exception:
            db.rollback()
            logger.exception("Falha ao registrar ação %s do dispositivo %s", action, device_id)
        return jsonify(result)
    finally:
        db.close()


@blueprint.get("/room/<room>")
def get_devices_by_room(room):
    db = get_db()
    try:
        return jsonify(serialize({"room": room, "devices": DeviceService.get_devices_by_room(db, room)}))
    finally:
        db.close()


@blueprint.get("/status/online")
def get_online_devices():
    db = get_db()
    try:
        devices = DeviceService.get_online_devices(db)
        return jsonify(serialize({"online_devices": len(devices), "devices": devices}))
    finally:
        db.close()
