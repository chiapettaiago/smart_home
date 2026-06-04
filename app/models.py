from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # tuya, roku, android, pc_windows, pc_linux, sensor, other
    room = Column(String(100), nullable=True)
    ip = Column(String(45), nullable=True)
    token = Column(String(512), nullable=True)  # Token/chave opcional para autenticação
    status = Column(String(20), default="offline")  # online, offline
    device_metadata = Column(JSON, default=dict)  # Dados adicionais em JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    energy_readings = relationship("EnergyReading", back_populates="device", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="device", cascade="all, delete-orphan")


class EnergyReading(Base):
    __tablename__ = "energy_readings"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    watts = Column(Float, nullable=True)
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    kwh = Column(Float, nullable=True)  # Acumulado
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    device = relationship("Device", back_populates="energy_readings")


class Automation(Base):
    __tablename__ = "automations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    trigger = Column(String(100), nullable=False)  # Tipo de gatilho: time, device_status, presence, etc
    condition = Column(JSON, nullable=True)  # Condições em JSON
    actions = Column(JSON, nullable=False, default=list)  # Lista de ações em JSON
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    execution_logs = relationship("AutomationLog", back_populates="automation", cascade="all, delete-orphan")


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(Integer, primary_key=True, index=True)
    automation_id = Column(Integer, ForeignKey("automations.id"), nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)
    result = Column(String(20))  # success, failed
    message = Column(String(1000), nullable=True)

    # Relationships
    automation = relationship("Automation", back_populates="execution_logs")


class Presence(Base):
    __tablename__ = "presence"

    id = Column(Integer, primary_key=True, index=True)
    user = Column(String(255), nullable=False, unique=True, index=True)
    is_home = Column(Boolean, default=False)
    last_update = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    phone_mac = Column(String(17), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    action = Column(String(100), nullable=False)
    params = Column(JSON, nullable=True)
    status = Column(String(20), default="pending")  # pending, success, failed
    response = Column(JSON, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    device = relationship("Device", back_populates="action_logs")
