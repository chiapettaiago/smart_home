from datetime import datetime, timezone

from app.config import HOME_ASSISTANT_TOKEN, HOME_ASSISTANT_URL
from app.integrations.home_assistant import HomeAssistantIntegration
from app.integrations.roku import RokuIntegration


class RokuStatusService:
    """Obtém status Roku e usa Home Assistant como fonte de playback quando possível."""

    @staticmethod
    def get_status(device, ha_config: dict = None) -> dict:
        status = RokuIntegration(device.ip).get_status() if device and device.ip else {}
        if not device:
            return status

        ha_state = RokuStatusService._get_home_assistant_media_state(device, ha_config=ha_config)
        if ha_state:
            status["now_playing"] = RokuStatusService._merge_home_assistant_playback(
                status.get("now_playing") or {},
                ha_state,
            )
            status["playback_state"] = status["now_playing"].get("playback_state")
            status["playback_state_label"] = status["now_playing"].get("playback_state_label")
        return status

    @staticmethod
    def _get_home_assistant_media_state(device, ha_config: dict = None) -> dict:
        metadata = device.device_metadata or {}
        ha_config = ha_config or {}
        ha_url = metadata.get("ha_url") or ha_config.get("ha_url") or HOME_ASSISTANT_URL
        ha_token = metadata.get("ha_token") or ha_config.get("ha_token") or HOME_ASSISTANT_TOKEN
        entity_id = (
            metadata.get("media_player_entity_id")
            or metadata.get("ha_media_player_entity_id")
            or metadata.get("entity_id")
            or metadata.get("external_id")
        )

        integration = HomeAssistantIntegration(base_url=ha_url, token=ha_token)
        if entity_id and str(entity_id).startswith("media_player."):
            result = integration.get_state(entity_id)
            return result.get("state") if result.get("success") else None

        result = integration.get_states()
        if not result.get("success"):
            return None
        states = result.get("states") or {}
        return RokuStatusService._find_matching_media_player(states.values(), device)

    @staticmethod
    def _find_matching_media_player(states, device) -> dict:
        device_name = (device.name or "").lower()
        device_ip = (device.ip or "").lower()
        best_score = 0
        best_state = None
        playback_candidates = []
        for state in states:
            entity_id = (state.get("entity_id") or "").lower()
            if not entity_id.startswith("media_player."):
                continue
            attributes = state.get("attributes") or {}
            if attributes.get("media_position") is not None or attributes.get("media_duration") is not None:
                playback_candidates.append(state)
            searchable = " ".join(
                str(value or "").lower()
                for value in (
                    entity_id,
                    attributes.get("friendly_name"),
                    attributes.get("manufacturer"),
                    attributes.get("model_name"),
                    attributes.get("model"),
                    attributes.get("device_class"),
                    attributes.get("source"),
                    attributes.get("app_name"),
                    attributes.get("host"),
                    attributes.get("hostname"),
                    attributes.get("ip_address"),
                )
            )
            score = 0
            if device_ip and device_ip in searchable:
                score += 100
            if "roku" in searchable:
                score += 40
            if device_name and device_name in searchable:
                score += 30
            if score > best_score:
                best_score = score
                best_state = state
        if best_score >= 40:
            return best_state

        active_candidates = [
            state for state in playback_candidates
            if (state.get("state") or "").lower() in {"playing", "paused", "buffering"}
        ]
        if len(active_candidates) == 1:
            return active_candidates[0]
        if len(playback_candidates) == 1:
            return playback_candidates[0]
        return None

    @staticmethod
    def _merge_home_assistant_playback(now_playing: dict, ha_state: dict) -> dict:
        attributes = ha_state.get("attributes") or {}
        playback_state = RokuStatusService._normalize_ha_playback_state(ha_state.get("state"))
        roku_playback_state = now_playing.get("playback_state")
        if playback_state == "idle" and roku_playback_state in {"playing", "paused", "buffering"}:
            playback_state = roku_playback_state
        ha_position = RokuStatusService._number_or_none(attributes.get("media_position"))
        ha_duration = RokuStatusService._number_or_none(attributes.get("media_duration"))
        updated_at_ms = RokuStatusService._parse_datetime_ms(attributes.get("media_position_updated_at"))
        sampled_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        position_seconds = ha_position
        duration_seconds = ha_duration
        progress_source = "home_assistant"
        if position_seconds is None:
            position_seconds = RokuStatusService._number_or_none(now_playing.get("position_seconds"))
            progress_source = now_playing.get("progress_source") or "roku"
        if duration_seconds is None or duration_seconds <= 0:
            duration_seconds = RokuStatusService._number_or_none(now_playing.get("duration_seconds"))
            if ha_position is None:
                progress_source = now_playing.get("progress_source") or "roku"

        if (
            playback_state == "playing"
            and ha_position is not None
            and updated_at_ms is not None
        ):
            elapsed_seconds = max(0, (sampled_at_ms - updated_at_ms) / 1000)
            position_seconds = ha_position + elapsed_seconds
        if duration_seconds and position_seconds is not None:
            position_seconds = max(0, min(position_seconds, duration_seconds))

        if position_seconds is not None and duration_seconds:
            progress_percent = round(max(0, min(100, (position_seconds / duration_seconds) * 100)), 1)
        else:
            progress_percent = None

        merged = {
            **now_playing,
            "app_name": attributes.get("app_name") or attributes.get("source") or now_playing.get("app_name"),
            "content_title": attributes.get("media_title") or now_playing.get("content_title"),
            "playback_state": playback_state,
            "playback_state_label": RokuIntegration.PLAYBACK_STATE_LABELS.get(playback_state, "Desconhecido"),
            "position_seconds": position_seconds,
            "duration_seconds": duration_seconds,
            "position_updated_at_ms": updated_at_ms,
            "position_sampled_at_ms": sampled_at_ms,
            "progress_percent": progress_percent,
            "progress_source": progress_source,
            "ha_entity_id": ha_state.get("entity_id"),
            "media_content_id": attributes.get("media_content_id"),
        }
        return merged

    @staticmethod
    def _normalize_ha_playback_state(state: str) -> str:
        state = (state or "").lower()
        if state in {"playing", "paused", "buffering", "idle", "off"}:
            return state
        if state in {"standby", "unknown", "unavailable"}:
            return "idle"
        return "unknown"

    @staticmethod
    def _number_or_none(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime_ms(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        except ValueError:
            return None
