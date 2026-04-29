from flask import Flask, render_template_string, request
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

GROQ_API_KEY = "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"

# ============================================================
# CARGAR DATOS
# ============================================================

def cargar_macro():
    try:
        trm       = pd.read_parquet("datos/macro/trm.parquet")
        inf_col   = pd.read_parquet("datos/macro/inflacion_col.parquet")
        inf_usa   = pd.read_parquet("datos/macro/inflacion_usa.parquet")
        risk_free = pd.read_parquet("datos/macro/risk_free.parquet")
        banrep    = pd.read_parquet("datos/macro/tasa_banrep.parquet")

        trm_actual   = float(trm['TRM'].iloc[-1])
        trm_hace_mes = float(trm['TRM'].iloc[-22]) if len(trm) > 22 else trm_actual
        trm_cambio   = ((trm_actual - trm_hace_mes) / trm_hace_mes) * 100

        return {
            "trm":        round(trm_actual, 2),
            "trm_cambio": round(trm_cambio, 2),
            "inf_col":    round(float(inf_col['Inflacion_COL'].iloc[-1]), 2),
            "inf_usa":    round(float(inf_usa['Inflacion_USA'].iloc[-1]), 2),
            "risk_free":  round(float(risk_free['Risk_Free'].iloc[-1]), 2),
            "banrep":     round(float(banrep['Tasa_Banrep'].iloc[-1]), 2),
            "cdt":        round(float(banrep['Tasa_Banrep'].iloc[-1]) - 0.75, 2),
            "spread":     round(float(inf_col['Inflacion_COL'].iloc[-1]) -
                               float(inf_usa['Inflacion_USA'].iloc[-1]), 2),
            "trm_hist":   trm.tail(90)
        }
    except Exception as e:
        return {"error": str(e)}

def cargar_portafolio(nombre_archivo=None):
    try:
        from gestor_portafolio import listar_portafolios, leer_portafolio
        portafolios = listar_portafolios()
        if not portafolios:
            return None, []

        if nombre_archivo:
            data = leer_portafolio(nombre_archivo)
        else:
            activo = next((p for p in portafolios if p['activo']), None)
            if not activo:
                activo = portafolios[0]
            data = leer_portafolio(activo['archivo'])

        return data, portafolios
    except:
        return None, []

def precio_actual_usd(ticker):
    try:
        hoy    = datetime.now()
        inicio = (hoy - timedelta(days=5)).strftime("%Y-%m-%d")
        fin    = hoy.strftime("%Y-%m-%d")
        df = yf.download(ticker, start=inicio, end=fin,
                        interval="1d", auto_adjust=True, progress=False)
        if df.empty:
            # Fallback: intentar con period
            df = yf.download(ticker, period="5d", interval="1d",
                           auto_adjust=True, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except:
        return None

def calcular_portafolio_tiempo_real(portafolio):
    if not portafolio or not portafolio.get('aportes'):
        return None
    try:
        trm       = pd.read_parquet("datos/macro/trm.parquet")
        trm_actual = float(trm['TRM'].iloc[-1])
    except:
        trm_actual = 4000

    inf_anual      = portafolio.get('inflacion_col', 4.90)
    posiciones_raw = {}

    for aporte in portafolio['aportes']:
        activo = aporte['activo']
        if activo not in posiciones_raw:
            posiciones_raw[activo] = {
                'fracciones':  0,
                'invertido':   0,
                'fecha_inicio': aporte['fecha']
            }
        posiciones_raw[activo]['fracciones'] += aporte['fracciones']
        posiciones_raw[activo]['invertido']  += aporte['monto_cop']

    resultados      = []
    total_invertido = total_valor = 0

    for activo, datos in posiciones_raw.items():
        precio_hoy = precio_actual_usd(activo)
        if precio_hoy is None:
            continue

        valor_hoy = datos['fracciones'] * precio_hoy * trm_actual
        fecha     = datetime.strptime(datos['fecha_inicio'], "%Y-%m-%d")
        años      = (datetime.now() - fecha).days / 365.25
        inv_real  = datos['invertido'] / (1 + inf_anual/100) ** años
        ganancia  = valor_hoy - inv_real
        rent      = (ganancia / inv_real * 100) if inv_real > 0 else 0

        resultados.append({
            'activo':       activo,
            'fracciones':   round(datos['fracciones'], 4),
            'precio_hoy':   round(precio_hoy, 2),
            'valor_hoy':    round(valor_hoy, 0),
            'invertido':    round(inv_real, 0),
            'ganancia':     round(ganancia, 0),
            'rentabilidad': round(rent, 2)
        })
        total_invertido += inv_real
        total_valor     += valor_hoy

    return {
        'posiciones':         resultados,
        'total_invertido':    round(total_invertido, 0),
        'total_valor':        round(total_valor, 0),
        'ganancia_total':     round(total_valor - total_invertido, 0),
        'rentabilidad_total': round((total_valor - total_invertido) /
                                   total_invertido * 100
                                   if total_invertido > 0 else 0, 2)
    }

# ============================================================
# NOTICIAS Y ANÁLISIS
# ============================================================

def buscar_noticias_relevantes(activos):
    import xml.etree.ElementTree as ET
    noticias = []
    terminos = [
        "Federal Reserve interest rates",
        "NVIDIA stock AI",
        "Bitcoin crypto market",
        "Colombia economia peso",
        "S&P 500 Wall Street",
        "Eli Lilly pharmaceutical",
        "Walmart earnings retail",
        "JPMorgan bank earnings"
    ]

    for termino in terminos[:6]:
        try:
            query    = termino.replace(' ', '+')
            url      = f"https://news.google.com/rss/search?q={query}&hl=es&gl=CO&ceid=CO:es"
            headers  = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=8)
            root     = ET.fromstring(response.content)
            items    = root.findall('.//item')

            for item in items[:2]:
                titulo = item.find('title')
                link   = item.find('link')
                fecha  = item.find('pubDate')
                fuente = item.find('source')
                if titulo is not None and link is not None:
                    noticias.append({
                        'titulo': titulo.text[:120] if titulo.text else '',
                        'url':    link.text if link.text else '',
                        'fecha':  fecha.text[:16] if fecha is not None and fecha.text else '',
                        'fuente': fuente.text if fuente is not None and fuente.text else 'Google News'
                    })
        except:
            continue

    vistos = set()
    unicos = []
    for n in noticias:
        if n['titulo'] not in vistos:
            vistos.add(n['titulo'])
            unicos.append(n)
    return unicos[:8]


