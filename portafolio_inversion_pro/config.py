import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "portafolio-secret-2024-xK9mN2pQ")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'portafolio.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # Groq AI
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
    GROQ_MODEL = "llama-3.3-70b-versatile"

    # Telegram
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8")

    # Monitor
    MONITOR_INTERVAL = 60  # segundos entre actualizaciones de precios
    MARKET_OPEN_HOUR = 9   # Hora apertura mercado (ET)
    MARKET_CLOSE_HOUR = 16  # Hora cierre mercado (ET)
