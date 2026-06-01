"""
Integração com Tuya IoT Platform.
Fluxo de importação por código de usuário (user code), no estilo Home Assistant.
"""

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests

class TuyaIntegration:
    """Gerenciador de integração com Tuya"""

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key or os.getenv("TUYA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("TUYA_API_SECRET", "")
        self.endpoint = "https://openapi.tuyaus.com"
        self.timeout = 10

    def _sign(self, message: str) -> str:
        return hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256).hexdigest().upper()

    def _request(self, method: str, path: str, params: dict = None, access_token: str = "") -> dict:
        if params:
            path = f"{path}?{urlencode(params)}"
        timestamp = str(int(time.time() * 1000))
        content_sha256 = hashlib.sha256(b"").hexdigest()
        string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
        sign_payload = f"{self.api_key}{access_token}{timestamp}{string_to_sign}"
        headers = {
            "client_id": self.api_key,
            "sign": self._sign(sign_payload),
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }
        if access_token:
            headers["access_token"] = access_token
        response = requests.request(
            method=method,
            url=f"{self.endpoint}{path}",
            headers=headers,
            timeout=self.timeout,
        )
        return response.json()

    def _get_access_token(self) -> str:
        result = self._request("GET", "/v1.0/token", params={"grant_type": 1})
        if not result.get("success"):
            return ""
        return (result.get("result") or {}).get("access_token", "")

    @staticmethod
    def _category_to_type(category: str) -> str:
        category = (category or "").lower()
        if category in {"dj", "dd", "cz", "kg", "pc", "qn"}:
            return "tuya"
        if category in {"tv", "dtt"}:
            return "roku"
        return "other"

    @staticmethod
    def _get_power_state(statuses: list) -> str:
        power_codes = {"switch", "switch_1", "switch_led", "switch_main"}
        for status in statuses or []:
            if status.get("code") in power_codes and isinstance(status.get("value"), bool):
                return "on" if status["value"] else "off"
        return ""

    def get_devices_by_user_code(self, user_code: str) -> dict:
        if not self.api_key or not self.api_secret:
            return {
                "success": False,
                "message": "Configure TUYA_API_KEY e TUYA_API_SECRET para importar dispositivos Tuya.",
                "devices": [],
            }

        access_token = self._get_access_token()
        if not access_token:
            return {"success": False, "message": "Falha ao autenticar na API Tuya.", "devices": []}

        # O user_code do app é tratado como UID da conta vinculada.
        result = self._request("GET", f"/v1.0/users/{user_code}/devices", access_token=access_token)
        if not result.get("success"):
            return {
                "success": False,
                "message": result.get("msg", "Falha ao listar dispositivos da conta Tuya."),
                "devices": [],
            }

        raw_devices = result.get("result") or []
        devices = [
            {
                "external_id": item.get("id"),
                "name": item.get("name") or "Dispositivo Tuya",
                "type": self._category_to_type(item.get("category")),
                "room": item.get("product_name") or "tuya",
                "status": "online" if item.get("online") else "offline",
                "device_metadata": {
                    "integration": "tuya",
                    "user_code": user_code,
                    "category": item.get("category"),
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name"),
                    "power_state": self._get_power_state(item.get("status")),
                },
            }
            for item in raw_devices
        ]
        return {"success": True, "message": "Dispositivos Tuya obtidos com sucesso.", "devices": devices}

    def turn_on(self, device_id: str) -> dict:
        """Liga um dispositivo Tuya"""
        # TODO: Implementar chamada à API do Tuya
        return {"success": False, "message": "Não implementado ainda"}

    def turn_off(self, device_id: str) -> dict:
        """Desliga um dispositivo Tuya"""
        # TODO: Implementar chamada à API do Tuya
        return {"success": False, "message": "Não implementado ainda"}

    def get_status(self, device_id: str) -> dict:
        """Obtém status de um dispositivo Tuya"""
        # TODO: Implementar chamada à API do Tuya
        return {"success": False, "message": "Não implementado ainda"}

    def send_command(self, device_id: str, command: str, params: dict = None) -> dict:
        """Envia comando customizado ao Tuya"""
        # TODO: Implementar chamada à API do Tuya
        return {"success": False, "message": "Não implementado ainda"}

    def get_device_list(self) -> list:
        """Obtém lista de dispositivos Tuya"""
        return []

    def get_device_energy(self, device_id: str) -> dict:
        """Obtém consumo de energia do Tuya"""
        # TODO: Implementar chamada à API do Tuya
        return {"success": False, "message": "Não implementado ainda"}