def generar_analisis_economico(macro, portafolio):
    try:
        from groq import Groq

        composicion = portafolio.get('composicion', {}) if portafolio else {}
        todos       = list(composicion.keys())
        perfil_port = portafolio.get('perfil', '') if portafolio else ''
        nombre_port = portafolio.get('nombre', '') if portafolio else ''
        hoy         = datetime.now().strftime("%d de %B de %Y")

        noticias       = buscar_noticias_relevantes(todos)
        noticias_texto = ""
        for i, n in enumerate(noticias, 1):
            noticias_texto += f"{i}. [{n['fuente']}] {n['titulo']} ({n['fecha']})\n"

        client = Groq(api_key=GROQ_API_KEY)

        prompt = f"""Eres un asesor financiero senior. HOY es {hoy}.

DATOS MACRO REALES DE HOY:
- TRM: ${macro['trm']:,.0f} COP/USD (cambio último mes: {macro['trm_cambio']:+.1f}%)
- Inflación Colombia: {macro['inf_col']}% | Inflación USA: {macro['inf_usa']}%
- Spread COL-USA: {macro['spread']}% — {'ALTO, peso bajo presión' if macro['spread'] > 3 else 'normal'}
- Tasa Banrep: {macro['banrep']}% | CDT referencia: {macro['cdt']}%
- Treasury Bills USA: {macro['risk_free']}%

PORTAFOLIO ANALIZADO: {nombre_port} ({perfil_port})
ACTIVOS: {', '.join(todos)}

NOTICIAS REALES DE HOY:
{noticias_texto}

INSTRUCCIONES — SÉ MUY ESPECÍFICO:
1. Cita cada noticia por su fuente y título, explica el mecanismo EXACTO de impacto en el portafolio
2. Para cada activo sensible, di exactamente cómo y por qué lo afecta con números cuando puedas
3. Usa los datos macro para cuantificar el impacto
4. Identifica 2 riesgos específicos con su mecanismo de transmisión
5. Termina con UNA acción concreta a vigilar esta semana con fecha específica
6. Lenguaje conversacional en español, como hablar con una amiga inteligente
7. 4 párrafos separados por salto de línea. Sin asteriscos. Sin bullets. Sin markdown.
8. Máximo 400 palabras."""

        respuesta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un asesor financiero experto. Das análisis específicos basados solo en las noticias reales que te dan. Nunca inventas eventos."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.6
        )

        texto   = respuesta.choices[0].message.content
        fuentes = "\n\n---FUENTES---\n"
        for n in noticias[:6]:
            fuentes += f"• {n['titulo']} — {n['fuente']} | {n['url']}\n"
        return texto + fuentes

    except Exception as e:
        return (f"TRM en ${macro['trm']:,.0f} ({macro['trm_cambio']:+.1f}% último mes). "
                f"Inflación Colombia {macro['inf_col']}% vs USA {macro['inf_usa']}%. "
                f"Banrep {macro['banrep']}% — CDT referencia {macro['cdt']}%.")

# ============================================================
# GRÁFICAS
# ============================================================

