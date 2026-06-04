"""Integracao com TV Roku informando apenas o IP."""

from flask import Blueprint, jsonify, request

from app.integrations.roku import RokuIntegration
from app.routers.common import error, get_db, verify_token
from app.services.device_service import DeviceService

blueprint = Blueprint("roku", __name__, url_prefix="/roku")


@blueprint.post("/discover")
def discover_roku():
    ip = (request.get_json(silent=True) or {}).get("ip", "").strip()
    if not ip:
        return error("Informe o IP", 422)
    result = RokuIntegration(ip).test_connection()
    if not result["online"]:
        return jsonify({"success": False, "ip": ip, "online": False, "message": "Roku nao encontrado neste IP"})
    status = RokuIntegration(ip).get_status()
    return jsonify(
        {
            "success": True,
            "ip": ip,
            "online": True,
            "powered_on": status.get("powered_on", False),
            "message": "Roku encontrado!",
        }
    )


@blueprint.post("/register")
def register_roku():
    token_error = verify_token()
    if token_error:
        return token_error
    ip = (request.get_json(silent=True) or {}).get("ip", "").strip()
    if not ip:
        return error("Informe o IP", 422)
    if not RokuIntegration(ip).test_connection()["online"]:
        return jsonify({"success": False, "message": "Nao foi possivel conectar ao Roku neste IP"})

    db = get_db()
    try:
        device = DeviceService.create_device(
            db,
            {
                "name": f"Roku {ip}",
                "type": "roku",
                "ip": ip,
                "status": "online",
                "room": "sala",
                "device_metadata": {"integration": "roku", "api_ready": True},
            },
        )
        return jsonify(
            {
                "success": True,
                "device_id": device.id,
                "name": device.name,
                "ip": ip,
                "message": f"Roku '{device.name}' cadastrado com sucesso!",
            }
        )
    finally:
        db.close()


@blueprint.post("/devices/<int:device_id>/control")
def control_roku(device_id):
    token_error = verify_token()
    if token_error:
        return token_error
    payload = request.get_json(silent=True) or {}
    command = payload.get("command", "").lower()
    params = payload.get("params") or {}
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device or device.type != "roku":
            return error("Dispositivo Roku nao encontrado", 404)
        roku = RokuIntegration(device.ip)
        handlers = {
            "turn_on": roku.turn_on,
            "turn_off": roku.turn_off,
            "close_app": roku.close_app,
            "get_status": roku.get_status,
            "get_apps": roku.get_app_list,
        }
        if command == "launch_app":
            result = roku.launch_app(params.get("app_id", "netflix"))
        elif command == "send_command":
            result = roku.send_command(params.get("command", "select"))
        elif command in handlers:
            result = handlers[command]()
        else:
            result = {"success": False, "message": f"Comando '{command}' nao reconhecido"}
        return jsonify({"success": result.get("success", False), "device_id": device_id, "command": command, "result": result})
    finally:
        db.close()


@blueprint.get("/devices/<int:device_id>/apps")
def get_roku_apps(device_id):
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device or device.type != "roku":
            return error("Dispositivo Roku nao encontrado", 404)
        result = RokuIntegration(device.ip).get_app_list()
        return jsonify({"device_id": device_id, "device_name": device.name, "apps": result.get("apps", {}), "success": result.get("success", False)})
    finally:
        db.close()


@blueprint.get("/devices/<int:device_id>/status")
def get_roku_status(device_id):
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device or device.type != "roku":
            return error("Dispositivo Roku nao encontrado", 404)
        status = RokuIntegration(device.ip).get_status()
        return jsonify({
            "device_id": device_id,
            "device_name": device.name,
            "ip": device.ip,
            "online": status.get("online", False),
            "powered_on": status.get("powered_on", False),
            "playback_state": status.get("playback_state"),
            "status": status,
        })
    finally:
        db.close()
