"""Gerenciamento de cômodos e vínculos com dispositivos."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Device as DeviceModel, Room as RoomModel


class RoomService:
    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(str(name or "").strip().split())[:100]

    @staticmethod
    def get_rooms(db: Session):
        return db.query(RoomModel).order_by(RoomModel.name.asc()).all()

    @staticmethod
    def get_room(db: Session, room_id: int):
        return db.query(RoomModel).filter(RoomModel.id == room_id).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        normalized = RoomService.normalize_name(name)
        if not normalized:
            return None
        return db.query(RoomModel).filter(func.lower(RoomModel.name) == normalized.lower()).first()

    @staticmethod
    def ensure_room(db: Session, name: str):
        normalized = RoomService.normalize_name(name)
        if not normalized:
            return None
        room = RoomService.get_by_name(db, normalized)
        if room:
            return room
        room = RoomModel(name=normalized)
        db.add(room)
        db.flush()
        return room

    @staticmethod
    def create_room(db: Session, name: str):
        normalized = RoomService.normalize_name(name)
        if not normalized:
            raise ValueError("Informe o nome do cômodo")
        if RoomService.get_by_name(db, normalized):
            raise ValueError("Este cômodo já existe")
        room = RoomModel(name=normalized)
        db.add(room)
        db.commit()
        db.refresh(room)
        return room

    @staticmethod
    def delete_room(db: Session, room_id: int) -> bool:
        room = RoomService.get_room(db, room_id)
        if not room:
            return False
        db.query(DeviceModel).filter(func.lower(DeviceModel.room) == room.name.lower()).update(
            {DeviceModel.room: None},
            synchronize_session=False,
        )
        db.delete(room)
        db.commit()
        return True

    @staticmethod
    def sync_existing_rooms(db: Session) -> None:
        changed = False
        names = db.query(DeviceModel.room).filter(DeviceModel.room.isnot(None)).distinct().all()
        for (name,) in names:
            normalized = RoomService.normalize_name(name)
            if normalized and not RoomService.get_by_name(db, normalized):
                db.add(RoomModel(name=normalized))
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def assign_device(db: Session, device_id: int, room_id: int | None):
        device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
        if not device:
            return None
        room = RoomService.get_room(db, room_id) if room_id else None
        if room_id and not room:
            raise ValueError("Cômodo não encontrado")
        device.room = room.name if room else None
        device.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(device)
        return device