def grafica_trm(trm_hist):
    trm_values = trm_hist['TRM'].values
    ma7        = pd.Series(trm_values).rolling(7).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trm_hist.index, y=trm_values,
        mode='lines', name='TRM',
        line=dict(color='#00d4aa', width=2),
        fill='tozeroy', fillcolor='rgba(0,212,170,0.08)'
    ))
    fig.add_trace(go.Scatter(
        x=trm_hist.index, y=ma7,
        mode='lines', name='Media 7d',
        line=dict(color='#f59e0b', width=1, dash='dot'),
        opacity=0.7
    ))
    fig.update_layout(
        title=dict(text="📈 TRM — Últimos 90 días", font=dict(size=14, color='#00d4aa')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,0.5)',
        font=dict(color='#94a3b8'), height=230,
        margin=dict(l=50, r=20, t=40, b=30),
        legend=dict(orientation='h', y=1.1, font=dict(size=10)),
        hovermode='x unified'
    )
    fig.update_xaxes(gridcolor='rgba(42,42,74,0.5)')
    fig.update_yaxes(gridcolor='rgba(42,42,74,0.5)', tickprefix="$", tickformat=",")
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_torta(pesos, titulo, colores):
    fig = go.Figure(go.Pie(
        labels=list(pesos.keys()),
        values=[v*100 for v in pesos.values()],
        hole=0.5,
        marker=dict(colors=colores, line=dict(color='#0f0f23', width=2)),
        textinfo='label+percent',
        textfont=dict(color='white', size=11),
        hovertemplate='<b>%{label}</b><br>%{percent}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color='#94a3b8')),
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white'), height=270,
        margin=dict(l=10, r=10, t=35, b=10),
        showlegend=False
    )
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_historico_individual(activos, dias=180):
    hoy    = datetime.now()
    inicio = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
    fin    = hoy.strftime("%Y-%m-%d")
    colores = ['#00d4aa','#3b82f6','#f59e0b','#ef4444',
               '#8b5cf6','#ec4899','#06b6d4','#84cc16','#f97316','#6366f1']
    datos = {}
    for ticker in activos:
        try:
            df = yf.download(ticker, start=inicio, end=fin,
                           auto_adjust=True, progress=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            datos[ticker] = df['Close'].squeeze()
        except:
            continue

    if not datos:
        return ""

    fig = go.Figure()
    for i, (ticker, serie) in enumerate(datos.items()):
        fig.add_trace(go.Scatter(
            x=serie.index, y=serie.values,
            mode='lines', name=ticker,
            line=dict(color=colores[i % len(colores)], width=2),
            hovertemplate=(f'<b>{ticker}</b><br>%{{x|%d %b %Y}}<br>'
                          f'$%{{y:,.2f}} USD<extra></extra>'),
            visible=True
        ))

    botones = [dict(
        label="Todos", method="update",
        args=[{"visible": [True] * len(datos)},
              {"title": {"text": f"Precio por acción (USD) — Todos | {inicio} → {fin}",
                         "font": {"color": "#00d4aa", "size": 13}}}]
    )]
    for i, ticker in enumerate(datos.keys()):
        vis = [False] * len(datos)
        vis[i] = True
        botones.append(dict(
            label=ticker, method="update",
            args=[{"visible": vis},
                  {"title": {"text": f"Precio por acción (USD) — {ticker} | {inicio} → {fin}",
                             "font": {"color": "#00d4aa", "size": 13}}}]
        ))

    fig.update_layout(
        title=dict(text=f"Precio por acción (USD) — Todos | {inicio} → {fin}",
                  font=dict(size=13, color='#00d4aa')),
        updatemenus=[dict(
            type="buttons", direction="left", buttons=botones,
            pad={"r": 10, "t": 10}, showactive=True, active=0,
            x=0.0, y=1.22, xanchor="left", yanchor="top",
            bgcolor='#1a1a2e', bordercolor='#00d4aa', borderwidth=1,
            font=dict(color='white', size=11)
        )],
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,0.5)',
        font=dict(color='#94a3b8'), height=430,
        margin=dict(l=60, r=20, t=100, b=40),
        legend=dict(orientation='h', y=-0.12, bgcolor='rgba(0,0,0,0)', font=dict(size=10)),
        hovermode='x unified'
    )
    fig.update_xaxes(gridcolor='rgba(42,42,74,0.5)', title_text="Fecha",
                    title_font=dict(size=11, color='#64748b'))
    fig.update_yaxes(gridcolor='rgba(42,42,74,0.5)', title_text="Precio (USD)",
                    title_font=dict(size=11, color='#64748b'), tickprefix="$")
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_ganancia_por_activo(tiempo_real):
    if not tiempo_real or not tiempo_real['posiciones']:
        return ""
    posiciones = sorted(tiempo_real['posiciones'], key=lambda x: x['ganancia'], reverse=True)
    activos   = [p['activo'] for p in posiciones]
    ganancias = [p['ganancia'] for p in posiciones]
    rents     = [p['rentabilidad'] for p in posiciones]
    colores   = ['#10b981' if g > 0 else '#ef4444' for g in ganancias]

    fig = go.Figure(go.Bar(
        x=activos, y=ganancias,
        marker=dict(color=colores, line=dict(color='rgba(0,0,0,0.3)', width=1)),
        text=[f"${g:,.0f}<br>{r:+.1f}%" for g, r in zip(ganancias, rents)],
        textposition='outside', textfont=dict(color='white', size=10),
        hovertemplate='<b>%{x}</b><br>Ganancia: $%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text="💰 Ganancia Real por Activo (COP)", font=dict(size=14, color='#00d4aa')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,0.5)',
        font=dict(color='#94a3b8'), height=320,
        margin=dict(l=40, r=20, t=50, b=40), showlegend=False
    )
    fig.update_xaxes(gridcolor='rgba(42,42,74,0.5)')
    fig.update_yaxes(gridcolor='rgba(42,42,74,0.5)', zeroline=True,
                    zerolinecolor='rgba(255,255,255,0.2)', zerolinewidth=1, tickprefix="$")
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_evolucion_portafolio(historico):
    if not historico or len(historico) < 2:
        return ""
    fechas    = [r['fecha'] for r in historico]
    valores   = [r['resumen']['total_valor'] for r in historico]
    invertido = [r['resumen']['total_invertido'] for r in historico]
    ganancias = [r['resumen']['ganancia_total'] for r in historico]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas, y=valores, mode='lines+markers', name='Valor portafolio',
        line=dict(color='#00d4aa', width=2),
        fill='tozeroy', fillcolor='rgba(0,212,170,0.08)',
        hovertemplate='<b>Valor</b><br>%{x}<br>$%{y:,.0f} COP<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=fechas, y=invertido, mode='lines', name='Total invertido',
        line=dict(color='#64748b', width=1, dash='dot'),
        hovertemplate='<b>Invertido</b><br>%{x}<br>$%{y:,.0f} COP<extra></extra>'
    ))
    fig.add_trace(go.Bar(
        x=fechas, y=ganancias, name='Ganancia',
        marker_color=['#10b981' if g > 0 else '#ef4444' for g in ganancias],
        opacity=0.6, yaxis='y2',
        hovertemplate='<b>Ganancia</b><br>%{x}<br>$%{y:,.0f} COP<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text="📈 Evolución del Portafolio", font=dict(size=14, color='#00d4aa')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,0.5)',
        font=dict(color='#94a3b8'), height=350,
        margin=dict(l=60, r=60, t=50, b=40),
        legend=dict(orientation='h', y=1.1, bgcolor='rgba(0,0,0,0)', font=dict(size=10)),
        hovermode='x unified',
        yaxis=dict(title="Valor COP", gridcolor='rgba(42,42,74,0.5)', tickprefix="$"),
        yaxis2=dict(title="Ganancia", overlaying='y', side='right',
                   gridcolor='rgba(42,42,74,0.2)', tickprefix="$")
    )
    fig.update_xaxes(gridcolor='rgba(42,42,74,0.5)')
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_trm_historico(historico):
    if not historico or len(historico) < 2:
        return ""
    fechas = [r['fecha'] for r in historico]
    trms   = [r['macro'].get('trm', 0) for r in historico]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas, y=trms, mode='lines+markers', name='TRM',
        line=dict(color='#f59e0b', width=2),
        fill='tozeroy', fillcolor='rgba(245,158,11,0.08)',
        hovertemplate='<b>TRM</b><br>%{x}<br>$%{y:,.0f} COP/USD<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text="💱 TRM en el Período", font=dict(size=14, color='#f59e0b')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,0.5)',
        font=dict(color='#94a3b8'), height=250,
        margin=dict(l=60, r=20, t=50, b=40), hovermode='x unified'
    )
    fig.update_xaxes(gridcolor='rgba(42,42,74,0.5)')
    fig.update_yaxes(gridcolor='rgba(42,42,74,0.5)', tickprefix="$", tickformat=",")
    return fig.to_html(include_plotlyjs=False, full_html=False)

