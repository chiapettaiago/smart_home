"""Gerenciamento de usuários do sistema."""

from datetime import datetime
import hmac
import re

from sqlalchemy import inspect, text
from sqlalchemy import func
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import AUTH_PASSWORD, AUTH_PASSWORD_HASH, AUTH_USERNAME
from app.models import Presence as PresenceModel, User as UserModel


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,128}$")
MAC_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}([:-]?)[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")


class UserService:
    @staticmethod
    def ensure_schema(db: Session) -> None:
        inspector = inspect(db.bind)
        if "users" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "phone_mac" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN phone_mac VARCHAR(17) NULL"))
            db.commit()

    @staticmethod
    def ensure_default_admin(db: Session) -> UserModel | None:
        if db.query(UserModel).count() > 0:
            return None
        password_hash = AUTH_PASSWORD_HASH or (generate_password_hash(AUTH_PASSWORD) if AUTH_PASSWORD else "")
        if not password_hash:
            return None
        user = UserModel(
            username=AUTH_USERNAME,
            display_name="Administrador",
            phone_mac=UserService.normalize_mac("") or None,
            password_hash=password_hash,
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        UserService._ensure_presence_record(db, AUTH_USERNAME)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def ensure_presence_records(db: Session) -> None:
        changed = False
        for user in db.query(UserModel).all():
            if not db.query(PresenceModel).filter(PresenceModel.user == user.username).first():
                db.add(PresenceModel(user=user.username, is_home=False))
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> UserModel | None:
        user = UserService.get_by_username(db, username)
        if not user:
            return None
        if not user.is_active:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def verify_legacy_credentials(username: str, password: str) -> bool:
        username_valid = hmac.compare_digest(username, AUTH_USERNAME)
        if AUTH_PASSWORD_HASH:
            password_valid = check_password_hash(AUTH_PASSWORD_HASH, password)
        elif AUTH_PASSWORD:
            password_valid = hmac.compare_digest(password, AUTH_PASSWORD)
        else:
            password_valid = False
        return username_valid and password_valid

    @staticmethod
    def get_users(db: Session) -> list[UserModel]:
        return db.query(UserModel).order_by(UserModel.username.asc()).all()

    @staticmethod
    def get_user(db: Session, user_id: int) -> UserModel | None:
        return db.query(UserModel).filter(UserModel.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> UserModel | None:
        normalized = (username or "").strip()
        if not normalized:
            return None
        return db.query(UserModel).filter(func.lower(UserModel.username) == normalized.lower()).first()

    @staticmethod
    def get_public_profile(db: Session, username: str) -> dict | None:
        user = UserService.get_by_username(db, username)
        if not user:
            return None
        presence = db.query(PresenceModel).filter(PresenceModel.user == user.username).first()
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "is_admin": bool(user.is_admin),
            "is_active": bool(user.is_active),
            "is_home": bool(presence.is_home) if presence else False,
            "presence_updated_at": presence.last_update if presence else None,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
        }

    @staticmethod
    def create_user(db: Session, data: dict) -> UserModel:
        username = (data.get("username") or "").strip()
        display_name = (data.get("display_name") or "").strip() or None
        phone_mac = UserService.normalize_mac(data.get("phone_mac") or "")
        password = data.get("password") or ""
        is_admin = bool(data.get("is_admin"))
        error = UserService.validate_user_payload(db, username, password=password, phone_mac=phone_mac)
        if error:
            raise ValueError(error)
        user = UserModel(
            username=username,
            display_name=display_name,
            phone_mac=phone_mac or None,
            password_hash=generate_password_hash(password),
            is_admin=is_admin,
            is_active=bool(data.get("is_active", True)),
        )
        db.add(user)
        UserService._ensure_presence_record(db, username)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, data: dict, current_user_id: int | None = None) -> UserModel:
        user = UserService.get_user(db, user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")
        username = (data.get("username") or user.username).strip()
        display_name = (data.get("display_name") or "").strip() if "display_name" in data else user.display_name
        phone_mac = UserService.normalize_mac(data.get("phone_mac") if "phone_mac" in data else user.phone_mac)
        password = data.get("password") or ""
        is_admin = bool(data.get("is_admin", user.is_admin))
        is_active = bool(data.get("is_active", user.is_active))
        error = UserService.validate_user_payload(db, username, password=password or None, phone_mac=phone_mac, user_id=user.id)
        if error:
            raise ValueError(error)
        if current_user_id == user.id and not is_active:
            raise ValueError("Você não pode desativar o próprio usuário.")
        if user.is_admin and (not is_admin or not is_active) and UserService.active_admin_count(db, exclude_user_id=user.id) == 0:
            raise ValueError("Mantenha pelo menos um administrador ativo.")
        old_username = user.username
        user.username = username
        user.display_name = display_name or None
        user.phone_mac = phone_mac or None
        user.is_admin = is_admin
        user.is_active = is_active
        if password:
            user.password_hash = generate_password_hash(password)
        UserService._sync_presence_username(db, old_username, username)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def delete_user(db: Session, user_id: int, current_user_id: int | None = None) -> None:
        user = UserService.get_user(db, user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")
        if current_user_id == user.id:
            raise ValueError("Você não pode remover o próprio usuário.")
        if user.is_admin and UserService.active_admin_count(db, exclude_user_id=user.id) == 0:
            raise ValueError("Mantenha pelo menos um administrador ativo.")
        presence = db.query(PresenceModel).filter(PresenceModel.user == user.username).first()
        if presence:
            db.delete(presence)
        db.delete(user)
        db.commit()

    @staticmethod
    def active_admin_count(db: Session, exclude_user_id: int | None = None) -> int:
        query = db.query(UserModel).filter(UserModel.is_admin.is_(True), UserModel.is_active.is_(True))
        if exclude_user_id is not None:
            query = query.filter(UserModel.id != exclude_user_id)
        return query.count()

    @staticmethod
    def validate_user_payload(
        db: Session,
        username: str,
        password: str | None = None,
        phone_mac: str | None = None,
        user_id: int | None = None,
    ) -> str | None:
        if not USERNAME_PATTERN.match(username or ""):
            return "Use um login com 3 a 128 caracteres: letras, números, ponto, hífen ou underline."
        existing = UserService.get_by_username(db, username)
        if existing and existing.id != user_id:
            return "Já existe um usuário com esse login."
        if not phone_mac:
            return "Informe o MAC do celular do usuário."
        if not MAC_PATTERN.match(phone_mac):
            return "Informe o MAC do celular no formato AA:BB:CC:DD:EE:FF."
        if phone_mac:
            existing_mac = (
                db.query(UserModel)
                .filter(func.lower(UserModel.phone_mac) == phone_mac.lower())
                .first()
            )
            if existing_mac and existing_mac.id != user_id:
                return "Esse MAC já está vinculado a outro usuário."
        if password is not None and len(password) < 8:
            return "A senha deve ter pelo menos 8 caracteres."
        return None

    @staticmethod
    def normalize_mac(value: str | None) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        compact = re.sub(r"[^0-9A-Fa-f]", "", value)
        if len(compact) != 12:
            return value.upper()
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).upper()

    @staticmethod
    def _ensure_presence_record(db: Session, username: str) -> PresenceModel:
        presence = db.query(PresenceModel).filter(PresenceModel.user == username).first()
        if not presence:
            presence = PresenceModel(user=username, is_home=False)
            db.add(presence)
        return presence

    @staticmethod
    def _sync_presence_username(db: Session, old_username: str, new_username: str) -> None:
        if old_username == new_username:
            UserService._ensure_presence_record(db, new_username)
            return
        presence = db.query(PresenceModel).filter(PresenceModel.user == old_username).first()
        target = db.query(PresenceModel).filter(PresenceModel.user == new_username).first()
        if presence and not target:
            presence.user = new_username
        elif presence and target:
            db.delete(presence)
        else:
            UserService._ensure_presence_record(db, new_username)
