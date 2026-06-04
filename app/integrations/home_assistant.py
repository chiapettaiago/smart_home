"""Integração com Home Assistant via API REST."""

import ast
import colorsys

import requests

from app.config import HOME_ASSISTANT_TOKEN, HOME_ASSISTANT_URL


class HomeAssistantIntegration:
    def __init__(self, base_url: str = HOME_ASSISTANT_URL, token: str = HOME_ASSISTANT_TOKEN):
        resolved_url = base_url or HOME_ASSISTANT_URL or "http://homeassistant.local:8123"
        self.base_url = resolved_url.rstrip("/")
        self.token = token or HOME_ASSISTANT_TOKEN or ""
        self.timeout = 10

    def _is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get_tuya_entity_ids_from_template(self) -> list:
        try:
            response = requests.post(
                f"{self.base_url}/api/template",
                headers=self._auth_headers(),
                json={"template": "{{ integration_entities('tuya') }}"},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return []

            payload = response.text.strip()
            if not payload:
                return []

            values = ast.literal_eval(payload)
            if isinstance(values, list):
                return [str(item) for item in values if item]
            return []
        except Exception:
            return []

    def call_service(self, domain: str, service: str, entity_id: str, service_data: dict = None) -> dict:
        if not self.base_url:
            return {"success": False, "message": "URL do Home Assistant não configurada."}
        if not self.token:
            return {"success": False, "message": "Token do Home Assistant não configurado."}
        if not entity_id:
            return {"success": False, "message": "entity_id não informado."}

        try:
            response = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self._auth_headers(),
                json={"entity_id": entity_id, **(service_data or {})},
                timeout=self.timeout,
            )
            if response.status_code not in {200, 201}:
                return {
                    "success": False,
                    "message": f"Falha ao executar {domain}.{service} ({response.status_code}).",
                    "response": response.text,
                }
            return {
                "success": True,
                "message": f"Serviço {domain}.{service} executado.",
                "response": response.json() if response.text else {},
            }
        except Exception as exc:
            return {"success": False, "message": f"Erro ao chamar serviço HA: {exc}"}

    def turn_on(self, entity_id: str) -> dict:
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        # Alguns dispositivos aceitam melhor no domínio base.
        candidates = [("homeassistant", "turn_on")]
        if domain in {"light", "switch", "fan", "climate"}:
            candidates.insert(0, (domain, "turn_on"))
        for dmn, svc in candidates:
            result = self.call_service(dmn, svc, entity_id)
            if result.get("success"):
                return result
        return result

    def turn_off(self, entity_id: str) -> dict:
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        candidates = [("homeassistant", "turn_off")]
        if domain in {"light", "switch", "fan", "climate"}:
            candidates.insert(0, (domain, "turn_off"))
        for dmn, svc in candidates:
            result = self.call_service(dmn, svc, entity_id)
            if result.get("success"):
                return result
        return result

    def toggle(self, entity_id: str) -> dict:
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        candidates = [("homeassistant", "toggle")]
        if domain in {"light", "switch", "fan"}:
            candidates.insert(0, (domain, "toggle"))
        for dmn, svc in candidates:
            result = self.call_service(dmn, svc, entity_id)
            if result.get("success"):
                return result
        return result

    def set_state(self, entity_id: str, service: str, service_data: dict = None) -> dict:
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        return self.call_service(domain, service, entity_id, service_data=service_data or {})

    def set_light_color_temp(self, entity_id: str, color_temp: int) -> dict:
        """Ajusta branco por temperatura tentando os formatos aceitos pelo HA."""
        result = self.set_state(entity_id, "turn_on", {"color_temp": color_temp})
        if result.get("success"):
            return result

        color_temp_kelvin = round(1000000 / color_temp) if color_temp else 4000
        fallback = self.set_state(entity_id, "turn_on", {"color_temp_kelvin": color_temp_kelvin})
        if fallback.get("success"):
            return fallback

        fallback["attempts"] = [
            {"service_data": {"color_temp": color_temp}, "result": self._summarize_result(result)},
            {"service_data": {"color_temp_kelvin": color_temp_kelvin}, "result": self._summarize_result(fallback)},
        ]
        return fallback

    def set_light_rgb_color(self, entity_id: str, rgb_color: list) -> dict:
        if self._is_white_rgb(rgb_color):
            return self.set_light_white(entity_id)

        result = self.set_state(entity_id, "turn_on", {"rgb_color": rgb_color})
        if result.get("success"):
            return result

        try:
            red, green, blue = [max(0, min(255, int(value))) / 255 for value in rgb_color[:3]]
            hue, saturation, _ = colorsys.rgb_to_hsv(red, green, blue)
            hs_payload = {"hs_color": [round(hue * 360, 2), round(saturation * 100, 2)]}
            fallback = self.set_state(entity_id, "turn_on", hs_payload)
            if fallback.get("success"):
                return fallback
            fallback["attempts"] = [
                {"service_data": {"rgb_color": rgb_color}, "result": self._summarize_result(result)},
                {"service_data": hs_payload, "result": self._summarize_result(fallback)},
            ]
            return fallback
        except Exception:
            return result

    def set_light_white(self, entity_id: str) -> dict:
        state = self.get_state(entity_id)
        attributes = ((state.get("state") or {}).get("attributes") or {}) if state.get("success") else {}
        attempts = []
        for service_data in self._white_service_candidates(attributes):
            result = self.set_state(entity_id, "turn_on", service_data)
            attempts.append({"service_data": service_data, "result": self._summarize_result(result)})
            if result.get("success"):
                return result

        result = attempts[-1]["result"] if attempts else {"success": False, "message": "Nenhuma tentativa de branco disponível."}
        result["attempts"] = attempts
        return result

    @staticmethod
    def _summarize_result(result: dict) -> dict:
        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "response": result.get("response"),
        }

    @staticmethod
    def _is_white_rgb(rgb_color: list) -> bool:
        return (
            isinstance(rgb_color, list)
            and len(rgb_color) >= 3
            and all(int(value) >= 245 for value in rgb_color[:3])
        )

    @staticmethod
    def _white_service_candidates(attributes: dict) -> list:
        supported_modes = attributes.get("supported_color_modes") or []
        ordered_modes = ["color_temp", "white", "rgbww", "rgbw", "xy", "hs", "rgb", *supported_modes]
        candidates_by_mode = {
            "color_temp": [
                {"color_temp_kelvin": HomeAssistantIntegration._preferred_kelvin(attributes)},
                {"color_temp": HomeAssistantIntegration._preferred_mired(attributes)},
            ],
            "hs": [{"hs_color": [0, 0]}],
            "white": [{"white": 255}],
            "xy": [{"xy_color": [0.3127, 0.3290]}],
            "rgbw": [{"rgbw_color": [255, 255, 255, 255]}],
            "rgbww": [{"rgbww_color": [255, 255, 255, 255, 255]}],
            "rgb": [{"rgb_color": [255, 255, 255]}],
        }
        candidates = []
        seen = set()
        for mode in ordered_modes:
            for candidate in candidates_by_mode.get(mode, []):
                key = tuple((key, tuple(value) if isinstance(value, list) else value) for key, value in candidate.items())
                if key not in seen:
                    candidates.append(candidate)
                    seen.add(key)
        return candidates

    @staticmethod
    def _preferred_kelvin(attributes: dict) -> int:
        minimum = attributes.get("min_color_temp_kelvin") or 2700
        maximum = attributes.get("max_color_temp_kelvin") or 6500
        minimum = int(minimum)
        maximum = int(maximum)
        return max(minimum, min(maximum, round(minimum + ((maximum - minimum) * 0.25))))

    @staticmethod
    def _preferred_mired(attributes: dict) -> int:
        minimum = attributes.get("min_mireds") or 153
        maximum = attributes.get("max_mireds") or 500
        minimum = int(minimum)
        maximum = int(maximum)
        preferred_mired = round(1000000 / HomeAssistantIntegration._preferred_kelvin(attributes))
        return max(minimum, min(maximum, preferred_mired))

    def get_state(self, entity_id: str) -> dict:
        if not self.base_url:
            return {"success": False, "message": "URL do Home Assistant não configurada."}
        if not self.token:
            return {"success": False, "message": "Token do Home Assistant não configurado."}
        if not entity_id:
            return {"success": False, "message": "entity_id não informado."}
        try:
            response = requests.get(
                f"{self.base_url}/api/states/{entity_id}",
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return {
                    "success": False,
                    "message": f"Falha ao obter estado ({response.status_code}).",
                    "response": response.text,
                }
            return {"success": True, "message": "Estado obtido com sucesso.", "state": response.json()}
        except Exception as exc:
            return {"success": False, "message": f"Erro ao consultar estado: {exc}"}

    def get_states(self, entity_ids: list = None) -> dict:
        """Obtém estados atuais em lote para evitar uma chamada por dispositivo."""
        if not self.base_url:
            return {"success": False, "message": "URL do Home Assistant não configurada.", "states": {}}
        if not self.token:
            return {"success": False, "message": "Token do Home Assistant não configurado.", "states": {}}
        try:
            response = requests.get(
                f"{self.base_url}/api/states",
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return {
                    "success": False,
                    "message": f"Falha ao obter estados ({response.status_code}).",
                    "states": {},
                }
            requested_ids = set(entity_ids or [])
            states = {
                item["entity_id"]: item
                for item in response.json()
                if item.get("entity_id") and (not requested_ids or item["entity_id"] in requested_ids)
            }
            return {"success": True, "message": "Estados obtidos com sucesso.", "states": states}
        except Exception as exc:
            return {"success": False, "message": f"Erro ao consultar estados: {exc}", "states": {}}

    def get_tuya_devices(self) -> dict:
        if not self.base_url:
            return {
                "success": False,
                "message": "Informe a URL do Home Assistant (ha_url) ou configure HOME_ASSISTANT_URL no .env.",
                "devices": [],
            }

        if not self.token:
            return {
                "success": False,
                "message": "Informe o ha_token do Home Assistant.",
                "devices": [],
            }

        try:
            response = requests.get(
                f"{self.base_url}/api/states",
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return {
                    "success": False,
                    "message": f"Home Assistant retornou status {response.status_code}.",
                    "devices": [],
                }

            entities = response.json()
            entities_by_id = {
                item.get("entity_id"): item
                for item in entities
                if item.get("entity_id")
            }
            devices = []
            matched_entity_ids = set()
            for entity in entities:
                entity_id = entity.get("entity_id", "")
                attributes = entity.get("attributes") or {}
                integration_name = (attributes.get("integration") or attributes.get("platform") or "").lower()
                friendly_name = (attributes.get("friendly_name") or "").lower()
                attribution = (attributes.get("attribution") or "").lower()
                manufacturer = (attributes.get("manufacturer") or "").lower()
                brand = (attributes.get("brand") or "").lower()
                model = (attributes.get("model") or "").lower()

                # Em muitos HA, entidades Tuya não vêm como `tuya.*`.
                is_tuya = any(
                    "tuya" in value
                    for value in (
                        entity_id.lower(),
                        integration_name,
                        friendly_name,
                        attribution,
                        manufacturer,
                        brand,
                        model,
                    )
                )
                if not is_tuya:
                    continue
                matched_entity_ids.add(entity_id)

            if not matched_entity_ids:
                matched_entity_ids.update(self._get_tuya_entity_ids_from_template())

            for entity_id in matched_entity_ids:
                entity = entities_by_id.get(entity_id)
                if not entity:
                    continue
                domain = entity_id.split(".", 1)[0]
                if domain not in {"light", "switch", "fan", "climate"}:
                    continue
                attributes = entity.get("attributes") or {}

                devices.append(
                    {
                        "external_id": entity_id,
                        "name": attributes.get("friendly_name") or entity_id,
                        "type": "tuya",
                        "room": attributes.get("room") or attributes.get("area") or "casa",
                        "status": "online" if entity.get("state") not in {"unavailable", "unknown"} else "offline",
                        "device_metadata": {
                            "integration": "tuya",
                            "source": "home_assistant",
                            "entity_id": entity_id,
                            "ha_state": entity.get("state"),
                            "power_state": entity.get("state") if entity.get("state") in {"on", "off"} else None,
                            "device_class": attributes.get("device_class"),
                            "unit_of_measurement": attributes.get("unit_of_measurement"),
                        },
                    }
                )

            return {
                "success": True,
                "message": f"Dispositivos Tuya lidos do Home Assistant com sucesso ({len(devices)} encontrado(s)).",
                "devices": devices,
            }
        except Exception as exc:
            return {
                "success": False,
                "message": f"Erro ao consultar Home Assistant: {exc}",
                "devices": [],
            }
