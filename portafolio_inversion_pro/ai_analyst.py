"""
Analista Conversacional con IA usando Groq (llama-3.3-70b-versatile).
"""
import logging
from groq import Groq
from config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres Andrea, una analista financiera experta y asistente personal de inversiones.
Ayudas a los usuarios a entender sus portafolios, analizar acciones, evaluar riesgos y tomar decisiones informadas.

Tu estilo:
- Profesional pero amigable y accesible
- Eres directa y das recomendaciones concretas cuando se te piden
- Usas datos del portafolio del usuario cuando están disponibles
- Siempre aclaras que tus análisis son informativos y no constituyen asesoría financiera certificada
- Respondes en español
- Usas emojis moderadamente para hacer la conversación más dinámica

Capacidades:
- Análisis de portafolio (diversificación, riesgo, rendimiento)
- Evaluación de acciones individuales
- Estrategias de inversión (largo plazo, dividendos, crecimiento)
- Explicación de métricas financieras
- Alertas sobre concentración de riesgo
- Comparación de activos
"""

PORTFOLIO_CONTEXT_TEMPLATE = """
=== CONTEXTO DEL PORTAFOLIO DEL USUARIO ===
Portafolio: {portfolio_name}
Acciones en portafolio:
{stocks_summary}

Resumen financiero:
- Inversión total: ${total_invested:,.2f}
- Valor actual: ${current_value:,.2f}
- Ganancia/Pérdida: ${gain_loss:,.2f} ({gain_loss_pct:.2f}%)
==========================================
"""


class AIAnalyst:
    def __init__(self):
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL

    def chat(self, message: str, history: list, context: dict, username: str) -> str:
        """Chat conversacional con contexto del portafolio."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Agregar contexto del portafolio si existe
        if context.get("portfolio") and context.get("stocks"):
            ctx = self._build_context(context)
            messages.append({"role": "system", "content": ctx})

        # Historial de conversación (máx 10 mensajes)
        for h in history[-10:]:
            if h.get("role") in ("user", "assistant"):
                messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error en AI chat: {e}")
            return "Lo siento, tuve un problema procesando tu consulta. Por favor intenta de nuevo."

    def analyze_portfolio(self, portfolio: dict, stocks: list, summary: dict) -> str:
        """Análisis automático completo del portafolio."""
        stocks_text = "\n".join([
            f"- {s['ticker']} ({s['company_name']}): {s['shares']} acciones @ ${s['buy_price']:.2f}, "
            f"actual: ${s['current_price']:.2f}, P&L: {s['gain_loss_pct']:.2f}%"
            for s in stocks
        ]) if stocks else "Sin acciones."

        prompt = f"""Analiza el siguiente portafolio de inversión de manera completa y profesional:

Portafolio: {portfolio.get('name')}
Acciones:
{stocks_text}

Métricas:
- Inversión total: ${summary.get('total_invested', 0):,.2f}
- Valor actual: ${summary.get('current_value', 0):,.2f}
- Ganancia/Pérdida: ${summary.get('gain_loss', 0):,.2f} ({summary.get('gain_loss_pct', 0):.2f}%)

Por favor proporciona:
1. 📊 Análisis de diversificación
2. ⚠️ Riesgos identificados
3. 🏆 Mejores y peores performers
4. 💡 Recomendaciones específicas
5. 🎯 Estrategia sugerida

Sé conciso pero completo. Máximo 400 palabras."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.6,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error en analyze_portfolio: {e}")
            return "Error generando el análisis. Por favor intenta de nuevo."

    def _build_context(self, context: dict) -> str:
        portfolio = context.get("portfolio", {})
        stocks = context.get("stocks", [])
        summary = context.get("summary", {})

        stocks_summary = "\n".join([
            f"  • {s['ticker']}: {s['shares']} acciones, comprado a ${s['buy_price']:.2f}, "
            f"actual ${s['current_price']:.2f} ({'+' if s['gain_loss_pct'] >= 0 else ''}{s['gain_loss_pct']:.2f}%)"
            for s in stocks
        ]) or "  (Sin acciones)"

        return PORTFOLIO_CONTEXT_TEMPLATE.format(
            portfolio_name=portfolio.get("name", ""),
            stocks_summary=stocks_summary,
            total_invested=summary.get("total_invested", 0),
            current_value=summary.get("current_value", 0),
            gain_loss=summary.get("gain_loss", 0),
            gain_loss_pct=summary.get("gain_loss_pct", 0),
        )
