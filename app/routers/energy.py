from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.device_service import DeviceService
from app.services.energy_service import EnergyService

blueprint = Blueprint("energy", __name__, url_prefix="/energy")


@blueprint.post("/readings")
def add_energy_reading():
    token_error = verify_token()
    if token_error:
        return token_error
    payload = request.get_json(silent=True) or {}
    device_id = payload.get("device_id")
    db = get_db()
    try:
        if not device_id or not DeviceService.get_device(db, device_id):
            return error("Dispositivo nao encontrado", 404)
        reading = EnergyService.add_reading(
            db,
            device_id=device_id,
            watts=payload.get("watts"),
            voltage=payload.get("voltage"),
            current=payload.get("current"),
            kwh=payload.get("kwh"),
        )
        return jsonify(serialize(reading))
    finally:
        db.close()


@blueprint.get("/readings/<int:device_id>")
def get_device_energy_readings(device_id):
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device:
            return error("Dispositivo nao encontrado", 404)
        readings = EnergyService.get_readings(
            db,
            device_id=device_id,
            hours=request.args.get("hours", 24, type=int),
            limit=request.args.get("limit", 100, type=int),
        )
        return jsonify(serialize({"device_id": device_id, "device_name": device.name, "readings": readings}))
    finally:
        db.close()


@blueprint.get("/consumption/total")
def get_total_consumption():
    db = get_db()
    try:
        hours = request.args.get("hours", 24, type=int)
        return jsonify({"period_hours": hours, **EnergyService.get_total_consumption(db, hours=hours)})
    finally:
        db.close()


@blueprint.get("/consumption/by-device")
def get_consumption_by_device():
    db = get_db()
    try:
        hours = request.args.get("hours", 24, type=int)
        return jsonify(
            {
                "period_hours": hours,
                "total_consumption": EnergyService.get_total_consumption(db, hours=hours),
                "by_device": EnergyService.get_consumption_by_device(db, hours=hours),
            }
        )
    finally:
        db.close()


@blueprint.get("/last-reading/<int:device_id>")
def get_last_energy_reading(device_id):
    db = get_db()
    try:
        device = DeviceService.get_device(db, device_id)
        if not device:
            return error("Dispositivo nao encontrado", 404)
        reading = EnergyService.get_last_reading(db, device_id)
        return jsonify(
            serialize(
                {
                    "device_id": device_id,
                    "device_name": device.name,
                    "reading": reading,
                    "message": None if reading else "Nenhuma leitura registrada ainda",
                }
            )
        )
    finally:
        db.close()
