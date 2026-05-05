"""
Sistema de Portafolio de Inversión Multi-Usuario
Puerto: 5000
"""

import os
import json
import threading
import time
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from database import db, User, Portfolio, Stock, Alert, Notification, AdminLog
from monitor import PortfolioMonitor
from ai_analyst import AIAnalyst
from telegram_bot import TelegramNotifier
from config import Config

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── App Setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Por favor inicia sesión para continuar."

monitor = PortfolioMonitor()
ai_analyst = AIAnalyst()
telegram = TelegramNotifier()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Decoradores ─────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"error": "Acceso denegado"}), 403
        return f(*args, **kwargs)
    return decorated


# ─── Rutas Principales ───────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        data = request.get_json() or request.form
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        telegram_chat_id = data.get("telegram_chat_id", "").strip()

        if not username or not email or not password:
            return jsonify({"error": "Todos los campos son requeridos"}), 400
        if len(password) < 6:
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Este email ya está registrado"}), 409
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Este nombre de usuario ya existe"}), 409

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            telegram_chat_id=telegram_chat_id if telegram_chat_id else None,
            is_admin=False
        )
        db.session.add(user)
        db.session.commit()

        # Portafolio por defecto
        default_portfolio = Portfolio(
            user_id=user.id,
            name="Mi Portafolio",
            description="Portafolio principal",
            currency="USD"
        )
        db.session.add(default_portfolio)
        db.session.commit()

        login_user(user)
        logger.info(f"Nuevo usuario registrado: {username} ({email})")
        return jsonify({"success": True, "redirect": url_for("dashboard")})

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        data = request.get_json() or request.form
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        remember = data.get("remember", False)

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Email o contraseña incorrectos"}), 401
        if not user.is_active:
            return jsonify({"error": "Cuenta desactivada. Contacta al administrador."}), 403

        login_user(user, remember=bool(remember))
        user.last_login = datetime.utcnow()
        db.session.commit()
        logger.info(f"Login: {user.username}")
        return jsonify({"success": True, "redirect": url_for("dashboard")})

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logger.info(f"Logout: {current_user.username}")
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id, is_active=True).all()
    notifications = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    return render_template("dashboard.html", portfolios=portfolios, notifications=notifications)


# ─── API Portafolios ──────────────────────────────────────────────────────────
@app.route("/api/portfolios", methods=["GET"])
@login_required
def get_portfolios():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id, is_active=True).all()
    result = []
    for p in portfolios:
        data = p.to_dict()
        data["summary"] = monitor.get_portfolio_summary(p.id)
        result.append(data)
    return jsonify(result)


@app.route("/api/portfolios", methods=["POST"])
@login_required
def create_portfolio():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "El nombre es requerido"}), 400

    portfolio = Portfolio(
        user_id=current_user.id,
        name=name,
        description=data.get("description", ""),
        currency=data.get("currency", "USD")
    )
    db.session.add(portfolio)
    db.session.commit()
    monitor.start_portfolio_monitor(portfolio.id)
    return jsonify(portfolio.to_dict()), 201


