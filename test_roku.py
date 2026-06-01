#!/usr/bin/env python3
"""
Script de teste para integração Roku
Permite testar a integração sem precisar de uma TV Roku real
"""

import requests
import json
import os
import sys
from typing import Optional

# Configuração
API_URL = "http://localhost:8000"
API_TOKEN = os.getenv("API_TOKEN", "")

def auth_headers():
    return {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}

# Cores para output
class Colors:
    OK = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")

def print_success(msg):
    print(f"{Colors.OK}✓{Colors.END} {msg}")

def print_warning(msg):
    print(f"{Colors.WARNING}⚠{Colors.END} {msg}")

def print_error(msg):
    print(f"{Colors.ERROR}✗{Colors.END} {msg}")

def test_discover(ip: str):
    """Testa descoberta de Roku"""
    print_info(f"Testando descoberta de Roku em {ip}...")
    
    try:
        response = requests.post(
            f"{API_URL}/roku/discover",
            json={"ip": ip},
            headers=auth_headers(),
            timeout=10
        )
        
        data = response.json()
        
        if data.get("success"):
            print_success(f"Roku encontrado em {ip}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        else:
            print_warning(f"Roku não encontrado: {data.get('message')}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return False
            
    except requests.exceptions.ConnectionError:
        print_error("Erro: Servidor não está rodando em http://localhost:8000")
        print_warning("Inicie o servidor com: python run.py")
        return False
    except Exception as e:
        print_error(f"Erro: {e}")
        return False

def test_register(ip: str, name: Optional[str] = None):
    """Testa registro de Roku"""
    print_info(f"Testando registro de Roku em {ip}...")
    
    device_name = name or f"Roku {ip}"
    
    try:
        response = requests.post(
            f"{API_URL}/roku/register",
            json={"ip": ip, "name": device_name},
            headers=auth_headers(),
            timeout=10
        )
        
        data = response.json()
        
        if data.get("success"):
            print_success(f"Roku registrado com sucesso!")
            device_id = data.get("device_id")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return device_id
        else:
            print_error(f"Erro ao registrar: {data.get('message')}")
            return None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None

def test_command(device_id: int, command: str, params: Optional[dict] = None):
    """Testa envio de comando para Roku"""
    print_info(f"Enviando comando '{command}' para dispositivo {device_id}...")
    
    try:
        response = requests.post(
            f"{API_URL}/roku/devices/{device_id}/control",
            json={"command": command, "params": params or {}},
            headers=auth_headers(),
            timeout=10
        )
        
        data = response.json()
        
        if data.get("success"):
            print_success(f"Comando '{command}' executado!")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_error(f"Erro ao executar comando: {data}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
    except Exception as e:
        print_error(f"Erro: {e}")

def test_status(device_id: int):
    """Testa obtenção de status"""
    print_info(f"Obtendo status do dispositivo {device_id}...")
    
    try:
        response = requests.get(
            f"{API_URL}/roku/devices/{device_id}/status",
            headers=auth_headers(),
            timeout=10
        )
        
        data = response.json()
        print_success("Status obtido!")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print_error(f"Erro: {e}")

def main():
    print("\n" + "="*60)
    print("  Smart Home - Teste de Integração Roku")
    print("="*60 + "\n")
    
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python test_roku.py <comando> [argumentos]")
        print("\nComandos disponíveis:")
        print("  discover <ip>              - Descobrir Roku pelo IP")
        print("  register <ip> [nome]       - Registrar Roku como dispositivo")
        print("  command <device_id> <cmd>  - Enviar comando para Roku")
        print("  status <device_id>         - Obter status do Roku")
        print("\nExemplos:")
        print("  python test_roku.py discover 192.168.1.100")
        print("  python test_roku.py register 192.168.1.100 'Roku Sala'")
        print("  python test_roku.py command 1 turn_on")
        print("  python test_roku.py command 1 launch_app netflix")
        print("  python test_roku.py status 1")
        return
    
    command = sys.argv[1].lower()
    
    if command == "discover" and len(sys.argv) > 2:
        ip = sys.argv[2]
        test_discover(ip)
        
    elif command == "register" and len(sys.argv) > 2:
        ip = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else None
        device_id = test_register(ip, name)
        if device_id:
            print_info(f"Use este device_id para controlar o Roku: {device_id}")
        
    elif command == "command" and len(sys.argv) > 3:
        device_id = int(sys.argv[2])
        cmd = sys.argv[3]
        
        # Parâmetros específicos para certos comandos
        params = {}
        if cmd == "launch_app" and len(sys.argv) > 4:
            params = {"app_id": sys.argv[4]}
        elif cmd == "send_command" and len(sys.argv) > 4:
            params = {"command": sys.argv[4]}
        
        test_command(device_id, cmd, params if params else None)
        
    elif command == "status" and len(sys.argv) > 2:
        device_id = int(sys.argv[2])
        test_status(device_id)
        
    else:
        print_error("Comando inválido ou argumentos faltando")

if __name__ == "__main__":
    main()
