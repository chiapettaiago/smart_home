#!/usr/bin/env python3
"""Testa localmente se o celular configurado aparece conectado ao Vivo Box."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PRESENCE_PHONE_MAC, VIVO_ROUTER_PASSWORD, VIVO_ROUTER_URL, VIVO_ROUTER_USERNAME
from app.integrations.vivo_router import VivoRouterIntegration


def main():
    required = {
        "VIVO_ROUTER_URL": VIVO_ROUTER_URL,
        "VIVO_ROUTER_USERNAME": VIVO_ROUTER_USERNAME,
        "VIVO_ROUTER_PASSWORD": VIVO_ROUTER_PASSWORD,
        "PRESENCE_PHONE_MAC": PRESENCE_PHONE_MAC,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Configure no .env: {', '.join(missing)}")

    result = VivoRouterIntegration(
        base_url=VIVO_ROUTER_URL,
        username=VIVO_ROUTER_USERNAME,
        password=VIVO_ROUTER_PASSWORD,
    ).is_connected(PRESENCE_PHONE_MAC)
    if not result.get("success"):
        raise SystemExit(result.get("message", "Falha ao consultar o Vivo Box."))
    print("Celular conectado ao Wi-Fi." if result["connected"] else "Celular não encontrado entre os clientes conectados.")


if __name__ == "__main__":
    main()
