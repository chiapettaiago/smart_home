from flask import Blueprint, jsonify

from app.routers.common import get_db, serialize, verify_token
from app.services.presence_service import PresenceService

blueprint = Blueprint("presence", __name__, url_prefix="/presence")


@blueprint.post("/router/refresh")
def refresh_router_presence():
    token_error = verify_token()
    if token_error:
        return token_error
    db = get_db()
    try:
        return jsonify(PresenceService.refresh_from_vivo_router(db, force=True))
    finally:
        db.close()


@blueprint.post("/<user>/home")
def set_user_home(user):
    token_error = verify_token()
    if token_error:
        return token_error
    return _set_presence(user, True)


@blueprint.post("/<user>/away")
def set_user_away(user):
    token_error = verify_token()
    if token_error:
        return token_error
    return _set_presence(user, False)


def _set_presence(user, is_home):
    db = get_db()
    try:
        presence = PresenceService.set_home(db, user) if is_home else PresenceService.set_away(db, user)
        return jsonify(serialize(presence))
    finally:
        db.close()


@blueprint.get("/<user>")
def get_user_presence(user):
    db = get_db()
    try:
        return jsonify(serialize(PresenceService.get_presence(db, user)))
    finally:
        db.close()


@blueprint.get("")
def get_all_presence():
    db = get_db()
    try:
        presence_list = PresenceService.get_all_presence(db)
        return jsonify(
            {
                "presence": {presence.user: presence.is_home for presence in presence_list},
                "anyone_home": any(presence.is_home for presence in presence_list),
            }
        )
    finally:
        db.close()
