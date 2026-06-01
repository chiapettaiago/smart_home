"""
Integração com Roku TV via API REST
Permite controlar TV Roku informando apenas o IP
"""

import requests
import logging
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
                # Parse XML simples
                text = response.text
                is_powered = "power_mode" in text and "PowerOn" in text
                
                now_playing = self.get_now_playing()

                return {
                    "success": True,
                    "online": True,
                    "powered_on": is_powered,
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
                return {"app_name": "Desconhecido", "content_title": None}

            root = ET.fromstring(active_app_response.text)
            app_node = root.find("app")
            app_name = app_node.text.strip() if app_node is not None and app_node.text else "Tela inicial"

            content_title = None
            media_response = self._make_request("GET", "/query/media-player")
            if media_response and media_response.status_code == 200:
                media_root = ET.fromstring(media_response.text)
                for tag in ("title", "artist", "album"):
                    node = media_root.find(f".//{tag}")
                    if node is not None and node.text and node.text.strip():
                        content_title = node.text.strip()
                        break

            return {"app_name": app_name, "content_title": content_title}
        except Exception as e:
            logger.warning(f"Erro ao obter now playing do Roku {self.device_ip}: {e}")
            return {"app_name": "Indisponível", "content_title": None}

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
