from sqlalchemy.orm import Session
from app.models import Device as DeviceModel
from datetime import datetime
import logging
from app.services.room_service import RoomService

logger = logging.getLogger(__name__)


class DeviceService:
    """Serviço para operações com dispositivos"""

    @staticmethod
    def get_devices(db: Session, skip: int = 0, limit: int = 100):
        """Obtém lista de dispositivos"""
        return db.query(DeviceModel).offset(skip).limit(limit).all()

    @staticmethod
    def get_device(db: Session, device_id: int):
        """Obtém um dispositivo específico"""
        return db.query(DeviceModel).filter(DeviceModel.id == device_id).first()

    @staticmethod
    def create_device(db: Session, device_data: dict):
        """Cria um novo dispositivo"""
        device_data = dict(device_data)
        if device_data.get("room"):
            device_data["room"] = RoomService.ensure_room(db, device_data["room"]).name
        db_device = DeviceModel(**device_data)
        db.add(db_device)
        db.commit()
        db.refresh(db_device)
        logger.info(f"Dispositivo criado: {db_device.id} - {db_device.name}")
        return db_device

    @staticmethod
    def update_device(db: Session, device_id: int, device_data: dict):
        """Atualiza um dispositivo"""
        device_data = dict(device_data)
        db_device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
        if not db_device:
            return None

        if device_data.get("room"):
            device_data["room"] = RoomService.ensure_room(db, device_data["room"]).name
        for key, value in device_data.items():
            if value is not None:
                setattr(db_device, key, value)

        db_device.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_device)
        logger.info(f"Dispositivo atualizado: {device_id}")
        return db_device

    @staticmethod
    def delete_device(db: Session, device_id: int):
        """Deleta um dispositivo"""
        db_device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
        if db_device:
            db.delete(db_device)
            db.commit()
            logger.info(f"Dispositivo deletado: {device_id}")
            return True
        return False

    @staticmethod
    def get_devices_by_room(db: Session, room: str):
        """Obtém dispositivos de um cômodo específico"""
        return db.query(DeviceModel).filter(DeviceModel.room == room).all()

    @staticmethod
    def get_online_devices(db: Session):
        """Obtém dispositivos online"""
        return db.query(DeviceModel).filter(DeviceModel.status == "online").all()

    @staticmethod
    def update_device_status(db: Session, device_id: int, status: str):
        """Atualiza o status de um dispositivo"""
        db_device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
        if db_device:
            db_device.status = status
            db_device.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(db_device)
            logger.info(f"Status do dispositivo {device_id} atualizado para: {status}")
            return db_device
        return None
