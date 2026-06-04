from datetime import datetime
import logging
import threading
import time

from sqlalchemy.orm import Session

from app.config import (
    PRESENCE_PHONE_MAC,
    PRESENCE_ROUTER_AWAY_MISSES,
    PRESENCE_ROUTER_INTERVAL_SECONDS,
    PRESENCE_USER,
    VIVO_ROUTER_PASSWORD,
    VIVO_ROUTER_URL,
    VIVO_ROUTER_USERNAME,
)
from app.integrations.vivo_router import VivoRouterIntegration, normalize_mac
from app.models import Presence as PresenceModel, User as UserModel

logger = logging.getLogger(__name__)
_router_presence_lock = threading.Lock()
_router_presence_last_check = 0.0
_router_presence_misses = {}


class PresenceService:
    """Serviço para gerenciar presença de usuários"""

    @staticmethod
    def get_presence(db: Session, user: str) -> PresenceModel:
        """Obtém status de presença de um usuário"""
        user = PresenceService._canonical_username(db, user)
        presence = db.query(PresenceModel).filter(PresenceModel.user == user).first()
        if not presence:
            # Cria registro se não existir
            presence = PresenceModel(user=user, is_home=False)
            db.add(presence)
            db.commit()
            db.refresh(presence)
        return presence

    @staticmethod
    def set_home(db: Session, user: str) -> PresenceModel:
        """Marca o usuário como em casa"""
        presence = PresenceService.get_presence(db, user)
        presence.is_home = True
        presence.last_update = datetime.utcnow()
        db.commit()
        db.refresh(presence)
        logger.info(f"Usuário {user} marcado como em casa")
        return presence

    @staticmethod
    def set_away(db: Session, user: str) -> PresenceModel:
        """Marca o usuário como fora de casa"""
        presence = PresenceService.get_presence(db, user)
        presence.is_home = False
        presence.last_update = datetime.utcnow()
        db.commit()
        db.refresh(presence)
        logger.info(f"Usuário {user} marcado como fora de casa")
        return presence

    @staticmethod
    def get_all_presence(db: Session):
        """Obtém status de presença de todos os usuários"""
        PresenceService.reconcile_user_presence_records(db)
        active_users = db.query(UserModel).filter(UserModel.is_active.is_(True)).order_by(UserModel.username.asc()).all()
        if not active_users:
            return db.query(PresenceModel).order_by(PresenceModel.user.asc()).all()
        usernames = [user.username for user in active_users]
        return db.query(PresenceModel).filter(PresenceModel.user.in_(usernames)).order_by(PresenceModel.user.asc()).all()

    @staticmethod
    def is_anyone_home(db: Session) -> bool:
        """Verifica se alguém está em casa"""
        return any(presence.is_home for presence in PresenceService.get_all_presence(db))

    @staticmethod
    def refresh_from_vivo_router(db: Session, force: bool = False) -> dict:
        """Atualiza presença pelos MACs dos usuários conectados ao Vivo Box."""
        global _router_presence_last_check, _router_presence_misses

        if not all((VIVO_ROUTER_URL, VIVO_ROUTER_USERNAME, VIVO_ROUTER_PASSWORD)):
            return {"success": False, "skipped": True, "message": "Presença pelo Vivo Box não configurada."}

        tracked_users = PresenceService._tracked_users(db)
        if not tracked_users:
            return {"success": False, "skipped": True, "message": "Nenhum usuário com MAC de celular cadastrado."}

        with _router_presence_lock:
            now = time.monotonic()
            if not force and now - _router_presence_last_check < PRESENCE_ROUTER_INTERVAL_SECONDS:
                return {"success": True, "skipped": True, "message": "Consulta do Vivo Box aguardando intervalo."}
            _router_presence_last_check = now

            router_result = VivoRouterIntegration(
                base_url=VIVO_ROUTER_URL,
                username=VIVO_ROUTER_USERNAME,
                password=VIVO_ROUTER_PASSWORD,
            ).get_connected_macs()
            if not router_result.get("success"):
                logger.warning("Não foi possível atualizar presença pelo Vivo Box: %s", router_result.get("message"))
                return router_result

            connected_macs = set(router_result["macs"])
            updates = []
            failures = []
            for user in tracked_users:
                target_mac = normalize_mac(user["phone_mac"])
                if len(target_mac) != 12:
                    failures.append({"user": user["username"], "message": "MAC do celular inválido."})
                    continue
                connected = target_mac in connected_macs

                if connected:
                    _router_presence_misses[user["username"]] = 0
                    presence = PresenceService.set_home(db, user["username"])
                else:
                    misses = _router_presence_misses.get(user["username"], 0) + 1
                    _router_presence_misses[user["username"]] = misses
                    presence = PresenceService.get_presence(db, user["username"])
                    if misses >= PRESENCE_ROUTER_AWAY_MISSES:
                        presence = PresenceService.set_away(db, user["username"])

                updates.append(
                    {
                        "user": presence.user,
                        "phone_mac": user["phone_mac"],
                        "is_home": presence.is_home,
                        "connected": connected,
                        "away_misses": _router_presence_misses.get(user["username"], 0),
                        "away_misses_required": PRESENCE_ROUTER_AWAY_MISSES,
                    }
                )

            if failures:
                logger.warning("Falhas ao atualizar presença pelo Vivo Box: %s", failures)
            return {
                "success": bool(updates),
                "users": updates,
                "failures": failures,
                "message": f"Presença atualizada para {len(updates)} usuário(s).",
            }

    @staticmethod
    def _tracked_users(db: Session) -> list[dict]:
        users = (
            db.query(UserModel)
            .filter(UserModel.is_active.is_(True), UserModel.phone_mac.isnot(None), UserModel.phone_mac != "")
            .order_by(UserModel.username.asc())
            .all()
        )
        tracked = [{"username": user.username, "phone_mac": user.phone_mac} for user in users]
        if not tracked and PRESENCE_PHONE_MAC and PRESENCE_USER:
            tracked.append({"username": PRESENCE_USER, "phone_mac": PRESENCE_PHONE_MAC})
        return tracked

    @staticmethod
    def reconcile_user_presence_records(db: Session) -> None:
        """Mescla presenças legadas e garante um registro por usuário ativo."""
        changed = False
        users = db.query(UserModel).filter(UserModel.is_active.is_(True)).all()
        user_by_name = {user.username.lower(): user for user in users}

        legacy_target = PresenceService._legacy_presence_target(db)
        if legacy_target and PRESENCE_USER:
            changed = PresenceService._merge_presence_record(db, PRESENCE_USER, legacy_target.username) or changed

        for user in users:
            presence = db.query(PresenceModel).filter(PresenceModel.user == user.username).first()
            if not presence:
                db.add(PresenceModel(user=user.username, is_home=False))
                changed = True

        for presence in db.query(PresenceModel).all():
            canonical = user_by_name.get((presence.user or "").lower())
            if canonical and presence.user != canonical.username:
                changed = PresenceService._merge_presence_record(db, presence.user, canonical.username) or changed

        if changed:
            db.commit()

    @staticmethod
    def _canonical_username(db: Session, username: str) -> str:
        username = (username or "").strip()
        user = db.query(UserModel).filter(UserModel.username.ilike(username)).first()
        if user:
            return user.username
        if PRESENCE_USER and username.lower() == PRESENCE_USER.lower():
            legacy_target = PresenceService._legacy_presence_target(db)
            if legacy_target:
                return legacy_target.username
        return username

    @staticmethod
    def _legacy_presence_target(db: Session):
        legacy_mac = normalize_mac(PRESENCE_PHONE_MAC)
        if len(legacy_mac) != 12:
            return None
        for user in db.query(UserModel).filter(UserModel.is_active.is_(True)).all():
            if normalize_mac(user.phone_mac) == legacy_mac:
                return user
        return None

    @staticmethod
    def _merge_presence_record(db: Session, source_username: str, target_username: str) -> bool:
        if not source_username or not target_username or source_username == target_username:
            return False
        source = db.query(PresenceModel).filter(PresenceModel.user == source_username).first()
        if not source:
            return False
        target = db.query(PresenceModel).filter(PresenceModel.user == target_username).first()
        if not target:
            source.user = target_username
            return True
        if source.is_home and not target.is_home:
            target.is_home = True
            target.last_update = source.last_update
        elif source.last_update and (not target.last_update or source.last_update > target.last_update):
            target.last_update = source.last_update
        db.delete(source)
        return True
