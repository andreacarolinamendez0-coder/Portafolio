"""
Monitor de portafolios: un hilo por portafolio para actualizaciones en paralelo.
"""
import threading
import time
import logging
from datetime import datetime

import yfinance as yf

logger = logging.getLogger(__name__)

_monitor_threads = {}
_lock = threading.Lock()
_price_cache = {}
_cache_ttl = 60  # segundos


class PortfolioMonitor:

    def __init__(self):
        self._stop_events = {}

    def get_current_price(self, ticker: str) -> dict | None:
        """Obtiene precio actual con caché de 60s."""
        now = time.time()
        if ticker in _price_cache:
            cached = _price_cache[ticker]
            if now - cached["ts"] < _cache_ttl:
                return cached["data"]
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = getattr(info, "last_price", None)
            if price is None:
                hist = t.history(period="1d", interval="1m")
                if hist.empty:
                    return None
                price = float(hist["Close"].iloc[-1])
            name = getattr(info, "exchange", ticker)
            try:
                name = t.info.get("shortName", ticker)
            except Exception:
                name = ticker
            data = {
                "ticker": ticker,
                "price": round(float(price), 4),
                "name": name,
                "currency": getattr(info, "currency", "USD"),
                "change": 0,
                "change_pct": 0,
                "volume": getattr(info, "three_month_average_volume", 0),
                "market_cap": getattr(info, "market_cap", 0),
                "timestamp": datetime.utcnow().isoformat(),
            }
            # Cambio del día
            try:
                prev = getattr(info, "previous_close", None)
                if prev and prev > 0:
                    data["change"] = round(price - prev, 4)
                    data["change_pct"] = round((price - prev) / prev * 100, 2)
            except Exception:
                pass
            _price_cache[ticker] = {"ts": now, "data": data}
            return data
        except Exception as e:
            logger.warning(f"Error obteniendo precio de {ticker}: {e}")
            return None

    def search_tickers(self, query: str) -> list:
        """Búsqueda básica de tickers."""
        try:
            results = []
            t = yf.Ticker(query.upper())
            info = t.info
            if info.get("symbol"):
                results.append({
                    "ticker": info["symbol"],
                    "name": info.get("shortName", query),
                    "exchange": info.get("exchange", ""),
                    "type": info.get("quoteType", ""),
                })
            return results
        except Exception:
            return []

    def get_portfolio_summary(self, portfolio_id: int) -> dict:
        """Calcula resumen del portafolio con precios actuales."""
        from database import db, Stock, Portfolio
        try:
            from flask import current_app
            with current_app.app_context():
                stocks = Stock.query.filter_by(portfolio_id=portfolio_id, is_active=True).all()
                if not stocks:
                    return {"total_invested": 0, "current_value": 0, "gain_loss": 0,
                            "gain_loss_pct": 0, "stock_count": 0}

                total_invested = sum(s.shares * s.buy_price for s in stocks)
                current_value = sum(s.shares * (s.current_price or s.buy_price) for s in stocks)
                gain_loss = current_value - total_invested
                gain_loss_pct = (gain_loss / total_invested * 100) if total_invested > 0 else 0

                return {
                    "total_invested": round(total_invested, 2),
                    "current_value": round(current_value, 2),
                    "gain_loss": round(gain_loss, 2),
                    "gain_loss_pct": round(gain_loss_pct, 2),
                    "stock_count": len(stocks),
                    "best_performer": self._best_performer(stocks),
                    "worst_performer": self._worst_performer(stocks),
                }
        except Exception as e:
            logger.error(f"Error en get_portfolio_summary({portfolio_id}): {e}")
            return {}

    def _best_performer(self, stocks):
        if not stocks:
            return None
        best = max(stocks, key=lambda s: ((s.current_price or s.buy_price) - s.buy_price) / s.buy_price if s.buy_price else 0)
        pct = ((best.current_price or best.buy_price) - best.buy_price) / best.buy_price * 100 if best.buy_price else 0
        return {"ticker": best.ticker, "gain_pct": round(pct, 2)}

    def _worst_performer(self, stocks):
        if not stocks:
            return None
        worst = min(stocks, key=lambda s: ((s.current_price or s.buy_price) - s.buy_price) / s.buy_price if s.buy_price else 0)
        pct = ((worst.current_price or worst.buy_price) - worst.buy_price) / worst.buy_price * 100 if worst.buy_price else 0
        return {"ticker": worst.ticker, "gain_pct": round(pct, 2)}

    def get_portfolio_chart(self, portfolio_id: int) -> dict:
        """Datos para gráfico de distribución del portafolio."""
        from database import db, Stock
        try:
            from flask import current_app
            with current_app.app_context():
                stocks = Stock.query.filter_by(portfolio_id=portfolio_id, is_active=True).all()
                if not stocks:
                    return {"labels": [], "values": [], "colors": []}
                labels = [s.ticker for s in stocks]
                values = [round(s.shares * (s.current_price or s.buy_price), 2) for s in stocks]
                gains = [round(((s.current_price or s.buy_price) - s.buy_price) / s.buy_price * 100, 2) if s.buy_price else 0 for s in stocks]
                return {"labels": labels, "values": values, "gains": gains}
        except Exception as e:
            logger.error(f"Error en get_portfolio_chart: {e}")
            return {"labels": [], "values": [], "gains": []}

    def start_portfolio_monitor(self, portfolio_id: int):
        """Inicia hilo de monitoreo para un portafolio."""
        with _lock:
            if portfolio_id in _monitor_threads and _monitor_threads[portfolio_id].is_alive():
                return
            stop_event = threading.Event()
            self._stop_events[portfolio_id] = stop_event
            t = threading.Thread(
                target=self._monitor_loop,
                args=(portfolio_id, stop_event),
                daemon=True,
                name=f"monitor-portfolio-{portfolio_id}"
            )
            _monitor_threads[portfolio_id] = t
            t.start()
            logger.info(f"Monitor iniciado para portafolio {portfolio_id}")

    def stop_portfolio_monitor(self, portfolio_id: int):
        """Detiene el hilo de monitoreo."""
        if portfolio_id in self._stop_events:
            self._stop_events[portfolio_id].set()
        with _lock:
            _monitor_threads.pop(portfolio_id, None)
        logger.info(f"Monitor detenido para portafolio {portfolio_id}")

    def _monitor_loop(self, portfolio_id: int, stop_event: threading.Event):
        """Bucle principal de monitoreo del portafolio."""
        from config import Config
        interval = Config.MONITOR_INTERVAL

        # Import lazy para evitar circular imports
        try:
            from flask import current_app
        except Exception:
            return

        while not stop_event.is_set():
            try:
                self._update_portfolio_prices(portfolio_id)
                self._check_alerts(portfolio_id)
            except Exception as e:
                logger.error(f"Error en monitor loop {portfolio_id}: {e}")
            stop_event.wait(interval)

    def _update_portfolio_prices(self, portfolio_id: int):
        from database import db, Stock, Portfolio
        try:
            from app import app
            with app.app_context():
                stocks = Stock.query.filter_by(portfolio_id=portfolio_id, is_active=True).all()
                for stock in stocks:
                    price_data = self.get_current_price(stock.ticker)
                    if price_data:
                        stock.current_price = price_data["price"]
                        stock.last_updated = datetime.utcnow()
                db.session.commit()
        except Exception as e:
            logger.error(f"Error actualizando precios portafolio {portfolio_id}: {e}")

    def _check_alerts(self, portfolio_id: int):
        from database import db, Alert, Portfolio, Notification, Stock, User
        from telegram_bot import TelegramNotifier
        try:
            from app import app
            with app.app_context():
                alerts = Alert.query.filter_by(portfolio_id=portfolio_id, is_active=True).all()
                if not alerts:
                    return

                portfolio = Portfolio.query.get(portfolio_id)
                if not portfolio:
                    return
                user = User.query.get(portfolio.user_id)
                telegram = TelegramNotifier()

                for alert in alerts:
                    price_data = self.get_current_price(alert.ticker)
                    if not price_data:
                        continue

                    price = price_data["price"]
                    change_pct = price_data.get("change_pct", 0)
                    triggered = False
                    msg = ""

                    if alert.alert_type == "price_above" and price >= alert.threshold:
                        triggered = True
                        msg = f"🚀 {alert.ticker} supera ${alert.threshold:.2f} → Precio actual: ${price:.2f}"
                    elif alert.alert_type == "price_below" and price <= alert.threshold:
                        triggered = True
                        msg = f"⚠️ {alert.ticker} cae bajo ${alert.threshold:.2f} → Precio actual: ${price:.2f}"
                    elif alert.alert_type == "change_pct_up" and change_pct >= alert.threshold:
                        triggered = True
                        msg = f"📈 {alert.ticker} subió {change_pct:.2f}% hoy (umbral: +{alert.threshold}%)"
                    elif alert.alert_type == "change_pct_down" and change_pct <= -alert.threshold:
                        triggered = True
                        msg = f"📉 {alert.ticker} bajó {change_pct:.2f}% hoy (umbral: -{alert.threshold}%)"

                    if triggered:
                        # Evitar spam: no re-notificar en la misma hora
                        from datetime import timedelta
                        if alert.last_triggered and (datetime.utcnow() - alert.last_triggered) < timedelta(hours=1):
                            continue

                        alert.triggered_count += 1
                        alert.last_triggered = datetime.utcnow()

                        # Guardar notificación en DB
                        notif = Notification(
                            user_id=portfolio.user_id,
                            title=f"Alerta: {alert.ticker}",
                            message=msg,
                            notif_type="alert"
                        )
                        db.session.add(notif)

                        # Telegram
                        if alert.notify_telegram and user.telegram_chat_id:
                            full_msg = f"🔔 *Alerta Portafolio: {portfolio.name}*\n\n{msg}"
                            telegram.send_message(user.telegram_chat_id, full_msg)

                        db.session.commit()
                        logger.info(f"Alerta disparada: {msg}")
        except Exception as e:
            logger.error(f"Error verificando alertas portafolio {portfolio_id}: {e}")

    def get_active_threads(self) -> int:
        return sum(1 for t in _monitor_threads.values() if t.is_alive())
