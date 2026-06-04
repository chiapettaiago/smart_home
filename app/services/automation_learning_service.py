"""Aprendizado simples de padrões de uso para sugerir automações."""

from collections import defaultdict
from datetime import timezone
import json

from sqlalchemy.orm import Session

from app.models import ActionLog as ActionLogModel, Automation as AutomationModel
from app.services.action_service import ActionService
from app.services.environment_service import EnvironmentService


class AutomationLearningService:
    MIN_OCCURRENCES = 3
    MIN_DAYS = 2
    WINDOW_MINUTES = 15

    @staticmethod
    def get_suggestions(db: Session, limit: int = 5) -> list:
        suggestions = AutomationLearningService._time_based_suggestions(db)
        suggestions.sort(key=lambda item: item["confidence"], reverse=True)
        return suggestions[:limit]

    @staticmethod
    def _time_based_suggestions(db: Session) -> list:
        logs = (
            db.query(ActionLogModel)
            .filter(ActionLogModel.status == "success")
            .order_by(ActionLogModel.executed_at.desc())
            .limit(500)
            .all()
        )
        groups = defaultdict(list)
        for log in logs:
            if not log.device:
                continue
            local_dt = AutomationLearningService._to_local_time(log.executed_at)
            bucket_minutes = round((local_dt.hour * 60 + local_dt.minute) / AutomationLearningService.WINDOW_MINUTES) * AutomationLearningService.WINDOW_MINUTES
            bucket_minutes %= 24 * 60
            params_key = json.dumps(log.params or {}, sort_keys=True, ensure_ascii=False)
            groups[(log.device_id, log.action, params_key, bucket_minutes)].append((log, local_dt))

        existing = AutomationLearningService._existing_fingerprints(db)
        suggestions = []
        for (device_id, action, params_key, bucket_minutes), entries in groups.items():
            days = {local_dt.date().isoformat() for _, local_dt in entries}
            if len(entries) < AutomationLearningService.MIN_OCCURRENCES or len(days) < AutomationLearningService.MIN_DAYS:
                continue
            log = entries[0][0]
            device = log.device
            params = json.loads(params_key)
            if not ActionService.is_action_available_for_device(device, action):
                continue
            time_value = AutomationLearningService._minutes_to_time(bucket_minutes)
            fingerprint = AutomationLearningService._fingerprint("time", {"time": time_value}, [{"device_id": device_id, "action": action, "params": params}])
            if fingerprint in existing:
                continue
            automation = {
                "name": f"{device.name} às {time_value}",
                "trigger": "time",
                "condition": {"time": time_value},
                "actions": [{"device_id": device_id, "action": action, "params": params}],
                "active": True,
            }
            occurrences = len(entries)
            confidence = min(0.95, 0.45 + (occurrences * 0.08) + (len(days) * 0.08))
            suggestions.append(
                {
                    "id": f"time:{device_id}:{action}:{bucket_minutes}",
                    "title": automation["name"],
                    "reason": f"Você executou '{ActionService.ACTION_SPECS.get(action, {}).get('label', action)}' em {device.name} perto de {time_value} por {len(days)} dias.",
                    "confidence": round(confidence, 2),
                    "automation": automation,
                }
            )
        return suggestions

    @staticmethod
    def _existing_fingerprints(db: Session) -> set:
        fingerprints = set()
        for automation in db.query(AutomationModel).all():
            fingerprints.add(AutomationLearningService._fingerprint(automation.trigger, automation.condition or {}, automation.actions or []))
        return fingerprints

    @staticmethod
    def _fingerprint(trigger: str, condition: dict, actions: list) -> str:
        condition_copy = dict(condition or {})
        condition_copy.pop("_conditions", None)
        normalized_actions = [
            {
                "device_id": item.get("device_id"),
                "action": item.get("action"),
                "params": item.get("params") or {},
            }
            for item in actions or []
        ]
        return json.dumps(
            {
                "trigger": trigger,
                "condition": condition_copy,
                "actions": normalized_actions,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    @staticmethod
    def _to_local_time(value):
        tzinfo = EnvironmentService.timezone()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tzinfo)

    @staticmethod
    def _minutes_to_time(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
