import os
import secrets
import warnings
from werkzeug.security import check_password_hash
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# Configurações gerais
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "")
API_TOKEN = os.getenv("API_TOKEN", "")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD_HASH = os.getenv("AUTH_PASSWORD_HASH", "")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true" if ENVIRONMENT == "production" else "false").lower() == "true"
SESSION_LIFETIME_MINUTES = int(os.getenv("SESSION_LIFETIME_MINUTES", "60"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

if not SECRET_KEY:
    if ENVIRONMENT == "production":
        raise RuntimeError("Configure SECRET_KEY com um valor aleatório antes de iniciar em produção.")
    SECRET_KEY = secrets.token_hex(32)
    warnings.warn("SECRET_KEY ausente: usando chave temporária de desenvolvimento.", RuntimeWarning)

if ENVIRONMENT == "production" and not AUTH_PASSWORD_HASH:
    raise RuntimeError("Configure AUTH_PASSWORD_HASH antes de iniciar em produção.")
if AUTH_PASSWORD and not AUTH_PASSWORD_HASH:
    warnings.warn("AUTH_PASSWORD em texto puro é legado. Migre para AUTH_PASSWORD_HASH.", RuntimeWarning)
if AUTH_PASSWORD_HASH and check_password_hash(AUTH_PASSWORD_HASH, "admin123"):
    if ENVIRONMENT == "production":
        raise RuntimeError("Troque a senha de demonstração antes de iniciar em produção.")
    warnings.warn("A senha de demonstração ainda está ativa. Execute scripts/set_password.py.", RuntimeWarning)

# Banco de dados
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://smart_home:change-me@127.0.0.1:3306/smart_home?charset=utf8mb4",
)

# Servidor
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8100"))

# Integrações (placeholders)
TUYA_API_KEY = os.getenv("TUYA_API_KEY", "")
TUYA_API_SECRET = os.getenv("TUYA_API_SECRET", "")
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
VIVO_ROUTER_URL = os.getenv("VIVO_ROUTER_URL", "")
VIVO_ROUTER_USERNAME = os.getenv("VIVO_ROUTER_USERNAME", "")
VIVO_ROUTER_PASSWORD = os.getenv("VIVO_ROUTER_PASSWORD", "")
PRESENCE_PHONE_MAC = os.getenv("PRESENCE_PHONE_MAC", "")
PRESENCE_USER = os.getenv("PRESENCE_USER", "")
PRESENCE_ROUTER_INTERVAL_SECONDS = int(os.getenv("PRESENCE_ROUTER_INTERVAL_SECONDS", "30"))
PRESENCE_ROUTER_AWAY_MISSES = int(os.getenv("PRESENCE_ROUTER_AWAY_MISSES", "3"))

# Whitelist de ações permitidas
ALLOWED_ACTIONS = [
    "turn_on",
    "turn_off",
    "toggle",
    "restart",
    "lock",
    "unlock",
    "open_app",
    "close_app",
    "get_status",
    "set_brightness",
    "set_color_temp",
    "set_hs_color",
    "set_rgb_color",
    "set_percentage",
    "set_temperature",
    "set_hvac_mode",
    "set_preset_mode",
    "set_fan_mode",
    "set_swing_mode",
    "tuya_command",
]

# Tipos de dispositivos suportados
DEVICE_TYPES = [
    "tuya",
    "roku",
    "android",
    "pc_windows",
    "pc_linux",
    "sensor",
    "other",
]

# Cômodos
ROOMS = [
    "sala",
    "quarto",
    "cozinha",
    "banheiro",
    "escritório",
    "garagem",
    "outro",
]
