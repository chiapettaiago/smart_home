#!/usr/bin/env python3
"""Script para iniciar o servidor de automacao residencial."""

from app.config import DEBUG, HOST, PORT
from app.main import app


def main():
    print(f"Smart Home Server - Iniciando em http://{HOST}:{PORT}")
    print(f"Dashboard disponivel em http://{HOST}:{PORT}/")
    print(f"API disponivel em http://{HOST}:{PORT}/api/info")
    print(f"Debug: {DEBUG}\n")
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
