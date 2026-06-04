import logging
import os
from datetime import timedelta

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from app.config import (
    AUTOMATION_DEVICE_POLL_INTERVAL_SECONDS,
    DEBUG,
    HOST,
    PORT,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    SESSION_LIFETIME_MINUTES,
)
from app.database import SessionLocal, init_db
from app.models import User as UserModel
from app.routers import automations, chatbot, dashboard, devices, energy, presence, roku, tuya, users
from app.security import (
    clear_login_failures,
    get_csrf_token,
    is_api_token_valid,
    is_csrf_token_valid,
    is_login_blocked,
    is_safe_redirect_target,
    register_login_failure,
)
from app.services.automation_service import AutomationService
from app.services.user_service import UserService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config.update(
        SECRET_KEY=SECRET_KEY,
        MAX_CONTENT_LENGTH=1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_LIFETIME_MINUTES),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    )

    for blueprint in (
        devices.blueprint,
        presence.blueprint,
        energy.blueprint,
        automations.blueprint,
        chatbot.blueprint,
        roku.blueprint,
        tuya.blueprint,
        users.blueprint,
        dashboard.blueprint,
    ):
        app.register_blueprint(blueprint)

    @app.before_request
    def require_login():
        public_paths = {"/login", "/health"}
        if request.path.startswith("/static/") or request.path in public_paths:
            return None
        if is_api_token_valid():
            return None
        if session.get("authenticated"):
            if request.method not in {"GET", "HEAD", "OPTIONS"} and not is_csrf_token_valid():
                return jsonify({"detail": "Token CSRF inválido ou ausente."}), 403
            return None
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"detail": "Autenticação obrigatória."}), 401
        return redirect(url_for("login", next=request.path))

    @app.after_request
    def add_security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if session.get("authenticated"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(500)
    def handle_internal_server_error(error):
        logger.exception("Erro interno ao processar %s %s", request.method, request.path, exc_info=error)
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"detail": "Erro interno ao processar a solicitação."}), 500
        return error

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": get_csrf_token}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("authenticated"):
            requested_url = request.args.get("next", "")
            next_url = requested_url if is_safe_redirect_target(requested_url) else url_for("get_dashboard")
            return redirect(next_url)

        error_message = None
        if request.method == "POST":
            username = request.form.get("username", "")[:128]
            password = request.form.get("password", "")[:1024]
            if not is_csrf_token_valid():
                return jsonify({"detail": "Token CSRF inválido ou ausente."}), 403
            if is_login_blocked(username):
                error_message = "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente."
            else:
                db = SessionLocal()
                authenticated_user = None
                try:
                    user = UserService.authenticate(db, username, password)
                    if not user and db.query(UserModel).count() == 0 and UserService.verify_legacy_credentials(username, password):
                        UserService.ensure_default_admin(db)
                        user = UserService.authenticate(db, username, password)
                    if user:
                        authenticated_user = {
                            "id": user.id,
                            "username": user.username,
                            "is_admin": bool(user.is_admin),
                        }
                finally:
                    db.close()
                if authenticated_user:
                    clear_login_failures(username)
                    session.clear()
                    session["authenticated"] = True
                    session["user_id"] = authenticated_user["id"]
                    session["username"] = authenticated_user["username"]
                    session["is_admin"] = authenticated_user["is_admin"]
                    session.permanent = True
                    get_csrf_token()
                    requested_url = request.args.get("next", "")
                    next_url = requested_url if is_safe_redirect_target(requested_url) else url_for("get_dashboard")
                    return redirect(next_url)
                register_login_failure(username)
                error_message = "Login ou senha inválidos."

        return render_template("login.html", error_message=error_message)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def get_dashboard():
        return render_template("dashboard.html", active_page="overview")

    @app.get("/devices-page")
    def get_devices_page():
        return render_template("devices.html", active_page="devices")

    @app.get("/energy-page")
    def get_energy_page():
        return render_template("energy.html", active_page="energy")

    @app.get("/automations-page")
    def get_automations_page():
        return render_template("automations.html", active_page="automations")

    @app.get("/chatbot-page")
    def get_chatbot_page():
        return render_template("chatbot.html", active_page="chatbot")

    @app.get("/presence-page")
    def get_presence_page():
        return render_template("presence.html", active_page="presence")

    @app.get("/activities-page")
    def get_activities_page():
        return render_template("activities.html", active_page="activities")

    @app.get("/users-page")
    def get_users_page():
        if not session.get("is_admin"):
            return jsonify({"detail": "Apenas administradores podem gerenciar usuários."}), 403
        return render_template("users.html", active_page="users")

    @app.get("/profiles/<username>")
    def get_user_profile(username):
        db = SessionLocal()
        try:
            profile = UserService.get_public_profile(db, username)
            if not profile:
                return jsonify({"detail": "Perfil não encontrado."}), 404
            return render_template("profile.html", active_page="", profile=profile)
        finally:
            db.close()

    @app.get("/health")
    def health_check():
        return jsonify(
            {
                "status": "healthy",
                "service": "Smart Home Server",
                "version": "1.0.0",
            }
        )

    @app.get("/api/info")
    def api_info():
        return jsonify(
            {
                "name": "Smart Home Server",
                "version": "1.0.0",
                "description": "Sistema de automacao residencial com Flask",
                "endpoints": {
                    "devices": "/devices",
                    "roku_register": "/roku/register",
                    "tuya_register": "/tuya/register",
                    "presence": "/presence",
                    "energy": "/energy",
                    "automations": "/automations",
                    "chatbot": "/chatbot/message",
                    "dashboard_data": "/api/dashboard/data",
                },
            }
        )

    with app.app_context():
        init_db()
        db = SessionLocal()
        try:
            UserService.ensure_schema(db)
            UserService.ensure_default_admin(db)
            UserService.ensure_presence_records(db)
        finally:
            db.close()
        logger.info("Banco de dados inicializado")

    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        AutomationService.start_device_state_monitor(
            dashboard._get_live_device_data,
            interval_seconds=AUTOMATION_DEVICE_POLL_INTERVAL_SECONDS,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
