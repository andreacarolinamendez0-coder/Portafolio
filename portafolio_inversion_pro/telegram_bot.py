"""
Notificador Telegram - Envía mensajes a usuarios vía bot.
"""
import logging
import requests
from config import Config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        """Envía un mensaje a un chat de Telegram."""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Telegram enviado a {chat_id}")
                return True
            else:
                logger.warning(f"Telegram error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Error enviando Telegram: {e}")
            return False

    def send_portfolio_alert(self, chat_id: str, portfolio_name: str, ticker: str,
                              alert_msg: str) -> bool:
        msg = (
            f"🔔 *Alerta de Portafolio*\n"
            f"📁 {portfolio_name}\n\n"
            f"{alert_msg}\n\n"
            f"_Sistema de Portafolio de Inversión_"
        )
        return self.send_message(chat_id, msg)

    def send_daily_summary(self, chat_id: str, username: str, portfolios_data: list) -> bool:
        lines = [f"📊 *Resumen Diario — {username}*\n"]
        for p in portfolios_data:
            sign = "📈" if p["gain_loss"] >= 0 else "📉"
            lines.append(
                f"{sign} *{p['name']}*\n"
                f"  Valor: ${p['current_value']:,.2f}\n"
                f"  Cambio: {'+' if p['gain_loss'] >= 0 else ''}{p['gain_loss_pct']:.2f}%\n"
            )
        lines.append("_Sistema de Portafolio de Inversión_")
        return self.send_message(chat_id, "\n".join(lines))

    def get_bot_info(self) -> dict | None:
        """Verifica que el bot funcione."""
        try:
            resp = requests.get(f"{self.base_url}/getMe", timeout=10)
            if resp.status_code == 200:
                return resp.json().get("result")
        except Exception as e:
            logger.error(f"Error verificando bot: {e}")
        return None
