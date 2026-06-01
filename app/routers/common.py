from datetime import date, datetime

from flask import jsonify, session

from app.database import SessionLocal
from app.security import is_api_token_valid


def get_db():
    return SessionLocal()


def verify_token():
    if not session.get("authenticated") and not is_api_token_valid():
        return jsonify({"detail": "Autenticação inválida"}), 401
    return None


def error(message, status_code):
    return jsonify({"detail": message}), status_code


def serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if hasattr(value, "__table__"):
        return {
            column.name: serialize(getattr(value, column.name))
            for column in value.__table__.columns
        }
    return value
