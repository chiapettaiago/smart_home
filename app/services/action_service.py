from sqlalchemy.orm import Session
from app.models import ActionLog as ActionLogModel
from datetime import datetime
from app.config import ALLOWED_ACTIONS
from app.config import HOME_ASSISTANT_TOKEN, HOME_ASSISTANT_URL
from app.integrations.home_assistant import HomeAssistantIntegration
from app.integrations.roku import RokuIntegration
import logging

logger = logging.getLogger(__name__)


class ActionService:
    """Serviço para executar ações em dispositivos"""

    ALLOWED_ACTIONS = ALLOWED_ACTIONS
    ACTION_SPECS = {
        "turn_on": {"label": "Ligar"},
        "turn_off": {"label": "Desligar"},
        "toggle": {"label": "Alternar estado"},
        "restart": {"label": "Reiniciar"},
        "lock": {"label": "Bloquear"},
        "unlock": {"label": "Desbloquear"},
        "get_status": {"label": "Consultar status"},
        "open_app": {
            "label": "Abrir aplicativo",
            "params": [
                {
                    "name": "app_name",
                    "label": "Aplicativo",
                    "type": "select",
                    "options": ["netflix", "youtube", "prime", "hulu", "disney", "hbo"],
                }
            ],
        },
        "close_app": {"label": "Fechar aplicativo / ir para Home"},
        "play": {"label": "Reproduzir"},
        "pause": {"label": "Pausar"},
        "set_brightness": {
            "label": "Ajustar brilho",
            "params": [{"name": "brightness", "label": "Brilho", "type": "number", "min": 1, "max": 255, "value": 160}],
        },
        "set_color_temp": {
            "label": "Ajustar temperatura de cor",
            "params": [{"name": "color_temp", "label": "Temperatura de cor", "type": "number", "min": 153, "max": 500, "value": 300}],
        },
        "set_rgb_color": {
            "label": "Ajustar cor",
            "params": [{"name": "rgb_color", "label": "Cor", "type": "color", "value": "#f59b63"}],
        },
        "set_percentage": {
            "label": "Ajustar percentual",
            "params": [{"name": "percentage", "label": "Percentual", "type": "number", "min": 0, "max": 100, "value": 50}],
        },
        "set_temperature": {
            "label": "Ajustar temperatura",
            "params": [{"name": "temperature", "label": "Temperatura", "type": "number", "min": 16, "max": 30, "step": 0.5, "value": 22}],
        },
        "set_hvac_mode": {
            "label": "Alterar modo HVAC",
            "params": [{"name": "hvac_mode", "label": "Modo HVAC", "type": "select", "options": ["auto", "heat", "cool", "dry", "fan_only", "off"]}],
        },
        "set_preset_mode": {
            "label": "Alterar preset",
            "params": [{"name": "preset_mode", "label": "Preset", "type": "select", "options": ["none", "eco", "comfort", "sleep", "boost"]}],
        },
        "set_fan_mode": {
            "label": "Alterar modo do ventilador",
            "params": [{"name": "fan_mode", "label": "Modo do ventilador", "type": "select", "options": ["auto", "low", "medium", "high"]}],
        },
        "set_swing_mode": {
            "label": "Alterar oscilação",
            "params": [{"name": "swing_mode", "label": "Oscilação", "type": "select", "options": ["off", "on", "vertical", "horizontal", "both"]}],
        },
    }
    TUYA_DOMAIN_ACTIONS = {
        "light": ["turn_on", "turn_off", "toggle", "get_status", "set_brightness", "set_color_temp", "set_rgb_color"],
        "switch": ["turn_on", "turn_off", "toggle", "get_status"],
        "fan": ["turn_on", "turn_off", "toggle", "get_status", "set_percentage", "set_preset_mode"],
        "climate": ["turn_on", "turn_off", "get_status", "set_temperature", "set_hvac_mode", "set_preset_mode", "set_fan_mode", "set_swing_mode"],
        "scene": ["turn_on", "get_status"],
    }

    @staticmethod
    def is_action_allowed(action: str) -> bool:
        """Verifica se a ação está na whitelist"""
        return action.lower() in ActionService.ALLOWED_ACTIONS

    @staticmethod
    def get_available_actions(device) -> list:
        """Lista apenas ações compatíveis com o tipo e a entidade do dispositivo."""
        if device.type == "roku":
            action_names = ["turn_on", "turn_off", "play", "pause", "get_status", "open_app", "close_app"]
        elif device.type == "tuya":
            metadata = device.device_metadata or {}
            entity_id = metadata.get("entity_id") or metadata.get("external_id") or ""
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            action_names = ActionService.TUYA_DOMAIN_ACTIONS.get(domain, ["turn_on", "turn_off", "get_status"])
        else:
            action_names = ["turn_on", "turn_off", "restart", "lock", "unlock", "get_status"]
        return [
            {"name": action_name, **ActionService.ACTION_SPECS[action_name]}
            for action_name in action_names
        ]

    @staticmethod
    def is_action_available_for_device(device, action: str) -> bool:
        return action in {item["name"] for item in ActionService.get_available_actions(device)}

    @staticmethod
    def validate_action_params(device, action: str, params: dict = None) -> str:
        """Valida parâmetros antes de executar comandos recebidos externamente."""
        available_action = next(
            (item for item in ActionService.get_available_actions(device) if item["name"] == action),
            None,
        )
        if not available_action:
            return f"A ação '{action}' não está disponível para '{device.name}'."
        params = params or {}
        if not isinstance(params, dict):
            return f"Os parâmetros de '{action}' são inválidos."
        for spec in available_action.get("params", []):
            value = params.get(spec["name"])
            if value is None or value == "":
                return f"Informe '{spec['label']}' para executar '{available_action['label']}'."
            if spec["type"] == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return f"O valor de '{spec['label']}' deve ser numérico."
                if value < spec.get("min", value) or value > spec.get("max", value):
                    return f"O valor de '{spec['label']}' está fora do intervalo permitido."
            if spec["type"] == "select" and value not in spec["options"]:
                return f"O valor de '{spec['label']}' não é permitido."
            if spec["type"] == "color" and (
                not isinstance(value, list)
                or len(value) != 3
                or not all(isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255 for channel in value)
            ):
                return f"O valor de '{spec['label']}' deve ser uma cor RGB válida."
        return ""

    @staticmethod
    def log_action(db: Session, device_id: int, action: str, params: dict = None, 
                   status: str = "pending", response: dict = None) -> ActionLogModel:
        """Registra uma ação no log"""
        action_log = ActionLogModel(
            device_id=device_id,
            action=action,
            params=params,
            status=status,
            response=response,
            executed_at=datetime.utcnow(),
        )
        db.add(action_log)
        db.commit()
        db.refresh(action_log)
        logger.info(f"Ação registrada: {action} no dispositivo {device_id}")
        return action_log

    @staticmethod
    def get_action_logs(db: Session, device_id: int = None, limit: int = 50):
        """Obtém logs de ações"""
        query = db.query(ActionLogModel)
        if device_id:
            query = query.filter(ActionLogModel.device_id == device_id)
        return query.order_by(ActionLogModel.executed_at.desc()).limit(limit).all()

    @staticmethod
    def execute_action(device, action: str, params: dict = None) -> dict:
        """Executa a ação real usando as integrações correspondentes"""
        logger.info(f"Executando ação real: {action} no dispositivo {device.id} tipo {device.type}")

        if device.type == "roku" and device.ip:
            roku = RokuIntegration(device.ip)
            if action.lower() == "turn_on":
                result = roku.turn_on()
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}
            elif action.lower() == "turn_off":
                result = roku.turn_off()
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}
            elif action.lower() == "get_status":
                result = roku.get_status()
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}
            elif action.lower() == "open_app" and params and "app_name" in params:
                result = roku.launch_app(params["app_name"])
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}
            elif action.lower() == "close_app":
                result = roku.close_app()
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}
            elif action.lower() in {"play", "pause"}:
                result = roku.send_command(action.lower())
                return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

        if device.type == "tuya":
            metadata = device.device_metadata or {}
            entity_id = metadata.get("entity_id") or metadata.get("external_id")
            ha_token = metadata.get("ha_token") or HOME_ASSISTANT_TOKEN
            ha_url = metadata.get("ha_url") or HOME_ASSISTANT_URL
            action_name = action.lower()

            if entity_id:
                ha = HomeAssistantIntegration(base_url=ha_url, token=ha_token)

                simple_actions = {
                    "turn_on": lambda: ha.turn_on(entity_id),
                    "turn_off": lambda: ha.turn_off(entity_id),
                    "toggle": lambda: ha.toggle(entity_id),
                    "get_status": lambda: ha.get_state(entity_id),
                }
                if action_name in simple_actions:
                    result = simple_actions[action_name]()
                    return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

                mapped_services = {
                    "set_brightness": ("turn_on", {"brightness": (params or {}).get("brightness")}),
                    "set_hs_color": ("turn_on", {"hs_color": (params or {}).get("hs_color")}),
                    "set_percentage": ("set_percentage", {"percentage": (params or {}).get("percentage")}),
                    "set_temperature": ("set_temperature", {"temperature": (params or {}).get("temperature")}),
                    "set_hvac_mode": ("set_hvac_mode", {"hvac_mode": (params or {}).get("hvac_mode")}),
                    "set_preset_mode": ("set_preset_mode", {"preset_mode": (params or {}).get("preset_mode")}),
                    "set_fan_mode": ("set_fan_mode", {"fan_mode": (params or {}).get("fan_mode")}),
                    "set_swing_mode": ("set_swing_mode", {"swing_mode": (params or {}).get("swing_mode")}),
                }
                if action_name == "set_color_temp":
                    color_temp = (params or {}).get("color_temp")
                    if color_temp is None:
                        return {
                            "success": False,
                            "message": "Parâmetros obrigatórios ausentes para set_color_temp.",
                            "data": {"required_params": ["color_temp"]},
                        }
                    result = ha.set_light_color_temp(entity_id, color_temp)
                    return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

                if action_name == "set_rgb_color":
                    rgb_color = (params or {}).get("rgb_color")
                    if rgb_color is None:
                        return {
                            "success": False,
                            "message": "Parâmetros obrigatórios ausentes para set_rgb_color.",
                            "data": {"required_params": ["rgb_color"]},
                        }
                    result = ha.set_light_rgb_color(entity_id, rgb_color)
                    return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

                if action_name in mapped_services:
                    service_name, service_data = mapped_services[action_name]
                    filtered_data = {key: value for key, value in service_data.items() if value is not None}
                    if not filtered_data:
                        return {
                            "success": False,
                            "message": f"Parâmetros obrigatórios ausentes para {action_name}.",
                            "data": {"required_params": list(service_data.keys())},
                        }
                    result = ha.set_state(entity_id, service_name, filtered_data)
                    return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

                if action_name == "tuya_command":
                    command = (params or {}).get("command")
                    command_params = (params or {}).get("command_params") or {}
                    if not command:
                        return {"success": False, "message": "Informe params.command para tuya_command.", "data": None}
                    result = ha.set_state(entity_id, command, command_params)
                    return {"success": result.get("success", False), "message": result.get("message", ""), "data": result}

        # Fallback para o mock se não houver integração implementada
        return ActionService.execute_action_mock(device.id, action, params)

    @staticmethod
    def execute_action_mock(device_id: int, action: str, params: dict = None) -> dict:
        """
        Executa uma ação mockada (sem integração real).
        Retorna estrutura pronta para ser expandida com integrações reais.
        """
        logger.info(f"Executando ação mockada: {action} no dispositivo {device_id} com params: {params}")

        # Simulação de execução
        if action.lower() == "turn_on":
            return {
                "success": True,
                "message": f"Dispositivo {device_id} ligado com sucesso",
                "data": {"action": "turn_on", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "turn_off":
            return {
                "success": True,
                "message": f"Dispositivo {device_id} desligado com sucesso",
                "data": {"action": "turn_off", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "restart":
            return {
                "success": True,
                "message": f"Dispositivo {device_id} reiniciando",
                "data": {"action": "restart", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "get_status":
            return {
                "success": True,
                "message": f"Status obtido",
                "data": {"status": "online", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "lock":
            return {
                "success": True,
                "message": f"Dispositivo {device_id} bloqueado",
                "data": {"action": "lock", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "unlock":
            return {
                "success": True,
                "message": f"Dispositivo {device_id} desbloqueado",
                "data": {"action": "unlock", "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "open_app":
            app_name = params.get("app_name", "app") if params else "app"
            return {
                "success": True,
                "message": f"Abrindo aplicativo {app_name}",
                "data": {"action": "open_app", "app": app_name, "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() == "close_app":
            app_name = params.get("app_name", "app") if params else "app"
            return {
                "success": True,
                "message": f"Fechando aplicativo {app_name}",
                "data": {"action": "close_app", "app": app_name, "timestamp": datetime.utcnow().isoformat()},
            }
        elif action.lower() in {"play", "pause"}:
            return {
                "success": True,
                "message": "Reproduzindo mídia" if action.lower() == "play" else "Pausando mídia",
                "data": {"action": action.lower(), "timestamp": datetime.utcnow().isoformat()},
            }
        else:
            return {
                "success": False,
                "message": f"Ação {action} não implementada",
                "data": None,
            }

    @staticmethod
    def get_recent_actions(db: Session, limit: int = 10):
        """Obtém ações recentes de todos os dispositivos"""
        return db.query(ActionLogModel).order_by(ActionLogModel.executed_at.desc()).limit(limit).all()
