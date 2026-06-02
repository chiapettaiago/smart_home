"""Detecção de presença no Vivo Box Askey RTF8225VW-SV."""

import ast
import re
from urllib.parse import urljoin

import requests

LAN_HOST_LIST_PATTERN = re.compile(r"var\s+lanHostList\s*=\s*(\[.*?\]);", re.DOTALL)
CLIENT_PAGES = (
    "/index_cliente.asp",
)


def normalize_mac(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value or "", flags=re.IGNORECASE).upper()


class VivoRouterIntegration:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 5):
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _encode_credential(value: str) -> str:
        return "".join(chr(ord(char) ^ 0x1F) for char in value)

    @staticmethod
    def _is_login_page(response) -> bool:
        return "te_acceso_router.cgi" in response.text or "Você não está Autenticado" in response.text

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    @staticmethod
    def _get_connected_macs(page: str) -> set:
        """Lê apenas clientes ativos; o roteador mantém clientes antigos na mesma página."""
        match = LAN_HOST_LIST_PATTERN.search(page)
        if not match:
            return None
        try:
            hosts = ast.literal_eval(match.group(1))
        except (SyntaxError, ValueError):
            return None
        return {
            normalize_mac(host[6])
            for host in hosts
            if isinstance(host, list)
            and len(host) > 6
            and str(host[0]) == "1"
            and normalize_mac(host[6])
        }

    def _login(self) -> dict:
        if not self.base_url or not self.username or not self.password:
            return {"success": False, "message": "Credenciais do Vivo Box não configuradas."}
        try:
            self.session.get(self._url("/login.asp"), timeout=self.timeout)
            response = self.session.post(
                self._url("/cgi-bin/te_acceso_router.cgi"),
                data={
                    "curWebPage": "/index.asp",
                    "loginUsername": self._encode_credential(self.username),
                    "loginPassword": self._encode_credential(self.password),
                },
                timeout=self.timeout,
                allow_redirects=True,
            )
            if self._is_login_page(response):
                return {"success": False, "message": "O Vivo Box recusou o login."}
            return {"success": True}
        except requests.RequestException as exc:
            return {"success": False, "message": f"Falha ao acessar o Vivo Box: {exc}"}

    def is_connected(self, mac_address: str) -> dict:
        target_mac = normalize_mac(mac_address)
        if len(target_mac) != 12:
            return {"success": False, "message": "MAC do celular inválido.", "connected": False}

        login = self._login()
        if not login.get("success"):
            return {**login, "connected": False}

        try:
            for path in CLIENT_PAGES:
                response = self.session.get(self._url(path), timeout=self.timeout)
                if self._is_login_page(response):
                    return {"success": False, "message": "Sessão do Vivo Box expirou.", "connected": False}
                page_macs = self._get_connected_macs(response.text)
                if page_macs is None:
                    return {"success": False, "message": "Não foi possível interpretar os clientes ativos do Vivo Box.", "connected": False}
                if target_mac in page_macs:
                    return {"success": True, "connected": True, "source_page": path}
            return {"success": True, "connected": False}
        except requests.RequestException as exc:
            return {"success": False, "message": f"Falha ao ler clientes do Vivo Box: {exc}", "connected": False}
