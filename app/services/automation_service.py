from sqlalchemy.orm import Session
from app.models import Automation as AutomationModel, AutomationLog as AutomationLogModel
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


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
