from flask import Blueprint, jsonify, request

from app.routers.common import error, get_db, serialize, verify_token
from app.services.automation_service import AutomationService

blueprint = Blueprint("automations", __name__, url_prefix="/automations")


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
    db = get_db()
    try:
        automation = AutomationService.update_automation(db, automation_id, request.get_json(silent=True) or {})
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
