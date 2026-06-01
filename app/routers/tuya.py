"""Cadastro simplificado de lampadas Tuya."""

from flask import Blueprint, jsonify, request

from app.integrations.home_assistant import HomeAssistantIntegration
from app.integrations.tuya import TuyaIntegration
from app.routers.common import get_db, verify_token
from app.services.device_service import DeviceService

blueprint = Blueprint("tuya", __name__, url_prefix="/tuya")


def _upsert_tuya_devices(db, devices, ha_url=None, ha_token=None):
    existing_devices = DeviceService.get_devices(db, skip=0, limit=5000)
    existing_by_external_id = {}
    for device in existing_devices:
        metadata = device.device_metadata or {}
        if metadata.get("integration") == "tuya" and metadata.get("external_id"):
            existing_by_external_id[metadata["external_id"]] = device

    created_devices = []
    updated_devices = []

    for device_data in devices:
        external_id = device_data.get("external_id")
        if not external_id:
            continue

        metadata = dict(device_data.get("device_metadata") or {})
        metadata["external_id"] = external_id
        if metadata.get("power_state") not in {"on", "off"}:
            metadata.pop("power_state", None)
        if ha_url:
            metadata["ha_url"] = ha_url
        if ha_token:
            metadata["ha_token"] = ha_token

        existing = existing_by_external_id.get(external_id)
        if existing:
            updated = DeviceService.update_device(
                db,
                existing.id,
                {
                    "name": device_data.get("name", existing.name),
                    "room": device_data.get("room", existing.room),
                    "status": device_data.get("status", existing.status),
                    "device_metadata": {**(existing.device_metadata or {}), **metadata},
                },
            )
            updated_devices.append({"id": updated.id, "name": updated.name, "external_id": external_id})
            continue

        created = DeviceService.create_device(
            db,
            {
                "name": device_data.get("name", "Dispositivo Tuya"),
                "type": "tuya",
                "room": device_data.get("room", "tuya"),
                "status": device_data.get("status", "offline"),
                "device_metadata": metadata,
            },
        )
        created_devices.append({"id": created.id, "name": created.name, "external_id": external_id})

    return created_devices, updated_devices


@blueprint.post("/register")
def register_tuya_lamp():
    token_error = verify_token()
    if token_error:
        return token_error

    user_code = (request.get_json(silent=True) or {}).get("user_code", "").strip()
    if not user_code:
        return jsonify({"detail": "Informe o codigo do usuario"}), 422

    integration = TuyaIntegration()
    import_result = integration.get_devices_by_user_code(user_code)
    if not import_result.get("success"):
        return jsonify({"success": False, "detail": import_result.get("message", "Falha ao importar dispositivos Tuya.")}), 400

    db = get_db()
    try:
        created_devices, updated_devices = _upsert_tuya_devices(db, import_result.get("devices", []))

        return jsonify(
            {
                "success": True,
                "imported_total": len(import_result.get("devices", [])),
                "created_total": len(created_devices),
                "updated_total": len(updated_devices),
                "devices": created_devices,
                "message": f"{len(created_devices)} dispositivo(s) Tuya configurado(s) automaticamente.",
            }
        )
    finally:
        db.close()


@blueprint.post("/sync-home-assistant")
def sync_tuya_from_home_assistant():
    payload = request.get_json(silent=True) or {}
    ha_token = (payload.get("ha_token") or "").strip()
    ha_url = (payload.get("ha_url") or "").strip()

    if not ha_token:
        return jsonify({"success": False, "detail": "Informe o ha_token do Home Assistant."}), 422

    integration = HomeAssistantIntegration(base_url=ha_url or None, token=ha_token)
    import_result = integration.get_tuya_devices()
    if not import_result.get("success"):
        return jsonify({"success": False, "detail": import_result.get("message", "Falha ao importar do Home Assistant.")}), 400

    db = get_db()
    try:
        created_devices, updated_devices = _upsert_tuya_devices(
            db,
            import_result.get("devices", []),
            ha_url=ha_url or None,
            ha_token=ha_token,
        )
        return jsonify(
            {
                "success": True,
                "imported_total": len(import_result.get("devices", [])),
                "created_total": len(created_devices),
                "updated_total": len(updated_devices),
                "created_devices": created_devices,
                "updated_devices": updated_devices,
                "message": f"Sincronização concluída: {len(created_devices)} criado(s), {len(updated_devices)} atualizado(s).",
            }
        )
    finally:
        db.close()
