"""Rotas para gerenciamento de usuários."""

from flask import Blueprint, jsonify, request, session

from app.routers.common import error, get_db, serialize, verify_token
from app.security import is_api_token_valid
from app.services.user_service import UserService

blueprint = Blueprint("users", __name__, url_prefix="/users")


def _serialize_user(user):
    data = serialize(user)
    data.pop("password_hash", None)
    return data


def _current_user_id() -> int | None:
    try:
        return int(session.get("user_id") or 0) or None
    except (TypeError, ValueError):
        return None


def _require_admin(db):
    token_error = verify_token()
    if token_error:
        return token_error
    if is_api_token_valid():
        return None
    user_id = _current_user_id()
    user = UserService.get_user(db, user_id) if user_id else None
    if not user or not user.is_active or not user.is_admin:
        return error("Apenas administradores podem gerenciar usuários.", 403)
    return None


@blueprint.get("")
def list_users():
    db = get_db()
    try:
        admin_error = _require_admin(db)
        if admin_error:
            return admin_error
        return jsonify({"users": [_serialize_user(user) for user in UserService.get_users(db)]})
    finally:
        db.close()


@blueprint.post("")
def create_user():
    db = get_db()
    try:
        admin_error = _require_admin(db)
        if admin_error:
            return admin_error
        payload = request.get_json(silent=True) or {}
        try:
            user = UserService.create_user(db, payload)
        except ValueError as exc:
            return error(str(exc), 422)
        return jsonify(_serialize_user(user)), 201
    finally:
        db.close()


@blueprint.put("/<int:user_id>")
def update_user(user_id):
    db = get_db()
    try:
        admin_error = _require_admin(db)
        if admin_error:
            return admin_error
        payload = request.get_json(silent=True) or {}
        try:
            user = UserService.update_user(db, user_id, payload, current_user_id=_current_user_id())
        except ValueError as exc:
            return error(str(exc), 422)
        if user.id == _current_user_id():
            session["username"] = user.username
            session["is_admin"] = bool(user.is_admin)
        return jsonify(_serialize_user(user))
    finally:
        db.close()


@blueprint.delete("/<int:user_id>")
def delete_user(user_id):
    db = get_db()
    try:
        admin_error = _require_admin(db)
        if admin_error:
            return admin_error
        try:
            UserService.delete_user(db, user_id, current_user_id=_current_user_id())
        except ValueError as exc:
            return error(str(exc), 422)
        return jsonify({"success": True})
    finally:
        db.close()
