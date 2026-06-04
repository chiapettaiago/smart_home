from sqlalchemy.orm import Session
from app.models import Automation as AutomationModel, AutomationLog as AutomationLogModel
from datetime import datetime
import logging
import threading

from app.services.action_service import ActionService
from app.services.device_service import DeviceService
from app.services.environment_service import EnvironmentService
from app.services.presence_service import PresenceService

logger = logging.getLogger(__name__)
_automation_lock = threading.Lock()
_device_states = {}
_monitor_lock = threading.Lock()
_monitor_stop_event = threading.Event()
_monitor_thread = None
_automation_context_runs = set()
_automation_condition_states = {}


class AutomationService:
    """Serviço para gerenciar automações"""

    @staticmethod
    def get_automations(db: Session, skip: int = 0, limit: int = 100):
        """Obtém lista de automações"""
        return db.query(AutomationModel).offset(skip).limit(limit).all()

    @staticmethod
    def get_automation(db: Session, automation_id: int) -> AutomationModel:
        """Obtém uma automação específica"""
        return db.query(AutomationModel).filter(AutomationModel.id == automation_id).first()

    @staticmethod
    def create_automation(db: Session, automation_data: dict) -> AutomationModel:
        """Cria uma nova automação"""
        automation = AutomationModel(**automation_data)
        db.add(automation)
        db.commit()
        db.refresh(automation)
        logger.info(f"Automação criada: {automation.id} - {automation.name}")
        return automation

    @staticmethod
    def update_automation(db: Session, automation_id: int, automation_data: dict) -> AutomationModel:
        """Atualiza uma automação"""
        automation = db.query(AutomationModel).filter(AutomationModel.id == automation_id).first()
        if not automation:
            return None

        for key, value in automation_data.items():
            if value is not None:
                setattr(automation, key, value)

        automation.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(automation)
        logger.info(f"Automação atualizada: {automation_id}")
        return automation

    @staticmethod
    def delete_automation(db: Session, automation_id: int) -> bool:
        """Deleta uma automação"""
        automation = db.query(AutomationModel).filter(AutomationModel.id == automation_id).first()
        if automation:
            db.delete(automation)
            db.commit()
            logger.info(f"Automação deletada: {automation_id}")
            return True
        return False

    @staticmethod
    def log_execution(db: Session, automation_id: int, result: str, message: str = None) -> AutomationLogModel:
        """Registra execução de uma automação"""
        log = AutomationLogModel(
            automation_id=automation_id,
            result=result,
            message=message,
            executed_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        logger.info(f"Execução de automação registrada: {automation_id} - {result}")
        return log

    @staticmethod
    def get_active_automations(db: Session):
        """Obtém apenas automações ativas"""
        return db.query(AutomationModel).filter(AutomationModel.active == True).all()

    @staticmethod
    def get_execution_logs(db: Session, automation_id: int = None, limit: int = 50):
        """Obtém logs de execução de automações"""
        query = db.query(AutomationLogModel)
        if automation_id:
            query = query.filter(AutomationLogModel.automation_id == automation_id)
        return query.order_by(AutomationLogModel.executed_at.desc()).limit(limit).all()

    @staticmethod
    def start_device_state_monitor(state_loader, interval_seconds: int = 5) -> None:
        """Monitora mudanças de estado mesmo quando o dashboard não está aberto."""
        global _monitor_thread

        with _monitor_lock:
            if _monitor_thread and _monitor_thread.is_alive():
                return
            _monitor_stop_event.clear()
            _monitor_thread = threading.Thread(
                target=AutomationService._run_device_state_monitor,
                args=(state_loader, interval_seconds),
                name="automation-device-state-monitor",
                daemon=True,
            )
            _monitor_thread.start()

    @staticmethod
    def _run_device_state_monitor(state_loader, interval_seconds: int) -> None:
        from app.database import SessionLocal

        while not _monitor_stop_event.is_set():
            db = SessionLocal()
            try:
                devices = DeviceService.get_devices(db, limit=1000)
                live_device_data = state_loader(devices)
                AutomationService.process_device_state_changes(db, live_device_data)
                AutomationService.process_context_automations(db)
            except Exception:
                logger.exception("Falha ao processar mudanças de estado dos dispositivos")
            finally:
                db.close()
            _monitor_stop_event.wait(interval_seconds)

    @staticmethod
    def process_device_state_changes(db: Session, live_device_data: dict) -> list:
        """Executa automações quando um dispositivo entra no estado configurado."""
        executed = []
        with _automation_lock:
            previous_states = dict(_device_states)
            current_states = {}
            for device_id, data in live_device_data.items():
                if data.get("power_state") in {"on", "off"}:
                    current_states[(device_id, "power")] = data["power_state"]
                if data.get("status") in {"online", "offline"}:
                    current_states[(device_id, "availability")] = data["status"]
            _device_states.update(current_states)

            for automation in AutomationService.get_active_automations(db):
                if automation.trigger != "device_status":
                    continue
                condition = automation.condition or {}
                device_id = condition.get("device_id")
                expected_state = condition.get("state")
                state_kind = "power" if expected_state in {"on", "off"} else "availability"
                state_key = (device_id, state_kind)
                current_state = current_states.get(state_key)
                previous_state = previous_states.get(state_key)
                if current_state != expected_state or previous_state in {None, expected_state}:
                    continue
                context = EnvironmentService.get_context()
                if not AutomationService._additional_conditions_match(db, automation, context, live_device_data):
                    continue
                AutomationService._execute_automation_actions(db, automation)
                executed.append(automation.id)
        return executed

    @staticmethod
    def process_context_automations(db: Session) -> list:
        """Executa automações baseadas em hora, presença, calendário, sol e clima."""
        executed = []
        context = EnvironmentService.get_context()
        with _automation_lock:
            for automation in AutomationService.get_active_automations(db):
                if automation.trigger == "device_status" or automation.trigger == "manual":
                    continue
                if AutomationService._context_trigger_due(db, automation, context):
                    AutomationService._execute_automation_actions(db, automation)
                    executed.append(automation.id)
        return executed

    @staticmethod
    def _context_trigger_due(db: Session, automation, context: dict) -> bool:
        condition = automation.condition or {}
        trigger = automation.trigger
        if trigger == "time":
            if context.get("time") != condition.get("time"):
                return False
            if not AutomationService._additional_conditions_match(db, automation, context):
                return False
            return AutomationService._claim_once(automation.id, f"time:{context['calendar']['date']}:{condition.get('time')}")

        if trigger == "sun":
            if not EnvironmentService.sun_event_due(condition, context):
                return False
            if not AutomationService._additional_conditions_match(db, automation, context):
                return False
            event = condition.get("event")
            offset = int(condition.get("offset_minutes") or 0)
            return AutomationService._claim_once(automation.id, f"sun:{context['calendar']['date']}:{event}:{offset}")

        if trigger == "presence":
            users = {presence.user: presence.is_home for presence in PresenceService.get_all_presence(db)}
            is_due = users.get(condition.get("user")) == condition.get("is_home")
            is_due = is_due and AutomationService._additional_conditions_match(db, automation, context)
            return AutomationService._claim_on_transition(automation.id, is_due)

        if trigger == "weather":
            is_due = EnvironmentService.matches_weather(condition, context)
            is_due = is_due and AutomationService._additional_conditions_match(db, automation, context)
            return AutomationService._claim_on_transition(automation.id, is_due, fire_initial=True)

        if trigger == "calendar":
            is_due = EnvironmentService.matches_calendar(condition, context)
            if not is_due or not AutomationService._additional_conditions_match(db, automation, context):
                return False
            key_suffix = condition.get("mode", "calendar")
            return AutomationService._claim_once(automation.id, f"calendar:{context['calendar']['date']}:{key_suffix}")

        return False

    @staticmethod
    def _additional_conditions_match(db: Session, automation, context: dict, live_device_data: dict = None) -> bool:
        conditions = (automation.condition or {}).get("_conditions") or {}
        items = conditions.get("items") or []
        if not items:
            return True
        results = [
            AutomationService._condition_item_matches(db, item, context, live_device_data or {})
            for item in items
        ]
        return any(results) if conditions.get("mode") == "any" else all(results)

    @staticmethod
    def _condition_item_matches(db: Session, item: dict, context: dict, live_device_data: dict) -> bool:
        condition_type = item.get("type")
        condition = item.get("condition") or {}
        if condition_type == "manual":
            return True
        if condition_type == "time":
            return context.get("time") == condition.get("time")
        if condition_type == "sun":
            return EnvironmentService.sun_event_due(condition, context)
        if condition_type == "weather":
            return EnvironmentService.matches_weather(condition, context)
        if condition_type == "calendar":
            return EnvironmentService.matches_calendar(condition, context)
        if condition_type == "presence":
            users = {presence.user: presence.is_home for presence in PresenceService.get_all_presence(db)}
            return users.get(condition.get("user")) == condition.get("is_home")
        if condition_type == "device_status":
            device_id = condition.get("device_id")
            expected_state = condition.get("state")
            data = live_device_data.get(device_id) or {}
            if not data:
                device = DeviceService.get_device(db, device_id)
                metadata = device.device_metadata or {} if device else {}
                data = {
                    "power_state": metadata.get("power_state") or metadata.get("ha_state"),
                    "status": device.status if device else None,
                }
            return data.get("power_state") == expected_state or data.get("status") == expected_state
        return False

    @staticmethod
    def _claim_once(automation_id: int, key: str) -> bool:
        run_key = (automation_id, key)
        if run_key in _automation_context_runs:
            return False
        _automation_context_runs.add(run_key)
        return True

    @staticmethod
    def _claim_on_transition(automation_id: int, is_due: bool, fire_initial: bool = False) -> bool:
        previous = _automation_condition_states.get(automation_id)
        _automation_condition_states[automation_id] = bool(is_due)
        return bool(is_due) and (previous is False or (fire_initial and previous is None))

    @staticmethod
    def _execute_automation_actions(db: Session, automation) -> None:
        messages = []
        success = True
        for item in automation.actions or []:
            device = DeviceService.get_device(db, item.get("device_id"))
            action = item.get("action", "")
            params = item.get("params") or {}
            if not device:
                success = False
                messages.append("Dispositivo da ação não encontrado.")
                continue
            validation_error = ActionService.validate_action_params(device, action, params)
            if validation_error:
                success = False
                messages.append(validation_error)
                continue
            result = ActionService.execute_action(device, action, params)
            result_success = bool(result.get("success"))
            success = success and result_success
            messages.append(f"{device.name}: {result.get('message') or 'Comando processado.'}")
            try:
                ActionService.log_action(
                    db,
                    device_id=device.id,
                    action=action,
                    params=params or None,
                    status="success" if result_success else "failed",
                    response=result.get("data"),
                )
            except Exception:
                db.rollback()
                logger.exception("Falha ao registrar ação da automação %s", automation.id)
        AutomationService.log_execution(
            db,
            automation_id=automation.id,
            result="success" if success else "failed",
            message="; ".join(messages) or "Automação sem ações.",
        )
