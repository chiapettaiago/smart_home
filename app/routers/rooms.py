from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.room_service import RoomService


blueprint = Blueprint("rooms", __name__, url_prefix="/rooms")


@blueprint.get("")
def get_rooms():
    db = get_db()
    try:
        return jsonify(serialize(RoomService.get_rooms(db)))
    finally:
        db.close()


@blueprint.post("")
def create_room():
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        try:
            room = RoomService.create_room(db, (request.get_json(silent=True) or {}).get("name"))
        except ValueError as exc:
            return error(str(exc), 422)
        return jsonify(serialize(room))
    finally:
        db.close()


@blueprint.delete("/<int:room_id>")
def delete_room(room_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        if not RoomService.delete_room(db, room_id):
            return error("Cômodo não encontrado", 404)
        return jsonify({"message": "Cômodo excluído e dispositivos desvinculados"})
    finally:
        db.close()


@blueprint.put("/<int:room_id>/devices/<int:device_id>")
def assign_device(room_id, device_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        try:
            device = RoomService.assign_device(db, device_id, room_id)
        except ValueError as exc:
            return error(str(exc), 404)
        return jsonify(serialize(device)) if device else error("Dispositivo não encontrado", 404)
    finally:
        db.close()


@blueprint.delete("/devices/<int:device_id>")
def unassign_device(device_id):
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        device = RoomService.assign_device(db, device_id, None)
        return jsonify(serialize(device)) if device else error("Dispositivo não encontrado", 404)
    finally:
        db.close()
