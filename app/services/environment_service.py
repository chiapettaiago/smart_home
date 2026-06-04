"""Contexto ambiental para automações: data, sol e clima."""

from datetime import date, datetime, time, timedelta, timezone
import logging
import math
from zoneinfo import ZoneInfo

import requests

from app.config import (
    HOME_LATITUDE,
    HOME_LONGITUDE,
    HOME_TIMEZONE,
    WEATHER_CACHE_SECONDS,
    WEATHER_PROVIDER_URL,
)

logger = logging.getLogger(__name__)

_weather_cache = {"expires_at": None, "data": None}


class EnvironmentService:
    WEATHER_CODE_LABELS = {
        0: "Céu limpo",
        1: "Principalmente limpo",
        2: "Parcialmente nublado",
        3: "Nublado",
        45: "Nevoeiro",
        48: "Nevoeiro com geada",
        51: "Garoa fraca",
        53: "Garoa moderada",
        55: "Garoa intensa",
        61: "Chuva fraca",
        63: "Chuva moderada",
        65: "Chuva forte",
        80: "Pancadas fracas",
        81: "Pancadas moderadas",
        82: "Pancadas fortes",
        95: "Trovoada",
    }
    RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    COMPARISON_OPERATORS = {
        "gt": lambda current, expected: current > expected,
        "gte": lambda current, expected: current >= expected,
        "lt": lambda current, expected: current < expected,
        "lte": lambda current, expected: current <= expected,
        "eq": lambda current, expected: current == expected,
        "neq": lambda current, expected: current != expected,
    }

    @staticmethod
    def timezone():
        try:
            return ZoneInfo(HOME_TIMEZONE)
        except Exception:
            logger.warning("Timezone %s inválida; usando UTC.", HOME_TIMEZONE)
            return timezone.utc

    @staticmethod
    def now():
        return datetime.now(EnvironmentService.timezone())

    @staticmethod
    def get_context(now=None) -> dict:
        now = now or EnvironmentService.now()
        sunrise, sunset = EnvironmentService._sun_times(now.date(), HOME_LATITUDE, HOME_LONGITUDE, now.tzinfo)
        weather = EnvironmentService.get_weather(now)
        calendar = EnvironmentService._calendar_context(now)
        sun = {
            "sunrise": sunrise.isoformat() if sunrise else None,
            "sunset": sunset.isoformat() if sunset else None,
            "sunrise_time": sunrise.strftime("%H:%M") if sunrise else None,
            "sunset_time": sunset.strftime("%H:%M") if sunset else None,
            "is_daylight": bool(sunrise and sunset and sunrise <= now < sunset),
            "minutes_to_sunrise": EnvironmentService._minutes_until(now, sunrise),
            "minutes_to_sunset": EnvironmentService._minutes_until(now, sunset),
        }
        return {
            "location": {
                "latitude": HOME_LATITUDE,
                "longitude": HOME_LONGITUDE,
                "timezone": HOME_TIMEZONE,
            },
            "now": now.isoformat(),
            "time": now.strftime("%H:%M"),
            "calendar": calendar,
            "sun": sun,
            "weather": weather,
        }

    @staticmethod
    def get_weather(now=None) -> dict:
        now = now or EnvironmentService.now()
        cached = _weather_cache.get("data")
        expires_at = _weather_cache.get("expires_at")
        if cached and expires_at and expires_at > now:
            return cached

        default = {
            "available": False,
            "temperature": None,
            "apparent_temperature": None,
            "humidity": None,
            "precipitation": None,
            "rain": None,
            "precipitation_probability": None,
            "weather_code": None,
            "condition": "indisponível",
            "is_raining": False,
            "wind_speed": None,
            "cloud_cover": None,
            "updated_at": now.isoformat(),
        }
        try:
            response = requests.get(
                WEATHER_PROVIDER_URL,
                params={
                    "latitude": HOME_LATITUDE,
                    "longitude": HOME_LONGITUDE,
                    "timezone": HOME_TIMEZONE,
                    "current": ",".join(
                        [
                            "temperature_2m",
                            "relative_humidity_2m",
                            "apparent_temperature",
                            "precipitation",
                            "rain",
                            "weather_code",
                            "cloud_cover",
                            "wind_speed_10m",
                            "is_day",
                        ]
                    ),
                    "hourly": "precipitation_probability",
                    "forecast_days": 1,
                },
                timeout=8,
            )
            if response.status_code != 200:
                logger.warning("Open-Meteo retornou %s: %s", response.status_code, response.text[:200])
                return EnvironmentService._cache_weather(default, now)
            payload = response.json()
            current = payload.get("current") or {}
            weather_code = current.get("weather_code")
            weather = {
                "available": True,
                "temperature": current.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "rain": current.get("rain"),
                "precipitation_probability": EnvironmentService._current_hourly_value(
                    payload.get("hourly") or {},
                    "precipitation_probability",
                    current.get("time"),
                ),
                "weather_code": weather_code,
                "condition": EnvironmentService.WEATHER_CODE_LABELS.get(weather_code, str(weather_code or "indisponível")),
                "is_raining": weather_code in EnvironmentService.RAIN_CODES or (current.get("rain") or 0) > 0,
                "wind_speed": current.get("wind_speed_10m"),
                "cloud_cover": current.get("cloud_cover"),
                "is_day": current.get("is_day"),
                "updated_at": now.isoformat(),
            }
            return EnvironmentService._cache_weather(weather, now)
        except Exception:
            logger.warning("Falha ao obter clima; usando contexto indisponível.")
            return EnvironmentService._cache_weather(default, now)

    @staticmethod
    def matches_weather(condition: dict, context: dict) -> bool:
        weather = context.get("weather") or {}
        field = condition.get("field")
        if field == "is_raining":
            return bool(weather.get("is_raining")) == bool(condition.get("is_raining"))
        current = weather.get(field)
        expected = condition.get("value")
        operator = condition.get("operator", "gte")
        if current is None or expected is None:
            return False
        try:
            return EnvironmentService.COMPARISON_OPERATORS.get(operator, EnvironmentService.COMPARISON_OPERATORS["gte"])(
                float(current),
                float(expected),
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def matches_calendar(condition: dict, context: dict) -> bool:
        calendar = context.get("calendar") or {}
        mode = condition.get("mode")
        if mode == "day_type":
            return calendar.get("day_type") == condition.get("day_type")
        if mode == "weekday":
            return calendar.get("weekday") == int(condition.get("weekday", -1))
        if mode == "date":
            return calendar.get("date") == condition.get("date")
        if mode == "month_day":
            return calendar.get("month") == int(condition.get("month", -1)) and calendar.get("day") == int(condition.get("day", -1))
        return False

    @staticmethod
    def sun_event_due(condition: dict, context: dict, window_minutes: int = 1) -> bool:
        event = condition.get("event")
        target_time = (context.get("sun") or {}).get(f"{event}_time")
        if event not in {"sunrise", "sunset"} or not target_time:
            return False
        offset = int(condition.get("offset_minutes") or 0)
        now_time = datetime.strptime(context["time"], "%H:%M")
        target = datetime.strptime(target_time, "%H:%M") + timedelta(minutes=offset)
        diff = abs((now_time - target).total_seconds()) / 60
        return diff < max(1, window_minutes)

    @staticmethod
    def _cache_weather(weather: dict, now: datetime) -> dict:
        _weather_cache["data"] = weather
        _weather_cache["expires_at"] = now + timedelta(seconds=WEATHER_CACHE_SECONDS)
        return weather

    @staticmethod
    def _calendar_context(now: datetime) -> dict:
        weekday = now.weekday()
        return {
            "date": now.date().isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "weekday": weekday,
            "weekday_name": ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][weekday],
            "day_type": "weekend" if weekday >= 5 else "weekday",
        }

    @staticmethod
    def _current_hourly_value(hourly: dict, field: str, current_time: str):
        times = hourly.get("time") or []
        values = hourly.get(field) or []
        if not times or not values:
            return None
        current_hour = (current_time or "")[:13]
        for index, item in enumerate(times):
            if item[:13] == current_hour and index < len(values):
                return values[index]
        return values[0] if values else None

    @staticmethod
    def _minutes_until(now: datetime, target: datetime):
        if not target:
            return None
        return round((target - now).total_seconds() / 60)

    @staticmethod
    def _sun_times(day: date, latitude: float, longitude: float, tzinfo) -> tuple:
        sunrise = EnvironmentService._sun_event(day, latitude, longitude, tzinfo, is_sunrise=True)
        sunset = EnvironmentService._sun_event(day, latitude, longitude, tzinfo, is_sunrise=False)
        return sunrise, sunset

    @staticmethod
    def _sun_event(day: date, latitude: float, longitude: float, tzinfo, is_sunrise: bool):
        zenith = 90.833
        day_of_year = day.timetuple().tm_yday
        lng_hour = longitude / 15
        approx_time = day_of_year + ((6 - lng_hour) / 24 if is_sunrise else (18 - lng_hour) / 24)
        mean_anomaly = (0.9856 * approx_time) - 3.289
        true_longitude = mean_anomaly + (1.916 * math.sin(math.radians(mean_anomaly))) + (0.020 * math.sin(math.radians(2 * mean_anomaly))) + 282.634
        true_longitude %= 360
        right_ascension = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_longitude)))) % 360
        longitude_quadrant = math.floor(true_longitude / 90) * 90
        ascension_quadrant = math.floor(right_ascension / 90) * 90
        right_ascension = (right_ascension + longitude_quadrant - ascension_quadrant) / 15
        sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
        cos_declination = math.cos(math.asin(sin_declination))
        cos_hour_angle = (
            math.cos(math.radians(zenith)) - (sin_declination * math.sin(math.radians(latitude)))
        ) / (cos_declination * math.cos(math.radians(latitude)))
        if cos_hour_angle < -1 or cos_hour_angle > 1:
            return None
        hour_angle = 360 - math.degrees(math.acos(cos_hour_angle)) if is_sunrise else math.degrees(math.acos(cos_hour_angle))
        hour_angle /= 15
        local_mean_time = hour_angle + right_ascension - (0.06571 * approx_time) - 6.622
        utc_hour = (local_mean_time - lng_hour) % 24
        utc_dt = datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(hours=utc_hour)
        return utc_dt.astimezone(tzinfo)