# ============================================================
# TEMPLATE HTML
# ============================================================

TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Dashboard de Portafolio</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #080818;
            background-image:
                radial-gradient(ellipse at 20% 50%, rgba(0,212,170,0.05) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 20%, rgba(59,130,246,0.05) 0%, transparent 50%);
            color: white;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            padding: 24px; max-width: 1400px; margin: 0 auto; min-height: 100vh;
        }
        .header {
            text-align: center; margin-bottom: 30px; padding: 30px;
            background: linear-gradient(135deg, rgba(0,212,170,0.08), rgba(59,130,246,0.08));
            border-radius: 16px; border: 1px solid rgba(0,212,170,0.15);
        }
        h1 {
            font-size: 2.2rem; font-weight: 700;
            background: linear-gradient(135deg, #00d4aa, #3b82f6);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }
        .subtitle { color: #64748b; font-size: 0.85rem; }
        .tabs {
            display: flex; gap: 4px; margin-bottom: 24px;
            background: rgba(26,26,46,0.8); padding: 6px;
            border-radius: 12px; border: 1px solid rgba(42,42,74,0.8); width: fit-content;
        }
        .tab {
            padding: 10px 24px; border-radius: 8px; cursor: pointer;
            font-size: 0.9rem; font-weight: 500; color: #64748b;
            border: none; background: transparent; transition: all 0.2s;
        }
        .tab:hover { color: white; background: rgba(0,212,170,0.1); }
        .tab.active { background: linear-gradient(135deg, #00d4aa, #0891b2); color: #0f0f23; font-weight: 700; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .grid-4 { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 20px; }
        .grid-2 { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; margin-bottom: 20px; }
        .card {
            background: rgba(26,26,46,0.8); backdrop-filter: blur(10px);
            border-radius: 14px; padding: 20px;
            border: 1px solid rgba(42,42,74,0.8); transition: border-color 0.2s;
        }
        .card:hover { border-color: rgba(0,212,170,0.3); }
        .card h3 {
            color: #64748b; font-size: 0.72rem; text-transform: uppercase;
            letter-spacing: 1.5px; margin-bottom: 10px; font-weight: 500;
        }
        .metric-value { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.5px; }
        .metric-sub { font-size: 0.78rem; color: #64748b; margin-top: 4px; }
        .badge {
            display: inline-flex; align-items: center; gap: 4px;
            padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
        }
        .badge-green { background: rgba(16,185,129,0.15); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.3); }
        .badge-yellow { background: rgba(245,158,11,0.15); color: #fcd34d; border: 1px solid rgba(245,158,11,0.3); }
        .section-title {
            font-size: 1rem; font-weight: 600; color: #00d4aa;
            margin: 28px 0 14px 0; display: flex; align-items: center; gap: 8px;
        }
        .section-title::after {
            content: ''; flex: 1; height: 1px;
            background: linear-gradient(to right, rgba(0,212,170,0.3), transparent);
        }
        .analisis-box {
            background: rgba(0,212,170,0.04); border-left: 3px solid #00d4aa;
            border-radius: 0 12px 12px 0; padding: 22px 24px; line-height: 1.75;
            color: #cbd5e1; font-size: 0.92rem; margin-bottom: 20px;
        }
        .analisis-box p { margin-bottom: 14px; }
        .analisis-box p:last-child { margin-bottom: 0; }
        .fuentes-box { margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(0,212,170,0.2); }
        .fuentes-titulo { color: #64748b; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
        .fuente-item { margin-bottom: 8px; font-size: 0.82rem; color: #94a3b8; display: flex; align-items: flex-start; gap: 8px; }
        .fuente-item a { color: #00d4aa; text-decoration: none; font-size: 0.78rem; }
        .fuente-item a:hover { text-decoration: underline; }
        .tiempo-real-table { width: 100%; border-collapse: collapse; }
        .tiempo-real-table th {
            color: #64748b; font-size: 0.72rem; text-transform: uppercase;
            letter-spacing: 1px; padding: 10px 12px; text-align: left;
            border-bottom: 1px solid rgba(42,42,74,0.8); font-weight: 500;
        }
        .tiempo-real-table td { padding: 12px; border-bottom: 1px solid rgba(26,26,46,0.5); font-size: 0.9rem; }
        .tiempo-real-table tr:last-child td { border-bottom: none; }
        .tiempo-real-table tr:hover td { background: rgba(0,212,170,0.03); }
        .positivo { color: #6ee7b7; font-weight: 500; }
        .negativo { color: #fca5a5; font-weight: 500; }
        .resumen-hero {
            background: linear-gradient(135deg, rgba(0,212,170,0.08), rgba(59,130,246,0.08));
            border: 1px solid rgba(0,212,170,0.2); border-radius: 16px;
            padding: 30px; text-align: center; margin-bottom: 20px;
        }
        .resumen-hero .label { color: #64748b; font-size: 0.85rem; margin-bottom: 8px; }
        .resumen-hero .big-number { font-size: 3rem; font-weight: 800; letter-spacing: -1px; line-height: 1; }
        .resumen-hero .detalles { margin-top: 12px; color: #64748b; font-size: 0.85rem; }
        .refresh-btn {
            display: flex; align-items: center; gap: 8px; margin: 30px auto; padding: 12px 32px;
            background: linear-gradient(135deg, #00d4aa, #0891b2);
            color: #0f0f23; border: none; border-radius: 10px;
            font-size: 0.95rem; font-weight: 700; cursor: pointer; transition: opacity 0.2s, transform 0.1s;
        }
        .refresh-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .footer { text-align: center; color: #1e293b; margin-top: 20px; font-size: 0.78rem; }
        .perfil-badge {
            display: inline-block; padding: 2px 8px; border-radius: 6px;
            font-size: 0.68rem; font-weight: 600; margin-left: 6px;
        }
        .cons-badge { background: rgba(0,212,170,0.15); color: #00d4aa; }
        .agre-badge { background: rgba(245,158,11,0.15); color: #fcd34d; }
        .historico-row {
            display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
            gap: 10px; padding: 12px 0; border-bottom: 1px solid rgba(26,26,46,0.5);
            align-items: center; font-size: 0.88rem;
        }
        .historico-header {
            display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
            gap: 10px; padding: 8px 0; color: #64748b; font-size: 0.72rem;
            text-transform: uppercase; letter-spacing: 1px;
            border-bottom: 1px solid rgba(42,42,74,0.8);
        }
        .no-data { text-align: center; padding: 40px; color: #64748b; font-size: 0.9rem; }
        select option { background: #1a1a2e; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Dashboard de Portafolio</h1>
        <p class="subtitle">Última actualización: {{ ultima_actualizacion }}</p>

        {% if lista_portafolios and lista_portafolios|length > 0 %}
        <div style="margin-top:16px">
            <select onchange="window.location='/?p='+this.value"
                    style="background:#1a1a2e; color:white; border:1px solid rgba(0,212,170,0.3);
                           border-radius:8px; padding:8px 16px; font-size:0.9rem; cursor:pointer;">
                {% for p in lista_portafolios %}
                <option value="{{ p.archivo }}"
                        {{ 'selected' if p.archivo == portafolio_archivo else '' }}>
                    {{ '🟢' if p.activo else '⚪' }} {{ p.nombre }} — {{ p.propietario }}
                </option>
                {% endfor %}
            </select>
        </div>
        {% endif %}

        {% if portafolio %}
        <div style="margin-top:10px; display:flex; gap:12px; justify-content:center; flex-wrap:wrap;">
            <span class="badge badge-{{ 'green' if portafolio.perfil == 'conservador' else 'yellow' }}">
                {{ portafolio.perfil.upper() }}
            </span>
            <span style="color:#64748b; font-size:0.85rem">👤 {{ portafolio.propietario }}</span>
            <span style="color:#64748b; font-size:0.85rem">📅 Desde {{ portafolio.fecha_inicio }}</span>
        </div>
        {% endif %}
    </div>

    <!-- PESTAÑAS -->
    <div class="tabs">
        <button class="tab active" onclick="mostrarTab('hoy', this)">📅 Hoy</button>
        <button class="tab" onclick="mostrarTab('historico', this)">📈 Histórico</button>
    </div>

    <!-- PESTAÑA HOY -->
    <div id="tab-hoy" class="tab-content active">

        <div class="section-title">🧠 Análisis Económico — Contexto de Hoy</div>
        <div class="analisis-box">
            {% set partes = analisis.split('---FUENTES---') %}
            {% for parrafo in partes[0].split('\n') %}
                {% if parrafo.strip() %}<p>{{ parrafo }}</p>{% endif %}
            {% endfor %}
            {% if partes|length > 1 %}
            <div class="fuentes-box">
                <p class="fuentes-titulo">📰 Fuentes consultadas</p>
                {% for linea in partes[1].split('\n') %}
                    {% if linea.strip() and 'http' in linea %}
                        {% set pl = linea.split(' | ') %}
                        {% if pl|length > 1 %}
                        <div class="fuente-item">
                            <span>{{ pl[0].replace('• ', '') }}</span>
                            <a href="{{ pl[1] }}" target="_blank">🔗 ver noticia</a>
                        </div>
                        {% endif %}
                    {% endif %}
                {% endfor %}
            </div>
            {% endif %}
        </div>

        <div class="section-title">🌍 Indicadores Macro</div>
        <div class="grid-4">
            <div class="card">
                <h3>TRM Actual</h3>
                <div class="metric-value">${{ macro.trm | int }}</div>
                <div class="metric-sub">
                    <span class="{{ 'positivo' if macro.trm_cambio > 0 else 'negativo' }}">
                        {{ '+' if macro.trm_cambio > 0 else '' }}{{ macro.trm_cambio }}% último mes
                    </span>
                </div>
            </div>
            <div class="card">
                <h3>Inflación Colombia</h3>
                <div class="metric-value">{{ macro.inf_col }}%</div>
                <div class="metric-sub">
                    {% if macro.spread > 3 %}
                    <span class="badge badge-yellow">⚠️ Spread {{ macro.spread }}% vs USA</span>
                    {% else %}
                    <span class="badge badge-green">✅ Spread {{ macro.spread }}% — normal</span>
                    {% endif %}
                </div>
            </div>
            <div class="card">
                <h3>Tasa Banrep</h3>
                <div class="metric-value">{{ macro.banrep }}%</div>
                <div class="metric-sub">CDT referencia: <strong>{{ macro.cdt }}%</strong></div>
            </div>
            <div class="card">
                <h3>Risk Free USA</h3>
                <div class="metric-value">{{ macro.risk_free }}%</div>
                <div class="metric-sub">Treasury Bills</div>
            </div>
        </div>

        <div class="card" style="margin-bottom:20px">{{ grafica_trm | safe }}</div>

        {% if portafolio and portafolio.composicion %}
        <div class="section-title">💼 Composición del Portafolio</div>
        <div class="card" style="margin-bottom:20px">{{ torta | safe }}</div>

        <div class="section-title">📈 Comportamiento Histórico de Activos</div>
        <div class="card" style="margin-bottom:20px">{{ grafica_historico | safe }}</div>
        {% endif %}

        {% if tiempo_real %}
        <div class="section-title">⚡ Portafolio en Tiempo Real</div>
        <div class="resumen-hero">
            <div class="label">Ganancia Real Total (pesos de hoy)</div>
            <div class="big-number {{ 'positivo' if tiempo_real.ganancia_total > 0 else 'negativo' }}">
                {{ '+' if tiempo_real.ganancia_total > 0 else '' }}${{ "{:,.0f}".format(tiempo_real.ganancia_total) }}
            </div>
            <div class="detalles">
                Invertido: <strong>${{ "{:,.0f}".format(tiempo_real.total_invertido) }}</strong> →
                Hoy: <strong>${{ "{:,.0f}".format(tiempo_real.total_valor) }}</strong>
                <span class="{{ 'positivo' if tiempo_real.rentabilidad_total > 0 else 'negativo' }}">
                    ({{ '+' if tiempo_real.rentabilidad_total > 0 else '' }}{{ tiempo_real.rentabilidad_total }}%)
                </span>
            </div>
        </div>

        <div class="card" style="margin-bottom:20px">
            <table class="tiempo-real-table">
                <thead>
                    <tr>
                        <th>Activo</th><th>Precio hoy</th><th>Fracciones</th>
                        <th>Valor COP</th><th>Ganancia</th><th>Rentabilidad</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pos in tiempo_real.posiciones %}
                    <tr>
                        <td>
                            <strong>{{ pos.activo }}</strong>
                            {% if portafolio %}
                            <span class="perfil-badge {{ 'cons-badge' if portafolio.perfil == 'conservador' else 'agre-badge' }}">
                                {{ 'CONS' if portafolio.perfil == 'conservador' else 'AGRE' }}
                            </span>
                            {% endif %}
                        </td>
                        <td>${{ "{:,.2f}".format(pos.precio_hoy) }}</td>
                        <td>{{ pos.fracciones }}</td>
                        <td>${{ "{:,.0f}".format(pos.valor_hoy) }}</td>
                        <td class="{{ 'positivo' if pos.ganancia > 0 else 'negativo' }}">
                            {{ '+' if pos.ganancia > 0 else '' }}${{ "{:,.0f}".format(pos.ganancia) }}
                        </td>
                        <td class="{{ 'positivo' if pos.rentabilidad > 0 else 'negativo' }}">
                            {{ '+' if pos.rentabilidad > 0 else '' }}{{ pos.rentabilidad }}%
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="card" style="margin-bottom:20px">{{ grafica_ganancias | safe }}</div>
        {% endif %}

    </div>

    <!-- PESTAÑA HISTÓRICO -->
    <div id="tab-historico" class="tab-content">
        {% if historico and historico|length > 0 %}
        {% set ultimo  = historico[-1] %}
        {% set primero = historico[0] %}

        <div class="section-title">📊 Resumen Acumulado</div>
        <div class="grid-4">
            <div class="card">
                <h3>Días registrados</h3>
                <div class="metric-value">{{ historico|length }}</div>
                <div class="metric-sub">desde {{ primero.fecha }}</div>
            </div>
            <div class="card">
                <h3>Valor actual</h3>
                <div class="metric-value positivo">${{ "{:,.0f}".format(ultimo.resumen.total_valor) }}</div>
                <div class="metric-sub">COP</div>
            </div>
            <div class="card">
                <h3>Ganancia acumulada</h3>
                <div class="metric-value {{ 'positivo' if ultimo.resumen.ganancia_total > 0 else 'negativo' }}">
                    {{ '+' if ultimo.resumen.ganancia_total > 0 else '' }}${{ "{:,.0f}".format(ultimo.resumen.ganancia_total) }}
                </div>
                <div class="metric-sub">COP real</div>
            </div>
            <div class="card">
                <h3>Rentabilidad total</h3>
                <div class="metric-value {{ 'positivo' if ultimo.resumen.rentabilidad_total > 0 else 'negativo' }}">
                    {{ '+' if ultimo.resumen.rentabilidad_total > 0 else '' }}{{ ultimo.resumen.rentabilidad_total }}%
                </div>
                <div class="metric-sub">desde inicio</div>
            </div>
        </div>

        <div class="section-title">📈 Evolución del Portafolio</div>
        <div class="card" style="margin-bottom:20px">{{ grafica_evolucion | safe }}</div>

        <div class="section-title">💱 TRM en el Período</div>
        <div class="card" style="margin-bottom:20px">{{ grafica_trm_hist | safe }}</div>

        <div class="section-title">📋 Registro Diario</div>
        <div class="card" style="margin-bottom:20px">
            <div class="historico-header">
                <span>Fecha</span><span>TRM</span><span>Valor COP</span>
                <span>Ganancia</span><span>Rentabilidad</span>
            </div>
            {% for reg in historico|reverse %}
            <div class="historico-row">
                <span>{{ reg.fecha }}</span>
                <span>${{ "{:,.0f}".format(reg.macro.trm) }}</span>
                <span>${{ "{:,.0f}".format(reg.resumen.total_valor) }}</span>
                <span class="{{ 'positivo' if reg.resumen.ganancia_total > 0 else 'negativo' }}">
                    {{ '+' if reg.resumen.ganancia_total > 0 else '' }}${{ "{:,.0f}".format(reg.resumen.ganancia_total) }}
                </span>
                <span class="{{ 'positivo' if reg.resumen.rentabilidad_total > 0 else 'negativo' }}">
                    {{ '+' if reg.resumen.rentabilidad_total > 0 else '' }}{{ reg.resumen.rentabilidad_total }}%
                </span>
            </div>
            {% endfor %}
        </div>

        {% else %}
        <div class="card">
            <div class="no-data">
                📭 Aún no hay registros históricos.<br><br>
                El registrador guarda un snapshot diario a las 4:05pm.<br>
                También puedes correr <strong>python registrador.py</strong> manualmente.
            </div>
        </div>
        {% endif %}
    </div>

    <button class="refresh-btn" onclick="location.reload()">🔄 Actualizar Dashboard</button>
    <p class="footer">Sistema de Portafolio Automatizado — Datos en tiempo real</p>

    <script>
        function mostrarTab(tab, btn) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            btn.classList.add('active');
        }
    </script>
</body>
</html>
"""

# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.route('/')
def dashboard():
    nombre_archivo = request.args.get('p', None)

    portafolio, lista_portafolios = cargar_portafolio(nombre_archivo)
    tiempo_real = calcular_portafolio_tiempo_real(portafolio)
    macro       = cargar_macro()

    g_trm = grafica_trm(macro['trm_hist']) if 'trm_hist' in macro else ""

    colores = ['#00d4aa','#3b82f6','#8b5cf6','#f59e0b','#ef4444']
    g_torta = ""
    if portafolio and portafolio.get('composicion'):
        g_torta = grafica_torta(
            portafolio['composicion'],
            f"{portafolio['nombre']} — {portafolio['perfil'].capitalize()}",
            colores
        )

    todos_activos = list(portafolio['composicion'].keys()) if portafolio and portafolio.get('composicion') else []
    g_historico   = grafica_historico_individual(todos_activos) if todos_activos else ""
    g_ganancias   = grafica_ganancia_por_activo(tiempo_real) if tiempo_real else ""
    analisis      = generar_analisis_economico(macro, portafolio)

    historico   = portafolio.get('historial', []) if portafolio else []
    g_evolucion = grafica_evolucion_portafolio(historico)
    g_trm_hist  = grafica_trm_historico(historico)

    portafolio_archivo = nombre_archivo or (
        next((p['archivo'] for p in lista_portafolios if p['activo']), '')
        if lista_portafolios else ''
    )

    return render_template_string(
        TEMPLATE,
        macro=macro,
        portafolio=portafolio,
        lista_portafolios=lista_portafolios,
        portafolio_archivo=portafolio_archivo,
        tiempo_real=tiempo_real,
        historico=historico,
        grafica_trm=g_trm,
        torta=g_torta,
        grafica_historico=g_historico,
        grafica_ganancias=g_ganancias,
        grafica_evolucion=g_evolucion,
        grafica_trm_hist=g_trm_hist,
        analisis=analisis,
        ultima_actualizacion=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

if __name__ == "__main__":
    print("=" * 55)
    print("🌐 DASHBOARD INICIANDO...")
    print("   Abre tu navegador en: http://localhost:5000")
    print("   Presiona Ctrl+C para detener")
    print("=" * 55)
    app.run(debug=False, port=5000)