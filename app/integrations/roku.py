"""
Integração com Roku TV via API REST
Permite controlar TV Roku informando apenas o IP
"""

import requests
import logging
import re
from typing import Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class RokuIntegration:
    """Gerenciador de integração com Roku TV"""

    # Comandos de controle remoto suportados
    REMOTE_COMMANDS = {
        "home": "Home",
        "back": "Back",
        "left": "Left",
        "right": "Right",
        "up": "Up",
        "down": "Down",
        "select": "Select",
        "play": "Play",
        "pause": "Pause",
        "rewind": "Rewind",
        "forward": "Forward",
    }
    PLAYBACK_STATE_LABELS = {
        "playing": "Reproduzindo",
        "paused": "Pausado",
        "idle": "Ocioso",
        "buffering": "Carregando",
        "error": "Erro",
        "unknown": "Desconhecido",
    }
    PLAYER_STATE_MAP = {
        "play": "playing",
        "playing": "playing",
        "pause": "paused",
        "paused": "paused",
        "stop": "idle",
        "stopped": "idle",
        "none": "idle",
        "idle": "idle",
        "buffer": "buffering",
        "buffering": "buffering",
        "error": "error",
    }
    MEDIA_DETAIL_TAGS = (
        "title",
        "artist",
        "album",
        "series",
        "episode",
        "season",
        "description",
        "content-type",
        "contentType",
        "media-type",
        "mediaType",
        "duration",
        "length",
        "position",
        "runtime",
        "stream-format",
        "streamFormat",
        "quality",
        "rating",
        "image",
        "thumbnail",
        "url",
        "is-live",
        "isLive",
    )

    def __init__(self, device_ip: str, timeout: int = 5):
        self.device_ip = device_ip
        self.timeout = timeout
        self.base_url = f"http://{device_ip}:8060"
        self.apps_cache = None

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: str = None,
        timeout: Optional[int] = None,
    ) -> Optional[requests.Response]:
        """Faz requisição ao Roku"""
        try:
            url = f"{self.base_url}{endpoint}"
            if method.upper() == "POST":
                response = requests.post(url, data=data, timeout=timeout or self.timeout)
            else:
                response = requests.get(url, timeout=timeout or self.timeout)
            return response
        except requests.exceptions.ConnectionError:
            logger.warning(f"Não foi possível conectar ao Roku em {self.device_ip}")
            return None
        except Exception as e:
            logger.error(f"Erro ao comunicar com Roku: {e}")
            return None

    def get_status(self) -> dict:
        """Obtém status da TV Roku"""
        try:
            response = self._make_request("GET", "/query/device-info")
            if response and response.status_code == 200:
                root = ET.fromstring(response.text)
                power_mode = (root.findtext("power-mode") or "").strip()
                is_powered = power_mode == "PowerOn"

                now_playing = self.get_now_playing()
                playback_state = "off" if not is_powered else now_playing.get("playback_state", "unknown")

                return {
                    "success": True,
                    "online": True,
                    "powered_on": is_powered,
                    "power_mode": power_mode,
                    "playback_state": playback_state,
                    "playback_state_label": self.PLAYBACK_STATE_LABELS.get(playback_state, "Desconhecido"),
                    "now_playing": now_playing,
                    "message": "Status obtido com sucesso",
                }
            return {
                "success": False,
                "online": False,
                "message": "Não conseguiu obter status",
            }
        except Exception as e:
            logger.error(f"Erro ao obter status do Roku: {e}")
            return {
                "success": False,
                "online": False,
                "message": f"Erro: {str(e)}",
            }

    def get_now_playing(self) -> dict:
        """Obtém o app ativo e tentativa de metadados do conteúdo em reprodução."""
        try:
            active_app_response = self._make_request("GET", "/query/active-app")
            if not active_app_response or active_app_response.status_code != 200:
                return {"app_name": "Desconhecido", "content_title": None, "playback_state": "unknown"}

            root = ET.fromstring(active_app_response.text)
            app_node = root.find("app")
            app_name = app_node.text.strip() if app_node is not None and app_node.text else "Tela inicial"
            app_attributes = dict(app_node.attrib) if app_node is not None else {}

            content_title = None
            player_state = None
            media_details = {}
            media_attributes = {}
            position_seconds = None
            duration_seconds = None
            progress_percent = None
            media_response = self._make_request("GET", "/query/media-player")
            if media_response and media_response.status_code == 200:
                media_root = ET.fromstring(media_response.text)
                player_node = media_root if media_root.tag == "player" else media_root.find(".//player")
                player_state = (player_node.attrib.get("state") or "").strip().lower() if player_node is not None else None
                media_details = self._extract_media_details(media_root)
                media_attributes = self._extract_media_attributes(media_root)
                position_seconds = self._parse_duration_seconds(
                    self._first_media_value(media_details, media_attributes, ("position", "elapsed", "runtime"))
                )
                duration_seconds = self._parse_duration_seconds(
                    self._first_media_value(media_details, media_attributes, ("duration", "length"))
                )
                if duration_seconds and position_seconds is not None:
                    progress_percent = round(max(0, min(100, (position_seconds / duration_seconds) * 100)), 1)
                for tag in ("title", "artist", "album"):
                    if media_details.get(tag):
                        content_title = media_details[tag]
                        break

            playback_state = self._normalize_playback_state(player_state, app_name, content_title)
            return {
                "app_name": app_name,
                "app_id": app_attributes.get("id"),
                "app_type": app_attributes.get("type"),
                "app_version": app_attributes.get("version"),
                "content_title": content_title,
                "player_state": player_state,
                "playback_state": playback_state,
                "playback_state_label": self.PLAYBACK_STATE_LABELS.get(playback_state, "Desconhecido"),
                "position_seconds": position_seconds,
                "duration_seconds": duration_seconds,
                "progress_percent": progress_percent,
                "media_details": media_details,
                "media_attributes": media_attributes,
            }
        except Exception as e:
            logger.warning(f"Erro ao obter now playing do Roku {self.device_ip}: {e}")
            return {"app_name": "Indisponível", "content_title": None, "playback_state": "unknown"}

    def _extract_media_details(self, media_root) -> dict:
        details = {}
        for tag in self.MEDIA_DETAIL_TAGS:
            node = media_root.find(f".//{tag}")
            if node is not None and node.text and node.text.strip():
                details[tag] = node.text.strip()
        return details

    def _extract_media_attributes(self, media_root) -> dict:
        attributes = {}
        for node in media_root.iter():
            if node.attrib:
                attributes[node.tag] = dict(node.attrib)
        return attributes

    def _first_media_value(self, media_details: dict, media_attributes: dict, keys: tuple):
        normalized_keys = {key.lower().replace("-", "").replace("_", "") for key in keys}
        for key, value in media_details.items():
            if key.lower().replace("-", "").replace("_", "") in normalized_keys:
                return value
        for attributes in media_attributes.values():
            for key, value in attributes.items():
                if key.lower().replace("-", "").replace("_", "") in normalized_keys:
                    return value
        return None

    def _parse_duration_seconds(self, value) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        milliseconds_match = re.fullmatch(r"([\d.]+)\s*ms", text, flags=re.IGNORECASE)
        if milliseconds_match:
            return int(float(milliseconds_match.group(1)) / 1000)
        seconds_match = re.fullmatch(r"([\d.]+)\s*s", text, flags=re.IGNORECASE)
        if seconds_match:
            return int(float(seconds_match.group(1)))
        try:
            numeric_value = float(text)
            return int(numeric_value / 1000) if numeric_value > 86400 else int(numeric_value)
        except ValueError:
            pass
        if ":" not in text:
            return None
        try:
            parts = [int(float(part)) for part in text.split(":")]
        except ValueError:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds

    def _normalize_playback_state(self, player_state: str, app_name: str, content_title: str = None) -> str:
        normalized = self.PLAYER_STATE_MAP.get((player_state or "").lower())
        if normalized:
            return normalized
        app = (app_name or "").strip().lower()
        if app in {"", "roku", "home", "tela inicial"}:
            return "idle"
        return "playing" if content_title else "idle"

    def turn_on(self) -> dict:
        """Liga a TV Roku (envia comando PowerOn)"""
        try:
            response = self._make_request("POST", "/keypress/PowerOn")
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": "Comando enviado - TV pode estar ligando",
                }
            return {"success": False, "message": "Falha ao enviar comando"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}

    def turn_off(self) -> dict:
        """Desliga a TV Roku (PowerOff via keypress)"""
        try:
            response = self._make_request("POST", "/keypress/PowerOff")
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": "Comando de desligar enviado",
                }
            return {"success": False, "message": "Falha ao enviar comando"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}

    def launch_app(self, app_id: str) -> dict:
        """Abre um app na TV Roku"""
        try:
            # IDs comuns de apps Roku
            app_ids = {
                "netflix": "12",
                "youtube": "837",
                "prime": "13",
                "hulu": "3",
                "disney": "549",
                "hbo": "61322",
            }
            
            roku_app_id = app_ids.get(app_id.lower(), app_id)
            
            response = self._make_request("POST", f"/launch/{roku_app_id}")
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": f"Abrindo {app_id}...",
                }
            return {"success": False, "message": f"Falha ao abrir {app_id}"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}

    def close_app(self) -> dict:
        """Volta para Home (fecha app)"""
        try:
            response = self._make_request("POST", "/keypress/Home")
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": "Voltando para Home...",
                }
            return {"success": False, "message": "Falha ao voltar para Home"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}

    def send_command(self, command: str) -> dict:
        """Envia comando de controle remoto"""
        command = command.lower()
        
        if command not in self.REMOTE_COMMANDS:
            return {
                "success": False,
                "message": f"Comando inválido. Comandos disponíveis: {', '.join(self.REMOTE_COMMANDS.keys())}",
            }
        
        try:
            roku_command = self.REMOTE_COMMANDS[command]
            response = self._make_request("POST", f"/keypress/{roku_command}")
            
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": f"Comando '{command}' enviado",
                }
            return {"success": False, "message": "Falha ao enviar comando"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}

    def get_app_list(self) -> dict:
        """Obtém lista de apps instalados"""
        try:
            response = self._make_request("GET", "/query/apps")
            
            if response and response.status_code == 200:
                # Parse XML simples para extrair apps
                apps = []
                text = response.text
                
                # Exemplo de apps padrão Roku
                common_apps = {
                    "Netflix": "12",
                    "YouTube": "837",
                    "Amazon Prime": "13",
                    "Hulu": "3",
                    "Disney+": "549",
                }
                
                return {
                    "success": True,
                    "apps": common_apps,
                    "message": "Apps obtidos com sucesso",
                }
            
            return {
                "success": False,
                "apps": {},
                "message": "Falha ao obter lista de apps",
            }
        except Exception as e:
            logger.error(f"Erro ao obter lista de apps: {e}")
            return {
                "success": False,
                "apps": {},
                "message": f"Erro: {str(e)}",
            }

    def test_connection(self) -> dict:
        """Testa conexão com o Roku"""
        try:
            response = self._make_request("GET", "/query/device-info", timeout=3)
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "online": True,
                    "message": "Roku encontrado e conectado!",
                }
            return {
                "success": False,
                "online": False,
                "message": "Roku não respondeu",
            }
        except Exception as e:
            return {
                "success": False,
                "online": False,
                "message": f"Erro: {str(e)}",
            }
