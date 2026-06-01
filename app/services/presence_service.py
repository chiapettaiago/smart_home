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
from app.integrations.vivo_router import VivoRouterIntegration
from app.models import Presence as PresenceModel

logger = logging.getLogger(__name__)
_router_presence_lock = threading.Lock()
_router_presence_last_check = 0.0
_router_presence_misses = 0


class PresenceService:
    """Serviço para gerenciar presença de usuários"""

    @staticmethod
    def get_presence(db: Session, user: str) -> PresenceModel:
        """Obtém status de presença de um usuário"""
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
        return db.query(PresenceModel).all()

    @staticmethod
    def is_anyone_home(db: Session) -> bool:
        """Verifica se alguém está em casa"""
        return bool(db.query(PresenceModel).filter(PresenceModel.is_home == True).first())

    @staticmethod
    def refresh_from_vivo_router(db: Session, force: bool = False) -> dict:
        """Atualiza presença pelo MAC conectado ao Vivo Box sem reagir a falhas transitórias."""
        global _router_presence_last_check, _router_presence_misses

        if not all((VIVO_ROUTER_URL, VIVO_ROUTER_USERNAME, VIVO_ROUTER_PASSWORD, PRESENCE_PHONE_MAC, PRESENCE_USER)):
            return {"success": False, "skipped": True, "message": "Presença pelo Vivo Box não configurada."}

        with _router_presence_lock:
            now = time.monotonic()
            if not force and now - _router_presence_last_check < PRESENCE_ROUTER_INTERVAL_SECONDS:
                return {"success": True, "skipped": True, "message": "Consulta do Vivo Box aguardando intervalo."}
            _router_presence_last_check = now

            result = VivoRouterIntegration(
                base_url=VIVO_ROUTER_URL,
                username=VIVO_ROUTER_USERNAME,
                password=VIVO_ROUTER_PASSWORD,
            ).is_connected(PRESENCE_PHONE_MAC)
            if not result.get("success"):
                logger.warning("Não foi possível atualizar presença pelo Vivo Box: %s", result.get("message"))
                return result

            if result["connected"]:
                _router_presence_misses = 0
                presence = PresenceService.set_home(db, PRESENCE_USER)
                return {**result, "user": presence.user, "is_home": True}

            _router_presence_misses += 1
            presence = PresenceService.get_presence(db, PRESENCE_USER)
            if _router_presence_misses >= PRESENCE_ROUTER_AWAY_MISSES:
                presence = PresenceService.set_away(db, PRESENCE_USER)
            return {
                **result,
                "user": presence.user,
                "is_home": presence.is_home,
                "away_misses": _router_presence_misses,
                "away_misses_required": PRESENCE_ROUTER_AWAY_MISSES,
            }
