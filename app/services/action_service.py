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

    @staticmethod
    def is_action_allowed(action: str) -> bool:
        """Verifica se a ação está na whitelist"""
        return action.lower() in ActionService.ALLOWED_ACTIONS

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
                    "set_color_temp": ("turn_on", {"color_temp": (params or {}).get("color_temp")}),
                    "set_hs_color": ("turn_on", {"hs_color": (params or {}).get("hs_color")}),
                    "set_rgb_color": ("turn_on", {"rgb_color": (params or {}).get("rgb_color")}),
                    "set_percentage": ("set_percentage", {"percentage": (params or {}).get("percentage")}),
                    "set_temperature": ("set_temperature", {"temperature": (params or {}).get("temperature")}),
                    "set_hvac_mode": ("set_hvac_mode", {"hvac_mode": (params or {}).get("hvac_mode")}),
                    "set_preset_mode": ("set_preset_mode", {"preset_mode": (params or {}).get("preset_mode")}),
                    "set_fan_mode": ("set_fan_mode", {"fan_mode": (params or {}).get("fan_mode")}),
                    "set_swing_mode": ("set_swing_mode", {"swing_mode": (params or {}).get("swing_mode")}),
                }
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