@app.route("/api/portfolios/<int:pid>", methods=["GET"])
@login_required
def get_portfolio(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    data = portfolio.to_dict()
    data["stocks"] = [s.to_dict() for s in portfolio.stocks if s.is_active]
    data["summary"] = monitor.get_portfolio_summary(pid)
    data["chart_data"] = monitor.get_portfolio_chart(pid)
    return jsonify(data)


@app.route("/api/portfolios/<int:pid>", methods=["PUT"])
@login_required
def update_portfolio(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if "name" in data:
        portfolio.name = data["name"]
    if "description" in data:
        portfolio.description = data["description"]
    db.session.commit()
    return jsonify(portfolio.to_dict())


@app.route("/api/portfolios/<int:pid>", methods=["DELETE"])
@login_required
def delete_portfolio(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    portfolio.is_active = False
    db.session.commit()
    monitor.stop_portfolio_monitor(pid)
    return jsonify({"success": True})


# ─── API Acciones ─────────────────────────────────────────────────────────────
@app.route("/api/portfolios/<int:pid>/stocks", methods=["POST"])
@login_required
def add_stock(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    data = request.get_json()

    ticker = data.get("ticker", "").upper().strip()
    shares = float(data.get("shares", 0))
    buy_price = float(data.get("buy_price", 0))

    if not ticker or shares <= 0 or buy_price <= 0:
        return jsonify({"error": "Datos inválidos"}), 400

    # Verificar ticker válido
    price_data = monitor.get_current_price(ticker)
    if price_data is None:
        return jsonify({"error": f"Ticker '{ticker}' no encontrado"}), 404

    stock = Stock(
        portfolio_id=pid,
        ticker=ticker,
        company_name=price_data.get("name", ticker),
        shares=shares,
        buy_price=buy_price,
        current_price=price_data.get("price", buy_price),
        buy_date=datetime.strptime(data.get("buy_date", datetime.utcnow().strftime("%Y-%m-%d")), "%Y-%m-%d")
    )
    db.session.add(stock)
    db.session.commit()
    return jsonify(stock.to_dict()), 201


@app.route("/api/stocks/<int:sid>", methods=["DELETE"])
@login_required
def delete_stock(sid):
    stock = Stock.query.join(Portfolio).filter(
        Stock.id == sid,
        Portfolio.user_id == current_user.id
    ).first_or_404()
    stock.is_active = False
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/stocks/<int:sid>", methods=["PUT"])
@login_required
def update_stock(sid):
    stock = Stock.query.join(Portfolio).filter(
        Stock.id == sid,
        Portfolio.user_id == current_user.id
    ).first_or_404()
    data = request.get_json()
    if "shares" in data:
        stock.shares = float(data["shares"])
    if "buy_price" in data:
        stock.buy_price = float(data["buy_price"])
    db.session.commit()
    return jsonify(stock.to_dict())


# ─── API Precios en Tiempo Real ───────────────────────────────────────────────
@app.route("/api/price/<ticker>")
@login_required
def get_price(ticker):
    data = monitor.get_current_price(ticker.upper())
    if data is None:
        return jsonify({"error": "Ticker no encontrado"}), 404
    return jsonify(data)


@app.route("/api/search/<query>")
@login_required
def search_ticker(query):
    results = monitor.search_tickers(query)
    return jsonify(results)


# ─── API Alertas ──────────────────────────────────────────────────────────────
@app.route("/api/alerts", methods=["GET"])
@login_required
def get_alerts():
    alerts = Alert.query.join(Portfolio).filter(
        Portfolio.user_id == current_user.id,
        Alert.is_active == True
    ).all()
    return jsonify([a.to_dict() for a in alerts])


@app.route("/api/alerts", methods=["POST"])
@login_required
def create_alert():
    data = request.get_json()
    pid = data.get("portfolio_id")
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()

    alert = Alert(
        portfolio_id=pid,
        ticker=data.get("ticker", "").upper(),
        alert_type=data.get("alert_type"),  # price_above, price_below, change_pct
        threshold=float(data.get("threshold", 0)),
        notify_telegram=data.get("notify_telegram", True),
        notify_email=data.get("notify_email", False)
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify(alert.to_dict()), 201


@app.route("/api/alerts/<int:aid>", methods=["DELETE"])
@login_required
def delete_alert(aid):
    alert = Alert.query.join(Portfolio).filter(
        Alert.id == aid,
        Portfolio.user_id == current_user.id
    ).first_or_404()
    alert.is_active = False
    db.session.commit()
    return jsonify({"success": True})


# ─── API IA / Analista ────────────────────────────────────────────────────────
@app.route("/api/ai/chat", methods=["POST"])
@login_required
def ai_chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    portfolio_id = data.get("portfolio_id")
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400

    # Contexto del portafolio del usuario
    context = {}
    if portfolio_id:
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=current_user.id).first()
        if portfolio:
            context["portfolio"] = portfolio.to_dict()
            context["stocks"] = [s.to_dict() for s in portfolio.stocks if s.is_active]
            context["summary"] = monitor.get_portfolio_summary(portfolio_id)

    response = ai_analyst.chat(message, history, context, current_user.username)
    return jsonify({"response": response})


@app.route("/api/ai/analyze/<int:pid>")
@login_required
def ai_analyze_portfolio(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    stocks = [s.to_dict() for s in portfolio.stocks if s.is_active]
    summary = monitor.get_portfolio_summary(pid)

    analysis = ai_analyst.analyze_portfolio(portfolio.to_dict(), stocks, summary)
    return jsonify({"analysis": analysis})


# ─── API Notificaciones ───────────────────────────────────────────────────────
@app.route("/api/notifications")
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return jsonify([n.to_dict() for n in notifs])


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/notifications/unread-count")
@login_required
def unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({"count": count})


# ─── Perfil de Usuario ────────────────────────────────────────────────────────
@app.route("/api/profile", methods=["GET"])
@login_required
def get_profile():
    return jsonify(current_user.to_dict())


@app.route("/api/profile", methods=["PUT"])
@login_required
def update_profile():
    data = request.get_json()
    if "telegram_chat_id" in data:
        current_user.telegram_chat_id = data["telegram_chat_id"]
    if "email_notifications" in data:
        current_user.email_notifications = data["email_notifications"]
    if "new_password" in data and data["new_password"]:
        if not check_password_hash(current_user.password_hash, data.get("current_password", "")):
            return jsonify({"error": "Contraseña actual incorrecta"}), 400
        current_user.password_hash = generate_password_hash(data["new_password"])
    db.session.commit()
    return jsonify(current_user.to_dict())


# ─── Panel de Administración ──────────────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    return render_template("admin.html")


@app.route("/api/admin/users")
@login_required
@admin_required
def admin_get_users():
    users = User.query.all()
    result = []
    for u in users:
        d = u.to_dict()
        d["portfolio_count"] = Portfolio.query.filter_by(user_id=u.id, is_active=True).count()
        result.append(d)
    return jsonify(result)


@app.route("/api/admin/users/<int:uid>", methods=["PUT"])
@login_required
@admin_required
def admin_update_user(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json()
    if "is_active" in data:
        user.is_active = data["is_active"]
    if "is_admin" in data:
        user.is_admin = data["is_admin"]
    db.session.commit()
    AdminLog.log(current_user.id, f"Updated user {user.username}: {data}")
    return jsonify(user.to_dict())


@app.route("/api/admin/stats")
@login_required
@admin_required
def admin_stats():
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_portfolios = Portfolio.query.filter_by(is_active=True).count()
    total_stocks = Stock.query.filter_by(is_active=True).count()
    recent_logins = User.query.filter(
        User.last_login >= datetime.utcnow() - timedelta(days=7)
    ).count()
    return jsonify({
        "total_users": total_users,
        "active_users": active_users,
        "total_portfolios": total_portfolios,
        "total_stocks": total_stocks,
        "recent_logins": recent_logins,
        "monitor_threads": monitor.get_active_threads()
    })


@app.route("/api/admin/logs")
@login_required
@admin_required
def admin_logs():
    logs = AdminLog.query.order_by(AdminLog.created_at.desc()).limit(100).all()
    return jsonify([l.to_dict() for l in logs])


# ─── Páginas de Portafolio ────────────────────────────────────────────────────
@app.route("/portfolio/<int:pid>")
@login_required
def portfolio_view(pid):
    portfolio = Portfolio.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    return render_template("portfolio.html", portfolio=portfolio)


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


# ─── Inicialización ───────────────────────────────────────────────────────────
def initialize_app():
    with app.app_context():
        db.create_all()

        # Crear admin por defecto si no existe
        admin = User.query.filter_by(email="admin@portafolio.com").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@portafolio.com",
                password_hash=generate_password_hash("admin123"),
                is_admin=True,
                is_active=True
            )
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin por defecto creado: admin@portafolio.com / admin123")

        # Iniciar monitores para portafolios activos
        portfolios = Portfolio.query.filter_by(is_active=True).all()
        for p in portfolios:
            monitor.start_portfolio_monitor(p.id)
        logger.info(f"Monitor iniciado para {len(portfolios)} portafolios")


if __name__ == "__main__":
    initialize_app()
    app.run(debug=True, port=5000, use_reloader=False)
