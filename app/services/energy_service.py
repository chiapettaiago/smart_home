from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import EnergyReading as EnergyReadingModel
from app.models import Device as DeviceModel
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EnergyService:
    """Serviço para gerenciar leituras de energia"""

    @staticmethod
    def add_reading(db: Session, device_id: int, watts: float = None, voltage: float = None,
                   current: float = None, kwh: float = None) -> EnergyReadingModel:
        """Adiciona uma nova leitura de energia"""
        reading = EnergyReadingModel(
            device_id=device_id,
            watts=watts,
            voltage=voltage,
            current=current,
            kwh=kwh,
            timestamp=datetime.utcnow(),
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        logger.info(f"Leitura de energia registrada: dispositivo {device_id} - {watts}W")
        return reading

    @staticmethod
    def get_readings(db: Session, device_id: int = None, hours: int = 24, limit: int = 100):
        """Obtém leituras de energia dos últimos N horas"""
        query = db.query(EnergyReadingModel)

        if device_id:
            query = query.filter(EnergyReadingModel.device_id == device_id)

        start_time = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(EnergyReadingModel.timestamp >= start_time)

        return query.order_by(EnergyReadingModel.timestamp.desc()).limit(limit).all()

    @staticmethod
    def get_total_consumption(db: Session, hours: int = 24) -> dict:
        """Obtém consumo total nos últimos N horas"""
        start_time = datetime.utcnow() - timedelta(hours=hours)

        result = db.query(
            func.sum(EnergyReadingModel.watts).label("total_watts"),
            func.sum(EnergyReadingModel.kwh).label("total_kwh"),
            func.count(EnergyReadingModel.id).label("readings_count"),
            func.avg(EnergyReadingModel.watts).label("avg_watts"),
        ).filter(EnergyReadingModel.timestamp >= start_time).first()

        return {
            "total_watts": result.total_watts or 0,
            "total_kwh": result.total_kwh or 0,
            "readings_count": result.readings_count or 0,
            "avg_watts": result.avg_watts or 0,
        }

    @staticmethod
    def get_consumption_by_device(db: Session, hours: int = 24) -> list:
        """Obtém consumo por dispositivo nos últimos N horas"""
        start_time = datetime.utcnow() - timedelta(hours=hours)

        result = db.query(
            DeviceModel.id,
            DeviceModel.name,
            func.sum(EnergyReadingModel.watts).label("total_watts"),
            func.sum(EnergyReadingModel.kwh).label("total_kwh"),
            func.count(EnergyReadingModel.id).label("readings_count"),
        ).join(EnergyReadingModel).filter(
            EnergyReadingModel.timestamp >= start_time
        ).group_by(DeviceModel.id, DeviceModel.name).all()

        return [
            {
                "device_id": r[0],
                "device_name": r[1],
                "total_watts": r[2] or 0,
                "total_kwh": r[3] or 0,
                "readings_count": r[4] or 0,
            }
            for r in result
        ]

    @staticmethod
    def get_last_reading(db: Session, device_id: int) -> EnergyReadingModel:
        """Obtém a última leitura de um dispositivo"""
        return db.query(EnergyReadingModel).filter(
            EnergyReadingModel.device_id == device_id
        ).order_by(EnergyReadingModel.timestamp.desc()).first()
