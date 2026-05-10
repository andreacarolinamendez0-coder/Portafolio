from flask import Flask, request, session, redirect, url_for, jsonify
import pandas as pd
import json, os, requests, subprocess
from datetime import datetime, timedelta
import plotly.graph_objects as go
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')
from styles import CSS
import subprocess, requests, time, threading


def arrancar_monitor():
    time.sleep(15)
    from monitor import iniciar_monitor
    from scheduler import iniciar_scheduler
    iniciar_monitor()
    iniciar_scheduler()

threading.Thread(target=arrancar_monitor, daemon=True).start()

os.makedirs("datos/macro", exist_ok=True)
os.makedirs("datos/precios", exist_ok=True)
os.makedirs("datos/portafolios", exist_ok=True)
os.makedirs("datos/Logs", exist_ok=True)

def notificar_url_ngrok():
    time.sleep(5)
    try:
        r = requests.get("http://localhost:4040/api/tunnels").json()
        url = r['tunnels'][0]['public_url']
        requests.post(f"https://api.telegram.org/bot8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8/sendMessage",
            json={"chat_id":"6999614895","text":f"🌐 URL del sistema:\n{url}"})
    except: pass

threading.Thread(target=notificar_url_ngrok, daemon=True).start()

app = Flask(__name__)
# Ruta base absoluta para que funcione en Railway y en local
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")
os.makedirs(os.path.join(DATOS_DIR, "macro"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "precios"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "portafolios"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "Logs"), exist_ok=True)
app.secret_key = os.environ.get("SECRET_KEY", "portafolio_andrea_2026_secreto")



# ── SVG logo átomo ──────────────────────────────────────────
LOGO = (
    '<svg width="18" height="18" viewBox="0 0 30 30" fill="none">'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="currentColor" stroke-width="1.3" fill="none"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="currentColor" stroke-width="1.3" fill="none" transform="rotate(60 15 15)"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="currentColor" stroke-width="1.3" fill="none" transform="rotate(120 15 15)"/>'
    '<circle cx="15" cy="15" r="2.2" fill="currentColor"/>'
    '</svg>'
)
LOGO_LG = (
    '<svg width="22" height="22" viewBox="0 0 30 30" fill="none">'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none" transform="rotate(60 15 15)"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none" transform="rotate(120 15 15)"/>'
    '<circle cx="15" cy="15" r="2.2" fill="white"/>'
    '</svg>'
)
LOGO_SM = (
    '<svg width="14" height="14" viewBox="0 0 30 30" fill="none">'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.5" fill="none"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.5" fill="none" transform="rotate(60 15 15)"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.5" fill="none" transform="rotate(120 15 15)"/>'
    '<circle cx="15" cy="15" r="2.2" fill="white"/>'
    '</svg>'
)

# ============================================================
# UTILIDADES
# ============================================================

def verificar_acceso(archivo):
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))
    from gestor_portafolio import leer_portafolio
    p = leer_portafolio(archivo)
    if not p or p.get('owner') != username:
        return redirect(url_for('mis_portafolios'))
    return None

def groq_chat(messages, system='', max_tokens=300, temperature=0.5):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    kwargs = {
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "messages": messages
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text

def cargar_macro():
    archivos = [
    os.path.join(DATOS_DIR, "macro/trm.parquet"),
    os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"),
    os.path.join(DATOS_DIR, "macro/inflacion_usa.parquet"),
    os.path.join(DATOS_DIR, "macro/risk_free.parquet"),
    os.path.join(DATOS_DIR, "macro/tasa_banrep.parquet")
]
    if any(not os.path.exists(f) for f in archivos):
        os.makedirs("datos/macro", exist_ok=True)
        os.makedirs("datos/precios", exist_ok=True)
        os.makedirs("datos/portafolios", exist_ok=True)
        try: subprocess.run(["python","recolector.py"], check=False, timeout=120)
        except: return None
    try:
        trm       = pd.read_parquet(os.path.join(DATOS_DIR, "macro/trm.parquet"))
        inf_col   = pd.read_parquet(os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"))
        inf_usa   = pd.read_parquet(os.path.join(DATOS_DIR, "macro/inflacion_usa.parquet"))
        risk_free = pd.read_parquet(os.path.join(DATOS_DIR, "macro/risk_free.parquet"))
        banrep    = pd.read_parquet(os.path.join(DATOS_DIR, "macro/tasa_banrep.parquet"))
        trm_actual   = float(trm['TRM'].iloc[-1])
        trm_hace_mes = float(trm['TRM'].iloc[-22]) if len(trm) > 22 else trm_actual
        return {
            "trm":        round(trm_actual, 2),
            "trm_cambio": round(((trm_actual-trm_hace_mes)/trm_hace_mes)*100, 2),
            "inf_col":    round(float(inf_col['Inflacion_COL'].iloc[-1]), 2),
            "inf_usa":    round(float(inf_usa['Inflacion_USA'].iloc[-1]), 2),
            "risk_free":  round(float(risk_free['Risk_Free'].iloc[-1]), 2),
            "banrep":     round(float(banrep['Tasa_Banrep'].iloc[-1]), 2),
            "cdt":        round(float(banrep['Tasa_Banrep'].iloc[-1])-0.75, 2),
            "spread":     round(float(inf_col['Inflacion_COL'].iloc[-1])-float(inf_usa['Inflacion_USA'].iloc[-1]), 2),
            "trm_hist":   trm.tail(90)
        }
    except Exception as e:
        print(f"❌ Error macro: {e}"); return None

def precio_actual_usd(ticker):
    try:
        hoy = datetime.now()
        df  = yf.download(ticker, start=(hoy-timedelta(days=5)).strftime("%Y-%m-%d"),
                          end=hoy.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True, progress=False)
        if df.empty:
            df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except: return None

def calcular_tiempo_real(portafolio):
    if not portafolio or not portafolio.get('aportes'): return None
    try:    trm_actual = float(pd.read_parquet("datos/macro/trm.parquet")['TRM'].iloc[-1])
    except: trm_actual = 4000
    inf_anual = portafolio.get('inflacion_col', 4.90)
    pos_raw   = {}
    for a in portafolio['aportes']:
        tk = a['activo']
        if tk not in pos_raw:
            pos_raw[tk] = {'fracciones':0,'invertido':0,'fecha_inicio':a['fecha']}
        pos_raw[tk]['fracciones'] += a['fracciones']
        pos_raw[tk]['invertido']  += a['monto_cop']
    resultados = []; total_inv = total_val = 0
    for tk, d in pos_raw.items():
        p = precio_actual_usd(tk)
        if p is None: continue
        val    = d['fracciones'] * p * trm_actual
        años   = (datetime.now()-datetime.strptime(d['fecha_inicio'],"%Y-%m-%d")).days/365.25
        inv_r  = d['invertido']/(1+inf_anual/100)**años
        gan    = val - inv_r
        resultados.append({'activo':tk,'fracciones':round(d['fracciones'],4),
            'precio_hoy':round(p,2),'valor_hoy':round(val,0),'invertido':round(inv_r,0),
            'ganancia':round(gan,0),'rentabilidad':round((gan/inv_r*100) if inv_r>0 else 0,2)})
        total_inv += inv_r; total_val += val
    if not resultados: return None
    return {'posiciones':resultados,'total_invertido':round(total_inv,0),
            'total_valor':round(total_val,0),'ganancia_total':round(total_val-total_inv,0),
            'rentabilidad_total':round((total_val-total_inv)/total_inv*100 if total_inv>0 else 0,2)}

def enviar_notificacion(portafolio, asunto, mensaje):
    if portafolio.get('telegram_chat_id'):
        try:
            requests.post(f"https://api.telegram.org/bot8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8/sendMessage",
                json={"chat_id":portafolio['telegram_chat_id'],"text":mensaje,"parse_mode":"HTML"},timeout=10)
        except: pass
    if portafolio.get('email'):
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            gu,gp = os.environ.get('GMAIL_USER',''),os.environ.get('GMAIL_PASS','')
            if gu and gp:
                msg = MIMEMultipart(); msg['From']=gu; msg['To']=portafolio['email']; msg['Subject']=asunto
                msg.attach(MIMEText(mensaje,'plain'))
                with smtplib.SMTP_SSL('smtp.gmail.com',465) as s: s.login(gu,gp); s.send_message(msg)
        except: pass

# ============================================================
# GRÁFICAS
# ============================================================

def grafica_trm(trm_hist):
    trm_values = trm_hist['TRM'].values.tolist()
    fechas     = [str(f)[:10] for f in trm_hist.index]
    ma7        = pd.Series(trm_values).rolling(7).mean().tolist()
    analisis_trm = ''
    try:
        import xml.etree.ElementTree as ET
        noticias = []
        for termino in ["dolar peso colombiano TRM", "tasa cambio Colombia hoy"]:
            try:
                r = requests.get(
                    f"https://news.google.com/rss/search?q={termino.replace(' ','+')}&hl=es&gl=CO&ceid=CO:es",
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
                for item in ET.fromstring(r.content).findall('.//item')[:2]:
                    t = item.find('title'); d = item.find('pubDate')
                    if t is not None:
                        noticias.append(f"- {t.text[:120]} ({d.text[:16] if d is not None else ''})")
            except:
                continue
        noticias_txt = '\n'.join(noticias) if noticias else 'Sin noticias recientes disponibles.'

        # ── Análisis técnico de la serie ──────────────────────────
        trm_series = pd.Series(trm_values)
        trm_hoy    = float(trm_values[-1])
        trm_ayer   = float(trm_values[-2]) if len(trm_values) > 1 else trm_hoy
        trm_7d     = float(trm_values[-7]) if len(trm_values) > 7 else trm_hoy
        trm_30d    = float(trm_values[-30]) if len(trm_values) > 30 else trm_hoy
        trm_90d    = float(trm_values[0])
        trm_max90  = max(trm_values)
        trm_min90  = min(trm_values)
        trm_ma7    = float(trm_series.rolling(7).mean().iloc[-1])
        trm_ma30   = float(trm_series.rolling(30).mean().iloc[-1])

        cambio_diario  = ((trm_hoy - trm_ayer) / trm_ayer) * 100
        cambio_7d      = ((trm_hoy - trm_7d) / trm_7d) * 100
        cambio_30d     = ((trm_hoy - trm_30d) / trm_30d) * 100
        cambio_90d     = ((trm_hoy - trm_90d) / trm_90d) * 100
        distancia_max  = ((trm_hoy - trm_max90) / trm_max90) * 100
        distancia_min  = ((trm_hoy - trm_min90) / trm_min90) * 100

        # Tendencia: precio vs medias móviles
        tendencia = "alcista" if trm_hoy > trm_ma7 > trm_ma30 else \
                    "bajista" if trm_hoy < trm_ma7 < trm_ma30 else "lateral"

        # Volatilidad: desviación estándar últimos 30d
        volatilidad = float(trm_series.tail(30).std())
        vol_nivel   = "alta" if volatilidad > 80 else "moderada" if volatilidad > 40 else "baja"

        # Posición relativa en el rango de 90 días (0% = mínimo, 100% = máximo)
        rango_90d   = trm_max90 - trm_min90
        posicion_rango = ((trm_hoy - trm_min90) / rango_90d * 100) if rango_90d > 0 else 50

        analisis_trm = groq_chat(
            [{'role': 'user', 'content':
              f'Eres analista cambiario senior del mercado colombiano. '
              f'Tienes los datos reales de la TRM de los últimos 90 días. Interprétalos.\n\n'

              f'DATOS TÉCNICOS DE LA TRM:\n'
              f'- Hoy: ${trm_hoy:,.0f} COP/USD\n'
              f'- Ayer: ${trm_ayer:,.0f} | Cambio diario: {cambio_diario:+.2f}%\n'
              f'- Hace 7 días: ${trm_7d:,.0f} | Cambio 7d: {cambio_7d:+.2f}%\n'
              f'- Hace 30 días: ${trm_30d:,.0f} | Cambio 30d: {cambio_30d:+.2f}%\n'
              f'- Hace 90 días: ${trm_90d:,.0f} | Cambio 90d: {cambio_90d:+.2f}%\n'
              f'- Máximo 90d: ${trm_max90:,.0f} ({distancia_max:+.1f}% vs hoy)\n'
              f'- Mínimo 90d: ${trm_min90:,.0f} ({distancia_min:+.1f}% vs hoy)\n'
              f'- Media móvil 7d: ${trm_ma7:,.0f} | Media móvil 30d: ${trm_ma30:,.0f}\n'
              f'- Tendencia: {tendencia}\n'
              f'- Volatilidad 30d: {vol_nivel} (σ = {volatilidad:,.0f} COP)\n'
              f'- Posición en rango 90d: {posicion_rango:.0f}% '
              f'(0% = mínimo histórico, 100% = máximo histórico)\n\n'

              f'NOTICIAS RECIENTES:\n{noticias_txt}\n\n'

              f'Escribe exactamente 4 oraciones, en este orden:\n'
              f'1. SITUACIÓN ACTUAL: dónde está el peso HOY dentro de su rango de 90 días y qué señala esa posición.\n'
              f'2. TENDENCIA: qué dice la relación entre precio actual y medias móviles sobre la dirección del dólar.\n'
              f'3. CAUSA: basándote en las noticias, qué factor concreto está dominando el movimiento reciente.\n'
              f'4. IMPLICACIÓN: qué significa esto para alguien que invierte en acciones americanas desde Colombia '
              f'(comprar dólares ahora vs esperar, impacto en retornos en COP).\n\n'
              f'Reglas: usa los números exactos del análisis técnico. '
              f'Sin frases genéricas. Sin asteriscos. Español directo. '
              f'Si las noticias no aportan contexto, concéntrate en los datos técnicos.'}],
            system=(
                'Eres analista cambiario senior del mercado colombiano con 15 años de experiencia. '
                'Das interpretaciones técnicas precisas, no descripciones de datos. '
                'Cuando ves una tendencia, dices qué significa para el inversionista, no solo que existe. '
                'Nunca inventas causas que no están en los datos o noticias.'
            ),
            max_tokens=400, temperature=0.2)
    except:
        pass

    import json as jm
    grafica_html = f"""
<div style="position:relative">
<div style="margin-bottom:8px">
  <p id="trm-titulo" style="color:#f5f5f7;font-size:14px;font-weight:600;letter-spacing:-0.01em;margin:0">
    Tasa Representativa del Mercado (TRM) — Últimos 90 días</p>
</div>
<div style="display:flex;gap:6px;margin-bottom:12px;align-items:center">
  <button onclick="filtrarTRM(7,this)" style="padding:5px 12px;border-radius:7px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.05);color:#6e6e73;transition:all 0.15s">7d</button>
  <button onclick="filtrarTRM(30,this)" style="padding:5px 12px;border-radius:7px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.05);color:#6e6e73;transition:all 0.15s">30d</button>
  <button onclick="filtrarTRM(60,this)" style="padding:5px 12px;border-radius:7px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.05);color:#6e6e73;transition:all 0.15s">60d</button>
  <button onclick="filtrarTRM(90,this)" style="padding:5px 12px;border-radius:7px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(0,113,227,0.5);background:rgba(0,113,227,0.2);color:#4da3ff;transition:all 0.15s">90d</button>
  <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#6e6e73;margin-left:8px">
    <span style="width:16px;height:2px;background:#0071e3;display:inline-block;border-radius:2px"></span>TRM</span>
  <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#6e6e73">
    <span style="width:16px;height:2px;background:#30d158;display:inline-block;border-radius:2px"></span>Media 7d</span>
</div>
<div id="trm-chart" style="width:100%;height:240px"></div>
</div>
<script>
(function(){{
  const fA={jm.dumps(fechas)}, tA={jm.dumps(trm_values)}, mA={jm.dumps(ma7)};
  function render(dias){{
    const n=Math.min(dias,fA.length), f=fA.slice(-n), t=tA.slice(-n), m=mA.slice(-n);
    document.getElementById('trm-titulo').textContent='Tasa Representativa del Mercado (TRM) — Últimos '+{{7:'7 días',30:'30 días',60:'60 días',90:'90 días'}}[dias];
    Plotly.react('trm-chart',[
      {{x:f,y:t,type:'scatter',mode:'lines',line:{{color:'#0071e3',width:2}},fill:'none',
        hovertemplate:'<b>$%{{y:,.0f}} COP/USD</b><br>%{{x}}<extra>TRM</extra>'}},
      {{x:f,y:m,type:'scatter',mode:'lines',line:{{color:'#30d158',width:1.5,dash:'dot'}},opacity:0.8,
        hovertemplate:'<b>$%{{y:,.0f}} COP/USD</b><br>%{{x}}<extra>Media 7d</extra>'}}
    ],{{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(17,17,17,0.6)',
        margin:{{l:80,r:16,t:8,b:36}},showlegend:false,hovermode:'x unified',
        hoverlabel:{{bgcolor:'rgba(12,12,12,0.97)',bordercolor:'rgba(255,255,255,0.1)',
          font:{{size:12,color:'#f5f5f7',family:'DM Sans,sans-serif'}}}},
        xaxis:{{gridcolor:'rgba(255,255,255,0.05)',color:'#6e6e73',tickfont:{{size:11,family:'DM Sans,sans-serif',color:'#6e6e73'}}}},
        yaxis:{{gridcolor:'rgba(255,255,255,0.05)',color:'#6e6e73',tickfont:{{size:11,family:'DM Sans,sans-serif',color:'#6e6e73'}},
          tickformat:'$,.0f',ticksuffix:' COP',range:[3000,Math.max(...t)*1.05],autorange:false}}
    }},{{responsive:true,displayModeBar:false}});
  }}
  window.filtrarTRM=function(dias,btn){{
    document.querySelectorAll('[onclick^="filtrarTRM"]').forEach(b=>{{b.style.background='rgba(255,255,255,0.05)';b.style.color='#6e6e73';b.style.border='1px solid rgba(255,255,255,0.08)';}});
    btn.style.background='rgba(0,113,227,0.2)';btn.style.color='#4da3ff';btn.style.border='1px solid rgba(0,113,227,0.5)';
    render(dias);
  }};
  render(90);
}})();
</script>
"""
    analisis_html = (
        '<div style="margin-top:12px;padding:14px 16px;background:rgba(255,255,255,0.04);'
        'border:1px solid rgba(255,255,255,0.07);border-radius:12px">'
        '<div style="font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;color:#6e6e73;margin-bottom:8px">Análisis IA</div>'
        f'<p style="font-size:0.82rem;color:#a1a1a6;line-height:1.6;margin:0">{analisis_trm}</p>'
        '</div>'
    ) if analisis_trm else ''
    fuente_html = '<div style="margin-top:8px;font-size:0.7rem;color:#6e6e73;text-align:right">Fuente: Banco de la República</div>'
    return grafica_html + analisis_html + fuente_html

def grafica_torta(pesos, titulo):
    cf = ['rgba(0,113,227,0.45)','rgba(48,209,88,0.45)','rgba(255,214,10,0.45)',
          'rgba(255,69,58,0.45)','rgba(191,90,242,0.45)','rgba(255,159,10,0.45)',
          'rgba(50,173,230,0.45)','rgba(52,199,89,0.45)']
    cb = ['rgba(0,113,227,0.9)','rgba(48,209,88,0.9)','rgba(255,214,10,0.9)',
          'rgba(255,69,58,0.9)','rgba(191,90,242,0.9)','rgba(255,159,10,0.9)',
          'rgba(50,173,230,0.9)','rgba(52,199,89,0.9)']
    n = len(pesos)
    fig = go.Figure(go.Pie(
        labels=list(pesos.keys()), values=[v*100 for v in pesos.values()],
        hole=0.55, marker=dict(colors=cf[:n], line=dict(color=cb[:n], width=3)),
        textinfo='label+percent', textposition='inside',
        textfont=dict(color='rgba(255,255,255,0.95)', size=13, family='DM Sans'),
        hovertemplate='<b>%{label}</b><br>%{percent:.1%}<extra></extra>',
        insidetextorientation='radial', rotation=45))
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#a1a1a6', family='DM Sans'), height=300,
        margin=dict(l=10,r=10,t=20,b=10), showlegend=False,
        hoverlabel=dict(bgcolor='rgba(12,12,12,0.97)', bordercolor='rgba(255,255,255,0.1)',
            font=dict(size=12,color='#f5f5f7',family='DM Sans')),
        annotations=[dict(text=titulo, x=0.5, y=0.5,
            font=dict(size=13,color='#6e6e73',family='DM Sans'),
            showarrow=False, xanchor='center', yanchor='middle')])
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_ganancias(tiempo_real):
    if not tiempo_real or not tiempo_real['posiciones']: return ""
    pos = sorted(tiempo_real['posiciones'], key=lambda x: x['ganancia'], reverse=True)
    act = [p['activo'] for p in pos]; gan = [p['ganancia'] for p in pos]; ren = [p['rentabilidad'] for p in pos]
    cf = ['rgba(48,209,88,0.45)' if g>0 else 'rgba(255,69,58,0.45)' for g in gan]
    cb = ['rgba(48,209,88,0.95)' if g>0 else 'rgba(255,69,58,0.95)' for g in gan]
    ct = ['rgba(48,209,88,0.9)' if g>0 else 'rgba(255,69,58,0.9)' for g in gan]
    fig = go.Figure(go.Bar(x=act, y=gan,
        marker=dict(color=cf, line=dict(color=cb,width=1.5), cornerradius=8),
        text=[f'${g:,.0f}<br><span style="font-size:10px">{r:+.1f}%</span>' for g,r in zip(gan,ren)],
        textposition='outside', textfont=dict(color=ct,size=12,family='DM Sans'),
        hovertemplate='<b>%{x}</b><br>$%{y:,.0f} COP<extra></extra>'))
    fig.update_layout(title=dict(text='Ganancia por Activo (COP)',font=dict(size=13,color='#6e6e73',family='DM Sans')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,17,17,0.6)',
        font=dict(color='#a1a1a6',family='DM Sans',size=12), height=320,
        margin=dict(l=60,r=20,t=50,b=40), showlegend=False,
        hoverlabel=dict(bgcolor='rgba(12,12,12,0.97)',bordercolor='rgba(255,255,255,0.1)',
            font=dict(size=12,color='#f5f5f7',family='DM Sans')))
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.04)',color='#6e6e73',tickfont=dict(size=12,family='DM Sans',color='#6e6e73'))
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)',color='#6e6e73',tickfont=dict(size=12,family='DM Sans',color='#6e6e73'),
        zeroline=True,zerolinecolor='rgba(255,255,255,0.12)',zerolinewidth=1,tickformat='$,.0f')
    return fig.to_html(include_plotlyjs=False, full_html=False)

def grafica_evolucion(historico):
    if not historico or len(historico)<2: return ""
    fechas=[r['fecha'] for r in historico]; vals=[r['resumen']['total_valor'] for r in historico]
    invs=[r['resumen']['total_invertido'] for r in historico]; gans=[r['resumen']['ganancia_total'] for r in historico]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fechas,y=vals,mode='lines+markers',name='Valor',
        line=dict(color='#0071e3',width=2),fill='tozeroy',fillcolor='rgba(0,113,227,0.08)',
        hovertemplate='<b>Valor</b><br>%{x}<br>$%{y:,.0f}<extra></extra>'))
    fig.add_trace(go.Scatter(x=fechas,y=invs,mode='lines',name='Invertido',
        line=dict(color='#6e6e73',width=1,dash='dot'),
        hovertemplate='<b>Invertido</b><br>%{x}<br>$%{y:,.0f}<extra></extra>'))
    fig.add_trace(go.Bar(x=fechas,y=gans,name='Ganancia',
        marker_color=['#30d158' if g>0 else '#ff453a' for g in gans],
        opacity=0.6,yaxis='y2',
        hovertemplate='<b>Ganancia</b><br>%{x}<br>$%{y:,.0f}<extra></extra>'))
    fig.update_layout(title=dict(text="Evolución del Portafolio",font=dict(size=13,color='#a1a1a6',family='DM Sans')),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(17,17,17,0.8)',
        font=dict(color='#a1a1a6',family='DM Sans'),height=350,
        margin=dict(l=60,r=60,t=50,b=40),
        legend=dict(orientation='h',y=1.1,bgcolor='rgba(0,0,0,0)',font=dict(size=10)),
        hovermode='x unified',
        yaxis=dict(title="Valor COP",gridcolor='rgba(255,255,255,0.06)',color='#6e6e73',tickprefix="$"),
        yaxis2=dict(title="Ganancia",overlaying='y',side='right',gridcolor='rgba(255,255,255,0.04)',color='#6e6e73',tickprefix="$"))
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.06)',color='#6e6e73')
    return fig.to_html(include_plotlyjs=False, full_html=False)

# ============================================================
# HELPERS
# ============================================================

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30" fill="none">'
    '<rect width="30" height="30" rx="6" fill="#000000"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none" transform="rotate(60 15 15)"/>'
    '<ellipse cx="15" cy="15" rx="10" ry="4" stroke="white" stroke-width="1.3" fill="none" transform="rotate(120 15 15)"/>'
    '<circle cx="15" cy="15" r="2.2" fill="white"/>'
    '</svg>'
)

def pagina(titulo, contenido, plotly=False):
    import base64
    ps = '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>' if plotly else ''
    favicon_b64 = base64.b64encode(FAVICON_SVG.encode()).decode()
    favicon_tag = f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,{favicon_b64}">'
    return ('<!DOCTYPE html><html lang="es"><head>'
            '<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>{titulo}</title>' + favicon_tag + ps + CSS + '</head><body>' + contenido + '</body></html>')

def nav_html(archivo, activa):
    def tab(href, label, nombre):
        s = 'background:#1c1c1e;color:#f5f5f7;border:1px solid rgba(255,255,255,0.1)' if activa==nombre else 'background:transparent;color:#6e6e73;border:none'
        return f'<a href="{href}" style="{s};padding:7px 16px;border-radius:7px;font-size:12px;text-decoration:none;font-family:inherit">{label}</a>'
    return (
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:24px">'
        f'<div style="width:32px;height:32px;background:#0a0a0a;border-radius:8px;'
        f'display:flex;align-items:center;justify-content:center;'
        f'border:1px solid rgba(255,255,255,0.08);flex-shrink:0;color:white">' + LOGO + '</div>'
        f'<div style="display:flex;gap:2px;background:rgba(255,255,255,0.05);padding:4px;border-radius:10px">'
        + tab(f'/portafolio/{archivo}','Dashboard','dashboard')
        + tab(f'/analista/{archivo}','Analista','analista')
        + tab(f'/seguimiento/{archivo}','Seguimiento','seguimiento')
        + tab(f'/bot/{archivo}','Asistente','bot')
        + tab(f'/monitor/{archivo}','Monitor','monitor')
        + tab(f'/config/{archivo}','Config','config')
        + tab(f'/settings','Mi Perfil','settings')
        + f'</div>'
        f'<a href="/mis-portafolios" style="margin-left:auto;color:#6e6e73;font-size:12px;text-decoration:none;margin-right:8px">← Portafolios</a>'
        f'<a href="/logout" style="color:#6e6e73;font-size:12px;text-decoration:none">Salir</a>'
        f'</div>'
    )

def _dropdown_portafolios(archivo_actual):
    from gestor_portafolio import listar_portafolios_de_usuario
    username    = session.get('username','')
    portafolios = listar_portafolios_de_usuario(username)
    if len(portafolios) <= 1:
        return ''
    opciones = ''
    for p in portafolios:
        selected = 'font-weight:600;color:#f5f5f7' if p['archivo'] == archivo_actual else 'color:#a1a1a6'
        opciones += (
            f'<a href="/portafolio/{p["archivo"]}" style="display:block;padding:8px 14px;'
            f'text-decoration:none;font-size:12px;{selected};'
            f'border-bottom:1px solid rgba(255,255,255,0.06);white-space:nowrap">'
            f'{p["nombre"]}</a>'
        )
    return (
        '<div style="position:relative;display:inline-block">'
        '<button onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" '
        'style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);'
        'border-radius:6px;padding:3px 8px;cursor:pointer;color:#a1a1a6;font-size:11px;'
        'font-family:DM Sans,sans-serif">▾</button>'
        '<div style="display:none;position:absolute;top:100%;left:0;z-index:100;'
        'background:#0a0a0a;border:1px solid rgba(255,255,255,0.1);'
        'border-radius:10px;overflow:hidden;margin-top:4px;min-width:160px;'
        'box-shadow:0 8px 32px rgba(0,0,0,0.6)">'
        + opciones +
        '</div></div>'
    )

def header_portafolio(archivo, portafolio, perfil_badge, tiempo_real):
    g_color = '#30d158' if tiempo_real and tiempo_real['ganancia_total']>0 else '#ff453a'
    r_sign  = '+' if tiempo_real and tiempo_real['rentabilidad_total']>0 else ''
    metricas = ''
    if tiempo_real:
        metricas = (
            f'<div style="text-align:right"><p style="color:#6e6e73;font-size:10px;margin:0;letter-spacing:0.04em;text-transform:uppercase">Valor hoy</p>'
            f'<p style="color:{g_color};font-size:15px;font-weight:600;margin:0;letter-spacing:-0.02em">${tiempo_real["total_valor"]:,.0f}</p></div>'
            f'<div style="text-align:right"><p style="color:#6e6e73;font-size:10px;margin:0;letter-spacing:0.04em;text-transform:uppercase">Ganancia</p>'
            f'<p style="color:{g_color};font-size:15px;font-weight:600;margin:0;letter-spacing:-0.02em">{r_sign}{tiempo_real["rentabilidad_total"]}%</p></div>'
        )
    return (
        '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:16px;padding:16px 24px;margin-bottom:20px">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">'
        '<div style="display:flex;align-items:center;gap:14px">'
        f'<div style="width:42px;height:42px;background:#0a0a0a;border-radius:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1px solid rgba(255,255,255,0.1);color:white">{LOGO_LG}</div>'
        '<div>'
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<h1 style="color:#f5f5f7;font-size:17px;font-weight:600;margin:0;letter-spacing:-0.02em">{portafolio["nombre"]}</h1>'
        + _dropdown_portafolios(archivo) +
        f'</div>'
        f'<p style="color:#6e6e73;font-size:12px;margin:2px 0 0">{portafolio["propietario"]} · {perfil_badge} · Desde {portafolio["fecha_inicio"]}</p>'
        '</div></div>'
        f'<div style="display:flex;gap:24px;align-items:center">{metricas}'
        f'<a href="/logout" style="color:#6e6e73;font-size:12px;text-decoration:none">Salir</a>'
        '</div></div>'
        + nav_html(archivo, 'dashboard').replace('margin-bottom:24px', 'margin-bottom:0')
        + '</div>'
    )

# ============================================================
# INICIO / MIS PORTAFOLIOS
# ============================================================

@app.route('/')
def inicio():
    if not session.get('username'):
        return redirect(url_for('login'))
    return redirect(url_for('mis_portafolios'))

@app.route('/mis-portafolios')
def mis_portafolios():
    if not session.get('username'):
        return redirect(url_for('login'))
    from gestor_portafolio import listar_portafolios_de_usuario
    username    = session['username']
    portafolios = listar_portafolios_de_usuario(username)
    cards = ''
    n_activos = sum(1 for p in portafolios if p.get('monitoreo_activo'))
    aviso_duplicado = ''
    if n_activos > 1:
        aviso_duplicado = (
            '<div style="background:rgba(255,69,58,0.08);border:1px solid rgba(255,69,58,0.2);'
            'border-radius:12px;padding:12px 16px;margin-bottom:16px;display:flex;gap:10px;align-items:center">'
            '<span style="font-size:18px">⚠️</span>'
            '<div>'
            '<p style="color:#ff453a;font-size:13px;font-weight:500;margin:0 0 2px">Más de un portafolio monitoreado</p>'
            '<p style="color:#6e6e73;font-size:12px;margin:0">Solo debería estar activo uno a la vez. '
            'Entra al Monitor de cada portafolio y desactiva los que no necesites.</p>'
            '</div></div>'
        )
 
    if portafolios:
        for p in portafolios:
            pb = f'<span class="badge badge-{"yellow" if p["perfil"]=="agresivo" else "blue"}">{p["perfil"].upper()}</span>'
            es_monitoreado = p.get('monitoreo_activo', False)
            borde = 'rgba(48,209,88,0.25)' if es_monitoreado else 'rgba(255,255,255,0.07)'
            fondo = 'rgba(48,209,88,0.04)' if es_monitoreado else 'rgba(255,255,255,0.04)'
 
            if es_monitoreado:
                btn = (
                    '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">'
                    '<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#30d158;'
                    'padding:5px 12px;border-radius:980px;background:rgba(48,209,88,0.08);'
                    'border:1px solid rgba(48,209,88,0.2)">'
                    '<span style="width:5px;height:5px;border-radius:50%;background:#30d158;'
                    'animation:pulse 2s infinite;display:inline-block"></span>'
                    'Monitoreando activamente</span>'
                    f'<span style="font-size:10px;color:#6e6e73">Este es el portafolio en seguimiento</span>'
                    '</div>'
                )
            else:
                btn = (
                    f'<form method="POST" action="/activar-portafolio/{p["archivo"]}" '
                    f'style="display:inline" onsubmit="event.stopPropagation()">'
                    f'<button type="submit" onclick="event.stopPropagation()" '
                    f'style="padding:5px 14px;border-radius:980px;font-size:11px;'
                    f'font-family:DM Sans,sans-serif;cursor:pointer;'
                    f'border:1px solid rgba(255,255,255,0.12);'
                    f'background:rgba(255,255,255,0.06);color:#6e6e73">'
                    f'Activar monitoreo</button></form>'
                )
 
            cards += (
                f'<div style="position:relative;margin-bottom:12px">'
                f'<a href="/portafolio/{p["archivo"]}" style="display:block;text-decoration:none;'
                f'background:{fondo};border:1px solid {borde};'
                f'border-radius:18px;padding:24px 28px;'
                f'backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);transition:all 0.2s ease"'
                f' onmouseover="this.style.borderColor=\'{"rgba(48,209,88,0.4)" if es_monitoreado else "rgba(255,255,255,0.16)"}\';this.style.transform=\'translateY(-1px)\'"'
                f' onmouseout="this.style.borderColor=\'{borde}\';this.style.transform=\'translateY(0)\'">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">'
                f'<div>'
                f'<div style="font-size:1.15rem;font-weight:600;color:#f5f5f7;margin-bottom:2px;letter-spacing:-0.02em">'
                f'{p["nombre"]}'
                + (' <span style="font-size:11px;color:#30d158;font-weight:400">● en vivo</span>' if es_monitoreado else '')
                + f'</div>'
                f'<div style="color:#6e6e73;font-size:0.85rem">{p["propietario"]}</div></div>'
                f'<div style="display:flex;gap:6px;align-items:center">{pb}</div></div>'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">'
                f'<div style="color:#6e6e73;font-size:0.78rem">Desde {p["fecha_inicio"]}</div>'
                f'{btn}</div></a></div>'
            )
    else:
        cards = (
            '<div class="card"><div class="no-data">No tienes portafolios aún.<br><br>'
            '<a href="/nuevo" class="btn btn-primary" '
            'style="display:inline-flex;width:auto;margin-top:16px">Crear mi primer portafolio</a>'
            '</div></div>'
        )

    contenido = (
        '<div class="container"><div class="header">'
        '<h1>Sistema de Portafolio</h1><p class="subtitle">Gestión inteligente de inversiones</p></div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">'
        '<h2 style="margin:0">Mis Portafolios</h2>'
        f'<div style="display:flex;gap:10px;align-items:center">'
        f'<span style="color:#6e6e73;font-size:13px">Hola, {username}</span>'
        + (f'<a href="/admin" class="btn btn-secondary" style="font-size:12px;padding:7px 14px">🛡 Admin</a>' if session.get('es_admin') else '') +
        '<a href="/settings" class="btn btn-secondary" style="font-size:12px;padding:7px 14px">Mi Perfil</a>'
        '<a href="/logout" class="btn btn-secondary" style="font-size:12px;padding:7px 14px">Cerrar sesión</a>'
        '<a href="/nuevo" class="btn btn-primary">+ Crear Portafolio</a></div></div>'
        + aviso_duplicado + cards + '</div>')
    return pagina('Mis Portafolios', contenido)

# ============================================================
# REGISTRO / LOGIN / LOGOUT
# ============================================================

@app.route('/register', methods=['GET','POST'])
def register():
    if session.get('username'):
        return redirect(url_for('mis_portafolios'))
    error = ''
    if request.method == 'POST':
        from gestor_portafolio import registrar_usuario
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        telegram = request.form.get('telegram', '').strip()
        if not username or not email or not password:
            error = 'Nombre, email y contraseña son obligatorios.'
        elif len(password) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres.'
        else:
            resultado = registrar_usuario(username, email, password, telegram)
            if resultado is True:
                session['username'] = username
                session['es_admin'] = False
                session.permanent   = True
                from gestor_portafolio import registrar_actividad
                ip          = request.headers.get('X-Forwarded-For', request.remote_addr or '—').split(',')[0].strip()
                dispositivo = request.headers.get('User-Agent', '—')[:120]
                registrar_actividad('registro_nuevo', username, email=email,
                    detalle='Nuevo usuario registrado', ip=ip, dispositivo=dispositivo)
                # Email de bienvenida
                try:
                    import smtplib
                    from email.mime.multipart import MIMEMultipart
                    from email.mime.text import MIMEText
                    gmail_user = os.environ.get('GMAIL_USER', '')
                    gmail_pass = os.environ.get('GMAIL_PASS', '')
                    if gmail_user and gmail_pass and email:
                        msg = MIMEMultipart('alternative')
                        msg['From']    = f"Sistema de Portafolio <{gmail_user}>"
                        msg['To']      = email
                        msg['Subject'] = "¡Bienvenido al Sistema de Portafolio!"
                        html = f"""
                        <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:32px;background:#0a0c10;color:#e8eaf2;border-radius:16px">
                            <h1 style="font-size:1.5rem;margin-bottom:8px">👋 Hola, {username}</h1>
                            <p style="color:#8892b0;margin-bottom:24px">Tu cuenta ha sido creada exitosamente.</p>
                            <div style="background:#1d2235;border-radius:12px;padding:20px;margin-bottom:24px">
                                <p style="margin:0 0 8px"><strong>Usuario:</strong> {username}</p>
                                <p style="margin:0"><strong>Email:</strong> {email}</p>
                            </div>
                            <p style="color:#8892b0;font-size:13px">
                                Ya puedes crear tus portafolios, activar el monitor de mercado
                                y usar el analista IA para optimizar tus inversiones.
                            </p>
                            <p style="color:#4a5578;font-size:11px;margin-top:24px">
                                Sistema de Portafolio de Inversión
                            </p>
                        </div>
                        """
                        msg.attach(MIMEText(html, 'html'))
                        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                            server.login(gmail_user, gmail_pass)
                            server.send_message(msg)
                        print(f"✅ Email bienvenida enviado a {email}")
                except Exception as e:
                    print(f"❌ Error enviando email bienvenida: {e}")
                return redirect(url_for('mis_portafolios'))
            else:
                error = resultado
    err_html = f'<div class="alert alert-error">{error}</div>' if error else ''
    contenido = (
        '<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px">'
        '<div style="width:100%;max-width:380px">'
        '<div style="text-align:center;margin-bottom:28px">'
        f'<div style="font-size:1.8rem;margin-bottom:10px">' + LOGO_LG + '</div>'
        '<h1 style="font-size:1.3rem;margin-bottom:4px;letter-spacing:-0.02em;color:#f5f5f7">Crear cuenta</h1>'
        '<p style="color:#6e6e73;font-size:0.82rem;margin:0">Accede a tu sistema de portafolio</p></div>'
        + err_html +
        '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:18px;padding:22px;backdrop-filter:blur(20px)">'
        '<form method="POST">'
        '<div style="margin-bottom:14px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">Nombre de usuario</label>'
        '<input type="text" name="username" class="form-input" placeholder="ej: andrea" autofocus required>'
        '</div>'
        '<div style="margin-bottom:14px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">Email</label>'
        '<input type="email" name="email" class="form-input" placeholder="tu@email.com" required>'
        '</div>'
        '<div style="margin-bottom:14px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">Contraseña</label>'
        '<input type="password" name="password" class="form-input" placeholder="Mínimo 6 caracteres" required>'
        '</div>'
        '<div style="margin-bottom:18px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">'
        'Telegram Chat ID <span style="font-weight:400;opacity:0.6">(opcional — para alertas)</span></label>'
        '<input type="text" name="telegram" class="form-input" placeholder="ej: 6999614895">'
        '<p style="color:#3d3d3f;font-size:11px;margin-top:6px">Envía /start a @userinfobot para obtener tu ID</p>'
        '</div>'
        '<button type="submit" id="btn-registro" class="btn btn-primary" style="border-radius:12px;font-size:0.9rem;padding:12px" '
        'onclick="this.disabled=true;this.textContent=\'Creando cuenta...\';this.form.submit()">Crear cuenta</button>'
        '</form></div>'
        '<div style="text-align:center;margin-top:18px">'
        '<a href="/login" style="color:#6e6e73;font-size:0.78rem;text-decoration:none">¿Ya tienes cuenta? Inicia sesión</a>'
        '</div></div></div>')
    return pagina('Registro', contenido)

@app.route('/login', methods=['GET','POST'])
def login():
    if session.get('username'):
        return redirect(url_for('mis_portafolios'))
    error = ''
    if request.method == 'POST':
        from gestor_portafolio import login_usuario
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        usuario  = login_usuario(email, password)
        ip          = request.headers.get('X-Forwarded-For', request.remote_addr or '—').split(',')[0].strip()
        dispositivo = request.headers.get('User-Agent', '—')[:120]
        if usuario and not usuario.get('bloqueado'):
            session['username'] = usuario['username']
            session['es_admin'] = usuario.get('es_admin', False)
            session.permanent   = True
            from gestor_portafolio import registrar_actividad
            registrar_actividad('login_ok', usuario['username'], email=email,
                detalle='Login exitoso', ip=ip, dispositivo=dispositivo)
            try:
                t = threading.Thread(
                    target=lambda: subprocess.run(["python","recolector.py"], check=False, timeout=120),
                    daemon=True
                )
                t.start()
            except: pass
            return redirect(url_for('mis_portafolios'))
        from gestor_portafolio import registrar_actividad
        if usuario and usuario.get('bloqueado'):
            minutos = usuario.get('minutos', 15)
            registrar_actividad('login_fail', usuario.get('username', email), email=email,
                detalle=f'Cuenta bloqueada — {minutos} min restantes', ip=ip, dispositivo=dispositivo)
            error = f'Cuenta bloqueada por demasiados intentos. Intenta en {minutos} minuto{"s" if minutos != 1 else ""}.'
        else:
            registrar_actividad('login_fail', email, email=email,
                detalle='Contraseña incorrecta', ip=ip, dispositivo=dispositivo)
            error = 'Email o contraseña incorrectos.'
    err_html = f'<div class="alert alert-error">{error}</div>' if error else ''
    contenido = (
        '<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px">'
        '<div style="width:100%;max-width:340px">'
        '<div style="text-align:center;margin-bottom:28px">'
        f'<div style="font-size:1.8rem;margin-bottom:10px">' + LOGO_LG + '</div>'
        '<h1 style="font-size:1.3rem;margin-bottom:4px;letter-spacing:-0.02em;color:#f5f5f7">Sistema de Portafolio</h1>'
        '<p style="color:#6e6e73;font-size:0.82rem;margin:0">Ingresa con tu cuenta</p></div>'
        + err_html +
        '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:18px;padding:22px;backdrop-filter:blur(20px)">'
        '<form method="POST">'
        '<div style="margin-bottom:14px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">Email</label>'
        '<input type="email" name="email" class="form-input" placeholder="tu@email.com" autofocus required>'
        '</div>'
        '<div style="margin-bottom:14px">'
        '<label style="display:block;font-size:0.75rem;color:#6e6e73;letter-spacing:0.04em;margin-bottom:8px">Contraseña</label>'
        '<input type="password" name="password" class="form-input" placeholder="••••••••" required>'
        '</div>'
        '<button type="submit" class="btn btn-primary" style="border-radius:12px;font-size:0.9rem;padding:12px">Entrar</button>'
        '</form></div>'
        '<div style="text-align:center;margin-top:18px">'
        '<a href="/register" style="color:#6e6e73;font-size:0.78rem;text-decoration:none">¿No tienes cuenta? Regístrate</a>'
        '</div></div></div>')
    return pagina('Iniciar sesión', contenido)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================================
# ACTIVAR PORTAFOLIO
# ============================================================

@app.route('/activar-portafolio/<archivo>', methods=['POST'])
def activar_portafolio_route(archivo):
    from gestor_portafolio import activar_portafolio
    activar_portafolio(archivo)
    return redirect(url_for('mis_portafolios'))

# ============================================================
# NUEVO PORTAFOLIO
# ============================================================

@app.route('/nuevo', methods=['GET','POST'])
def nuevo_portafolio():
    if not session.get('username'):
        return redirect(url_for('login'))
    mensaje = ''; error = ''
    if request.method == 'POST':
        from gestor_portafolio import crear_portafolio_para_usuario
        try:
            username    = session['username']
            nombre      = request.form.get('nombre', '').strip()
            propietario = request.form.get('propietario', '').strip()
            perfil      = request.form.get('perfil', 'agresivo')
            inv         = float(request.form.get('inversion', '0').replace(',','').replace('.','') or 0)
            aporte      = float(request.form.get('aporte', '0').replace(',','').replace('.','') or 0)
            freq        = int(request.form.get('frecuencia', '1'))
            if not nombre or not propietario:
                error = 'Nombre y propietario son obligatorios.'
            else:
                r = crear_portafolio_para_usuario(username, nombre, perfil, propietario, inv, aporte, freq)
                if r:
                    mensaje = f'Portafolio "{nombre}" creado exitosamente.'
                else:
                    error = 'Ya existe un portafolio con ese nombre.'
        except Exception as e:
            error = f'Error: {str(e)}'
    msg_html  = f'<div class="alert alert-success">{mensaje}</div>' if mensaje else ''
    err_html  = f'<div class="alert alert-error">{error}</div>' if error else ''
    link_html = ('<div class="card"><a href="/mis-portafolios" class="btn btn-secondary" style="width:auto;display:inline-flex">Ver mis portafolios</a></div>') if mensaje else ''
    contenido = (
        '<div class="container" style="max-width:600px">'
        '<div style="margin-bottom:24px"><a href="/mis-portafolios" style="color:#6e6e73;font-size:0.85rem;text-decoration:none">← Volver</a></div>'
        '<h2>Crear Nuevo Portafolio</h2>' + msg_html + err_html +
        '<div class="card"><form method="POST"><div class="grid-2">'
        '<div class="form-group"><label>Nombre *</label><input type="text" name="nombre" class="form-input" placeholder="Ej: Agresivo Andrea 2026" required></div>'
        '<div class="form-group"><label>Propietario *</label><input type="text" name="propietario" class="form-input" placeholder="Ej: Andrea" required></div>'
        '</div><div class="form-group"><label>Perfil de riesgo</label><select name="perfil" class="form-select">'
        '<option value="agresivo">Agresivo — mayor riesgo, mayor retorno (10 años)</option>'
        '<option value="conservador">Conservador — menor riesgo, más estable (5 años)</option>'
        '</select></div><div class="grid-2">'
        '<div class="form-group"><label>Inversión inicial COP *</label><input type="number" name="inversion" class="form-input" placeholder="Ej: 1000000" required></div>'
        '<div class="form-group"><label>Aporte DCA COP (opcional)</label><input type="number" name="aporte" class="form-input" placeholder="Ej: 500000"></div>'
        '</div><div class="form-group"><label>Frecuencia de aportes</label><select name="frecuencia" class="form-select">'
        '<option value="1">Mensual</option><option value="3">Trimestral</option><option value="12">Anual</option>'
        '</select></div>'
        '<button type="submit" class="btn btn-primary">Crear Portafolio</button>'
        '</form></div>' + link_html + '</div>')
    return pagina('Nuevo Portafolio', contenido)

# ============================================================
# DASHBOARD PORTAFOLIO
# ============================================================

@app.route('/portafolio/<archivo>')
def dashboard_portafolio(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio
    portafolio  = leer_portafolio(archivo)
    if not portafolio: return redirect(url_for('mis_portafolios'))
    macro       = cargar_macro()
    tiempo_real = calcular_tiempo_real(portafolio)
    historico   = portafolio.get('historial', [])
    composicion = portafolio.get('composicion', {})
    g_trm       = grafica_trm(macro['trm_hist']) if macro and 'trm_hist' in macro else ''
    g_torta     = grafica_torta(composicion, portafolio['nombre']) if composicion else ''
    g_ganancias = grafica_ganancias(tiempo_real) if tiempo_real else ''
    g_evolucion = grafica_evolucion(historico)
    entrados    = set(a['activo'] for a in portafolio.get('aportes',[]))
    pendientes  = [a for a in composicion if a not in entrados]
    entrados_l  = [a for a in composicion if a in entrados]
    perfil      = portafolio['perfil']
    pb          = f'<span class="badge badge-{"yellow" if perfil=="agresivo" else "blue"}">{perfil.upper()}</span>'

    if macro:
        tc = 'positivo' if macro['trm_cambio']>0 else 'negativo'
        ts = '+' if macro['trm_cambio']>0 else ''
        macro_html = (
            '<div class="section-title">Indicadores Macro</div><div class="grid-4">'
            f'<div class="card"><h3>TRM Actual</h3><div class="metric-value">${macro["trm"]:,.0f}</div>'
            f'<div class="metric-sub"><span class="{tc}">{ts}{macro["trm_cambio"]}% último mes</span></div></div>'
            f'<div class="card"><h3>Inflación Colombia</h3><div class="metric-value">{macro["inf_col"]}%</div>'
            f'<div class="metric-sub">USA: {macro["inf_usa"]}% · Spread: {macro["spread"]}%</div></div>'
            f'<div class="card"><h3>Tasa Banrep</h3><div class="metric-value">{macro["banrep"]}%</div>'
            f'<div class="metric-sub">CDT ref: {macro["cdt"]}%</div></div>'
            f'<div class="card"><h3>Risk Free USA</h3><div class="metric-value">{macro["risk_free"]}%</div>'
            '<div class="metric-sub">Treasury Bills</div></div></div>'
            f'<div class="card">{g_trm}</div>')
    else:
        macro_html = '<div class="card cargando">⏳ Cargando datos del mercado...</div>'

    entradas_html = ''
    if composicion:
        fe = ''.join(f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:center"><span style="color:#f5f5f7">{a}</span><span class="badge badge-green">ENTRADO</span></div>' for a in entrados_l) or '<div style="color:#6e6e73;padding:8px 0">Sin entradas aún</div>'
        fp = ''.join(f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:center"><span style="color:#f5f5f7">{a}</span><span class="badge badge-yellow">PENDIENTE</span></div>' for a in pendientes) or '<div style="color:#30d158;padding:8px 0">Ya entraste a todos</div>'
        entradas_html = ('<div class="section-title">Estado de Entradas</div><div class="grid-2">'
            f'<div class="card"><h3>Ya entraste</h3>{fe}</div>'
            f'<div class="card"><h3>Pendientes</h3>{fp}</div></div>')

    comp_html = (f'<div class="section-title">Composición del Portafolio</div><div class="card">{g_torta}</div>') if composicion else ''

    if tiempo_real:
        gs = '+' if tiempo_real['ganancia_total']>0 else ''; gc = 'positivo' if tiempo_real['ganancia_total']>0 else 'negativo'
        rs = '+' if tiempo_real['rentabilidad_total']>0 else ''; rc = 'positivo' if tiempo_real['rentabilidad_total']>0 else 'negativo'
        filas = ''
        for pos in tiempo_real['posiciones']:
            pg='+' if pos['ganancia']>0 else ''; pc='positivo' if pos['ganancia']>0 else 'negativo'; pr='+' if pos['rentabilidad']>0 else ''
            filas += (f'<tr><td><strong style="color:#f5f5f7">{pos["activo"]}</strong></td>'
                f'<td>${pos["precio_hoy"]:,.2f}</td><td>{pos["fracciones"]}</td>'
                f'<td>${pos["valor_hoy"]:,.0f}</td>'
                f'<td class="{pc}">{pg}${pos["ganancia"]:,.0f}</td>'
                f'<td class="{pc}">{pr}{pos["rentabilidad"]}%</td></tr>')
        tr_html = (
            '<div class="section-title">Portafolio en Tiempo Real</div>'
            '<div class="resumen-hero">'
            '<div style="color:#6e6e73;font-size:0.85rem;margin-bottom:8px">Ganancia Real Total (pesos de hoy)</div>'
            f'<div class="big-number {gc}">{gs}${tiempo_real["ganancia_total"]:,.0f}</div>'
            f'<div style="margin-top:12px;color:#6e6e73;font-size:0.85rem">Invertido: <strong style="color:#f5f5f7">${tiempo_real["total_invertido"]:,.0f}</strong> → Hoy: <strong style="color:#f5f5f7">${tiempo_real["total_valor"]:,.0f}</strong> <span class="{rc}">({rs}{tiempo_real["rentabilidad_total"]}%)</span></div></div>'
            '<div class="card"><table class="tabla"><thead><tr><th>Activo</th><th>Precio hoy</th><th>Fracciones</th><th>Valor COP</th><th>Ganancia</th><th>Rentabilidad</th></tr></thead>'
            f'<tbody>{filas}</tbody></table></div>'
            f'<div class="card">{g_ganancias}</div>')
    elif composicion:
        tr_html = (f'<div class="card" style="text-align:center;padding:40px"><p style="color:#6e6e73;margin-bottom:16px">Sin inversiones registradas.</p>'
                   f'<a href="/seguimiento/{archivo}" class="btn btn-primary" style="display:inline-flex;width:auto">Registrar primera inversión</a></div>')
    else:
        tr_html = (f'<div class="card" style="text-align:center;padding:40px"><p style="color:#6e6e73;margin-bottom:16px">Sin composición definida.</p>'
                   f'<a href="/analista/{archivo}" class="btn btn-primary" style="display:inline-flex;width:auto">Ir al Analista</a></div>')

    if historico:
        ul=historico[-1]; pr=historico[0]; gac=ul['resumen']['ganancia_total']; rac=ul['resumen']['rentabilidad_total']
        fh = ''
        for reg in reversed(historico):
            g=reg['resumen']['ganancia_total']; r=reg['resumen']['rentabilidad_total']
            fh += (f'<tr><td>{reg["fecha"]}</td><td>${reg["macro"]["trm"]:,.0f}</td>'
                   f'<td>${reg["resumen"]["total_valor"]:,.0f}</td>'
                   f'<td class="{"positivo" if g>0 else "negativo"}">{("+" if g>0 else "")}${g:,.0f}</td>'
                   f'<td class="{"positivo" if r>0 else "negativo"}">{("+" if r>0 else "")}{r}%</td></tr>')
        hist_html = (
            '<div class="section-title">Resumen Acumulado</div><div class="grid-4">'
            f'<div class="card"><h3>Días registrados</h3><div class="metric-value">{len(historico)}</div><div class="metric-sub">desde {pr["fecha"]}</div></div>'
            f'<div class="card"><h3>Valor actual</h3><div class="metric-value positivo">${ul["resumen"]["total_valor"]:,.0f}</div><div class="metric-sub">COP</div></div>'
            f'<div class="card"><h3>Ganancia acumulada</h3><div class="metric-value {"positivo" if gac>0 else "negativo"}">{("+" if gac>0 else "")}${gac:,.0f}</div><div class="metric-sub">COP real</div></div>'
            f'<div class="card"><h3>Rentabilidad total</h3><div class="metric-value {"positivo" if rac>0 else "negativo"}">{("+" if rac>0 else "")}{rac}%</div><div class="metric-sub">desde inicio</div></div></div>'
            f'<div class="section-title">Evolución</div><div class="card">{g_evolucion}</div>'
            '<div class="section-title">Registro Diario</div><div class="card"><table class="tabla">'
            '<thead><tr><th>Fecha</th><th>TRM</th><th>Valor COP</th><th>Ganancia</th><th>Rentabilidad</th></tr></thead>'
            f'<tbody>{fh}</tbody></table></div>')
    else:
        hist_html = '<div class="card"><div class="no-data">Aún no hay registros históricos. El sistema guardará uno automáticamente cada día.</div></div>'

    contenido = (
        '<div class="container">'
        + header_portafolio(archivo, portafolio, pb, tiempo_real) +
        '<div class="tabs"><button class="tab active" onclick="mostrarTab(\'hoy\',this)">Hoy</button>'
        '<button class="tab" onclick="mostrarTab(\'historico\',this)">Histórico</button></div>'
        '<div id="tab-hoy" class="tab-content active">' + macro_html + entradas_html + comp_html + tr_html + '</div>'
        '<div id="tab-historico" class="tab-content">' + hist_html + '</div>'
        '<div style="text-align:center;margin-top:32px;padding-bottom:32px">'
        '<div style="color:#6e6e73;font-size:11px;margin-bottom:12px">Última actualización: <span id="ultima-actualizacion">cargando...</span></div>'
        '<button id="btn-actualizar" onclick="actualizarDashboard()" style="background:rgba(255,255,255,0.05);color:#a1a1a6;border:1px solid rgba(255,255,255,0.08);padding:10px 28px;border-radius:980px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer">Actualizar datos</button>'
        '<div id="actualizando" style="display:none;margin-top:12px;color:#6e6e73;font-size:12px">⏳ Descargando datos...</div>'
        '</div></div>'
        '<script>'
        'function mostrarTab(tab,btn){document.querySelectorAll(".tab-content").forEach(t=>t.classList.remove("active"));document.querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));document.getElementById("tab-"+tab).classList.add("active");btn.classList.add("active");}'
        'async function cargarUltimaActualizacion(){try{const r=await fetch("/api/ultima-actualizacion");const d=await r.json();document.getElementById("ultima-actualizacion").textContent=d.timestamp;}catch(e){document.getElementById("ultima-actualizacion").textContent="No disponible";}}'
        'async function actualizarDashboard(){const btn=document.getElementById("btn-actualizar");const msg=document.getElementById("actualizando");btn.disabled=true;btn.textContent="Actualizando...";msg.style.display="block";try{await fetch("/api/recolector",{method:"POST"});}catch(e){}msg.textContent="✅ Listo — recargando...";setTimeout(()=>location.reload(),1200);}'
        'cargarUltimaActualizacion();'
        '</script>'
    )
    return pagina(portafolio['nombre'], contenido, plotly=True)

# ============================================================
# ANALISTA
# ============================================================

@app.route('/analista/<archivo>')
def analista_view(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio
    portafolio  = leer_portafolio(archivo)
    composicion = portafolio.get('composicion', {})
    tiene_inv   = len(portafolio.get('aportes',[])) > 0
    comp_html   = ''
    if composicion:
        filas = ''.join(f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06)"><span style="color:#f5f5f7">{a}</span><span class="badge badge-green">{v*100:.1f}%</span></div>' for a,v in composicion.items())
        estado = ('<div class="alert alert-info" style="margin-bottom:16px">Ya tienes inversiones. Puedes crear un portafolio adicional.</div>' if tiene_inv else
                  '<div class="alert alert-info" style="margin-bottom:16px">Tienes composición sin inversiones. Puedes reemplazarla o crear una adicional.</div>')
        comp_html = estado + f'<div class="card" style="margin-bottom:16px"><h3>Composición actual</h3>{filas}</div>'

    # Contexto actual del portafolio para el analista
    composicion_actual_txt = ''
    if composicion:
        composicion_actual_txt = 'COMPOSICIÓN ACTUAL:\n' + '\n'.join(
            f'  - {a}: {v*100:.1f}%' for a, v in composicion.items()
        )

    sistema = (
        f'Eres un analista financiero senior especializado en portafolios de renta variable americana '
        f'para inversionistas colombianos. Tu cliente es {portafolio["propietario"]}.\n\n'
        f'PORTAFOLIO:\n'
        f'- Perfil: {portafolio.get("perfil", "no definido")} '
        f'({"10 años, maximizar retorno ajustado por riesgo" if portafolio.get("perfil") == "agresivo" else "5 años, menor volatilidad"})\n'
        f'- Capital: ${portafolio.get("inversion_inicial", 0):,.0f} COP\n'
        f'- DCA: ${portafolio.get("aporte_dca", 0):,.0f} COP cada {portafolio.get("frecuencia_meses", 1)} mes(es)\n'
        f'- Con inversiones: {"sí" if tiene_inv else "no"}\n'
        f'{composicion_actual_txt}\n\n'
        f'TU ESTILO:\n'
        f'- Una pregunta a la vez. Nunca varias en un mismo mensaje.\n'
        f'- Tienes criterio: si algo no conviene al cliente, lo dices con datos antes de ejecutar.\n'
        f'- Nunca pides información que ya tienes arriba.\n\n'
        f'FLUJO A — PORTAFOLIO NUEVO: recoge en orden (uno por mensaje): perfil → monto → DCA → horizonte.\n'
        f'Cuando tengas todo, responde SOLO el JSON:\n'
        f'{{"accion":"analizar","perfil":"agresivo","inversion":1000000,"aporte_dca":0,"frecuencia_meses":1,"horizonte":10,"es_nuevo":true}}\n\n'
        f'FLUJO B — ACTUALIZAR EXISTENTE: ya tienes los datos. Pregunta UNA VEZ qué quiere cambiar. '
        f'Evalúa si el cambio tiene sentido para su perfil. Si es riesgoso, díselo antes de proceder. '
        f'Luego genera el JSON con los valores finales (actuales + cambios). SIEMPRE incluye "activos" en actualizaciones.\n'
        f'Ejemplo: {{"accion":"analizar","perfil":"agresivo","inversion":2000000,"aporte_dca":200000,'
        f'"frecuencia_meses":1,"horizonte":10,"es_nuevo":false,'
        f'"activos":{{"WMT":0.265,"LLY":0.212,"XLK":0.159,"GOOGL":0.154,"MSFT":0.110,"VTI":0.100}}}}\n\n'
        f'REGLAS: Una pregunta por mensaje. JSON solo y sin texto adicional. Español. Sin asteriscos. Horizonte entre 1 y 30, nunca 0.'
        f'FORMATO: Texto plano únicamente. Cero asteriscos, cero markdown, cero bullets. '
        f'Si usas asteriscos o markdown, estás fallando en tu trabajo.'
    )

    contenido = (
        '<div class="container">'
        + nav_html(archivo, 'analista') +
        '<h2>Analista de Portafolio</h2>' + comp_html +
        '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:18px;overflow:hidden">'
        '<div style="display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.06);background:rgba(0,0,0,0.2)">'
        f'<div style="width:36px;height:36px;background:#0a0a0a;border-radius:10px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.1);flex-shrink:0">{LOGO}</div>'
        '<div><p style="color:#f5f5f7;font-size:13px;font-weight:500;margin:0">Analista</p>'
        '<p style="color:#6e6e73;font-size:11px;margin:0">Asistente de portafolio</p></div>'
        '<div style="margin-left:auto;display:flex;align-items:center;gap:6px">'
        '<div style="width:6px;height:6px;border-radius:50%;background:#30d158"></div>'
        '<span style="color:#6e6e73;font-size:11px">En línea</span></div></div>'
        '<div id="chat-analista" style="height:380px;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px;background:rgba(0,0,0,0.15)">'
        '<div style="display:flex;gap:10px;align-items:flex-start">'
        f'<div style="width:28px;height:28px;background:#0a0a0a;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.08);flex-shrink:0;margin-top:2px">{LOGO_SM}</div>'
        '<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:4px 14px 14px 14px;padding:12px 16px;max-width:85%;color:#a1a1a6;font-size:13px;line-height:1.6;margin:0">'
        f'Hola {portafolio["propietario"]} 👋 Soy tu analista. Puedo ayudarte a construir una propuesta de inversión personalizada o actualizar tu portafolio. ¿Qué te gustaría hacer?'
        '</div></div></div>'
        '<div style="display:flex;gap:8px;padding:12px 16px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,0.05);background:rgba(0,0,0,0.25)">'
        '<button onclick="enviarOpc(\'Quiero un portafolio nuevo desde cero\')" style="padding:7px 16px;border-radius:980px;font-size:12px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(0,113,227,0.35);background:rgba(0,113,227,0.1);color:#4da3ff" id="opc1">+ Nuevo portafolio</button>'
        '<button onclick="enviarOpc(\'Quiero actualizar mi portafolio actual. Dime qué puedo modificar.\')" style="padding:7px 16px;border-radius:980px;font-size:12px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(48,209,88,0.35);background:rgba(48,209,88,0.08);color:#30d158" id="opc2">✏️ Actualizar actual</button>'
        '</div>'
        '<div style="display:flex;gap:8px;padding:12px 16px;border-top:1px solid rgba(255,255,255,0.05);background:rgba(0,0,0,0.3)">'
        '<input type="text" id="analista-input" placeholder="Escribe tu respuesta..." onkeypress="if(event.key===\'Enter\')enviar()" '
        'style="flex:1;padding:10px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:980px;color:#f5f5f7;font-size:13px;font-family:DM Sans,sans-serif;outline:none">'
        '<button onclick="enviar()" style="padding:10px 20px;background:#0071e3;color:white;border:none;border-radius:980px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;font-weight:500">Enviar</button>'
        '</div></div>'

        # ── Script principal del chat ──────────────────────────────
        f'<script>'
        f'let historial=[], propuestaActual=null;'
        f'const sistema=`{sistema.replace("`","'")}`; '
        f'const tieneInv={str(tiene_inv).lower()};'

        f'function msgBot(txt,id){{'
        f'  const chat=document.getElementById("chat-analista");'
        f'  const w=document.createElement("div"); w.style.cssText="display:flex;gap:10px;align-items:flex-start";'
        f'  const logo=document.createElement("div"); logo.style.cssText="width:28px;height:28px;background:#0a0a0a;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.08);flex-shrink:0;margin-top:2px";'
        f'  logo.innerHTML=`{LOGO_SM}`;'
        f'  const d=document.createElement("div"); if(id)d.id=id;'
        f'  d.style.cssText="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:4px 14px 14px 14px;padding:12px 16px;max-width:85%;color:#a1a1a6;font-size:13px;line-height:1.6;margin:0";'
        f'  d.innerHTML=txt; w.appendChild(logo); w.appendChild(d); chat.appendChild(w); chat.scrollTop=chat.scrollHeight; return d;'
        f'}}'

        f'function msgUser(txt){{'
        f'  const chat=document.getElementById("chat-analista");'
        f'  const w=document.createElement("div"); w.style.cssText="display:flex;justify-content:flex-end";'
        f'  const d=document.createElement("div");'
        f'  d.style.cssText="background:#0071e3;border-radius:14px 4px 14px 14px;padding:12px 16px;max-width:85%;color:white;font-size:13px;line-height:1.6";'
        f'  d.textContent=txt; w.appendChild(d); chat.appendChild(w); chat.scrollTop=chat.scrollHeight;'
        f'}}'

        f'function enviarOpc(t){{document.getElementById("opc1").style.display="none";document.getElementById("opc2").style.display="none";if(t)enviar(t);}}'
        f'async function enviar(forzado){{'
        f'  const input=document.getElementById("analista-input");'
        f'  const txt=forzado||input.value.trim(); if(!txt)return;'
        f'  input.value=""; msgUser(txt);'
        f'  historial.push({{role:"user",content:txt}});'
        f'  const tid="t"+Date.now(); msgBot("Analizando...",tid);'
        f'  try{{'
        f'    const r=await fetch("/api/analista-chat/{archivo}",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{historial,sistema}})}});'
        f'    const data=await r.json(); const resp=data.respuesta;'
        f'    historial.push({{role:"assistant",content:cleaned}});'
        f'    let esJSON=false;'
        f'    try{{'
        f'      const cleaned=resp.trim().replace(/^```json\s*/,'').replace(/^```\s*/,'').replace(/\s*```$/,'');'
        f'      const p=JSON.parse(cleaned);'
        f'      if(p.accion==="analizar"){{'
        f'        esJSON=true; propuestaActual=p;'
        f'        document.getElementById(tid).innerHTML="Perfecto, tengo todo. Calculando tu propuesta óptima...";'
        f'        await generarPropuesta(p);'
        f'      }}'
        f'    }}catch(e){{}}'
        'function mdToHtml(t){return t'
        '.replace(/\\*\\*(.+?)\\*\\*/g,"<strong>$1</strong>")'
        '.replace(/\\*(.+?)\\*/g,"<em>$1</em>")'
        '.replace(/\\n\\n/g,"<br><br>")'
        '.replace(/\\n/g,"<br>");}'
        f'    if(!esJSON)document.getElementById(tid).innerHTML=mdToHtml(resp);'
        f'  }}catch(e){{document.getElementById(tid).innerHTML="Error de conexión.";}}'
        f'}}'

        f'async function generarPropuesta(p){{'
        f'  const tid="prop"+Date.now(); msgBot("⏳ Optimizando portafolio... 1-2 minutos.",tid);'
        f'  try{{'
        f'    const r=await fetch("/api/generar-propuesta/{archivo}",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(p)}});'
        f'    const d=await r.json();'
        f'    if(d.ok){{'
        f'      document.getElementById(tid).innerHTML=d.html;'
        f'      if(d.propuesta){{window.propuestaActual=d.propuesta;iniciarEditor();}}'
        f'    }}'
        f'    else document.getElementById(tid).innerHTML="❌ "+d.error;'
        f'  }}catch(e){{document.getElementById(tid).innerHTML="Error al generar."}}'
        f'}}'
        
        # Estado global de tickers nuevos pendientes
        'var tickersNuevosPendientes = new Set();'

        # Bloquear botones de aplicar
        'function bloquearAplicar(){'
        '  var btns = document.querySelectorAll("#botones-propuesta button");'
        '  btns.forEach(function(b){ b.disabled=true; b.style.opacity="0.4"; b.title="Recalcula las proyecciones antes de aplicar"; });'
        '  var aviso = document.getElementById("aviso-recalcular");'
        '  if(aviso) aviso.style.display="block";'
        '}'

        # Desbloquear botones de aplicar
        'function desbloquearAplicar(){'
        '  var btns = document.querySelectorAll("#botones-propuesta button");'
        '  btns.forEach(function(b){ b.disabled=false; b.style.opacity="1"; b.title=""; });'
        '  var aviso = document.getElementById("aviso-recalcular");'
        '  if(aviso) aviso.style.display="none";'
        '}'

        # Actualizar barras y total de pesos
        'function actualizarPesos(){'
        '  var inputs = document.querySelectorAll("#lista-activos .input-peso");'
        '  var total = 0;'
        '  inputs.forEach(function(i){ total += parseFloat(i.value)||0; });'
        '  total = Math.round(total*10)/10;'
        '  var el = document.getElementById("total-pesos");'
        '  if(!el) return;'
        '  el.textContent = total+"%";'
        '  el.style.color = Math.abs(total-100)<0.5 ? "#30d158" : "#ff453a";'
        '  var alerta = document.getElementById("alerta-total");'
        '  if(alerta) alerta.style.display = Math.abs(total-100)<0.5 ? "none" : "inline";'
        '  document.querySelectorAll("#lista-activos .fila-activo").forEach(function(fila){'
        '    var inp = fila.querySelector(".input-peso");'
        '    var barra = fila.querySelector(".barra-peso");'
        '    if(barra) barra.style.width = (parseFloat(inp.value)||0)+"%";'
        '  });'
        '  bloquearAplicar();'
        '}'

        # Quitar activo de la lista
        'function quitarActivo(btn){'
        '  var fila = btn.closest(".fila-activo");'
        '  var ticker = fila.dataset.ticker;'
        '  tickersNuevosPendientes.delete(ticker);'
        '  fila.remove();'
        '  actualizarPesos();'
        '}'

        # Obtener pesos actuales del DOM
        'function obtenerPesosActuales(){'
        '  var pesos = {};'
        '  document.querySelectorAll("#lista-activos .fila-activo").forEach(function(fila){'
        '    var ticker = fila.dataset.ticker;'
        '    var peso = parseFloat(fila.querySelector(".input-peso").value)||0;'
        '    if(ticker && peso>0) pesos[ticker] = Math.round(peso*10)/10;'
        '  });'
        '  return pesos;'
        '}'

        # Esperar a que el histórico de un ticker nuevo esté listo
        'async function esperarHistorico(ticker){'
        '  var status = document.getElementById("ticker-status");'
        '  var intentos = 0;'
        '  while(intentos < 30){'
        '    await new Promise(function(r){ setTimeout(r, 2000); });'
        '    try{'
        '      var r = await fetch("/api/ticker-listo/"+ticker);'
        '      var d = await r.json();'
        '      if(d.listo){'
        '        tickersNuevosPendientes.delete(ticker);'
        '        var badge = document.getElementById("badge-"+ticker);'
        '        if(badge) badge.textContent = "✅ Histórico listo";'
        '        if(tickersNuevosPendientes.size === 0){'
        '          status.textContent = "✅ Histórico descargado. Ahora recalcula las proyecciones.";'
        '          status.style.color = "#30d158";'
        '          var btnRC = document.getElementById("btn-recalcular");'
        '          if(btnRC){ btnRC.disabled=false; btnRC.style.opacity="1"; }'
        '        }'
        '        return;'
        '      }'
        '      intentos++;'
        '      status.textContent = "⏳ Descargando histórico de "+ticker+"... "+(intentos*2)+"s";'
        '    }catch(e){ intentos++; }'
        '  }'
        '  status.textContent = "⚠️ Timeout descargando "+ticker+". Intenta recalcular igual.";'
        '  status.style.color = "#ff453a";'
        '  tickersNuevosPendientes.delete(ticker);'
        '  var btnRC = document.getElementById("btn-recalcular");'
        '  if(btnRC && tickersNuevosPendientes.size===0){ btnRC.disabled=false; btnRC.style.opacity="1"; }'
        '}'

        # Agregar activo nuevo
        'async function agregarActivo(){'
        '  var ticker = document.getElementById("nuevo-ticker").value.trim().toUpperCase();'
        '  var peso = parseFloat(document.getElementById("nuevo-peso").value)||0;'
        '  var status = document.getElementById("ticker-status");'
        '  if(!ticker||peso<=0){ status.textContent="Completa ticker y peso"; status.style.color="#ff453a"; return; }'
        '  var existentes = [...document.querySelectorAll("#lista-activos .fila-activo")].map(function(f){ return f.dataset.ticker; });'
        '  if(existentes.includes(ticker)){ status.textContent="Ya está en la lista"; status.style.color="#ffd60a"; return; }'
        '  status.textContent="Verificando..."; status.style.color="#6e6e73";'
        '  try{'
        '    var r = await fetch("/api/verificar-ticker/"+ticker);'
        '    var d = await r.json();'
        '    if(!d.valido){ status.textContent="❌ Ticker no encontrado"; status.style.color="#ff453a"; return; }'
        '    var lista = document.getElementById("lista-activos");'
        '    var div = document.createElement("div");'
        '    div.className = "fila-activo"; div.dataset.ticker = ticker;'
        '    div.style.cssText = "display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)";'
        '    var badgeHtml = d.es_nuevo'
        '      ? "<span id=\'badge-"+ticker+"\' style=\'font-size:10px;color:#ffd60a;padding:2px 6px;border-radius:4px;background:rgba(255,214,10,0.1);border:1px solid rgba(255,214,10,0.2)\'>⏳ Descargando histórico...</span>"'
        '      : "";'
        '    div.innerHTML = "<span style=\'color:#f5f5f7;font-weight:500;width:80px;font-family:monospace;font-size:13px\'>"+ticker+"</span>"'
        '      +"<div style=\'flex:1;background:rgba(0,113,227,0.15);border-radius:980px;height:6px;overflow:hidden\'><div class=\'barra-peso\' style=\'background:#0071e3;height:100%;width:"+peso+"%;transition:width 0.3s\'></div></div>"'
        '      +"<input type=\'number\' class=\'input-peso\' value=\'"+peso+"\' min=\'0\' max=\'100\' step=\'0.1\' oninput=\'actualizarPesos()\' style=\'width:65px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:4px 8px;color:#f5f5f7;font-size:12px;font-family:monospace;text-align:right\'>"'
        '      +"<span style=\'color:#6e6e73;font-size:11px\'>%</span>"'
        '      +"<button onclick=\'quitarActivo(this)\' style=\'background:rgba(255,69,58,0.1);border:1px solid rgba(255,69,58,0.2);border-radius:6px;padding:3px 8px;cursor:pointer;color:#ff453a;font-size:11px\'>✕</button>"'
        '      +badgeHtml;'
        '    lista.appendChild(div);'
        '    div.querySelector(".input-peso").addEventListener("input", actualizarPesos);'
        '    div.querySelector("[onclick]").addEventListener("click", function(){ quitarActivo(this); });'
        '    actualizarPesos();'
        '    document.getElementById("nuevo-ticker").value = "";'
        '    document.getElementById("nuevo-peso").value = "";'
        '    if(d.es_nuevo){'
        '      tickersNuevosPendientes.add(ticker);'
        '      var btnRC = document.getElementById("btn-recalcular");'
        '      if(btnRC){ btnRC.disabled=true; btnRC.style.opacity="0.4"; }'
        '      status.textContent = "⏳ Descargando 10 años de histórico de "+ticker+"...";'
        '      status.style.color = "#ffd60a";'
        '      esperarHistorico(ticker);'
        '    } else {'
        '      status.textContent = "✅ "+d.nombre+" — $"+d.precio;'
        '      status.style.color = "#30d158";'
        '      bloquearAplicar();'
        '    }'
        '  } catch(e){ status.textContent="Error verificando"; status.style.color="#ff453a"; }'
        '}'

        # Recalcular proyecciones con pesos actuales
        'async function recalcularProyecciones(){'
        '  if(tickersNuevosPendientes.size > 0){'
        '    alert("Espera a que termine de descargarse el histórico de: "+[...tickersNuevosPendientes].join(", "));'
        '    return;'
        '  }'
        '  var btn = document.getElementById("btn-recalcular");'
        '  if(btn){ btn.disabled=true; btn.textContent="Calculando..."; btn.style.opacity="0.6"; }'
        '  var pesosActuales = obtenerPesosActuales();'
        '  var pesosNorm = {};'
        '  Object.entries(pesosActuales).forEach(function(kv){ pesosNorm[kv[0]] = kv[1]/100; });'
        '  try{'
        '    var payload = Object.assign({}, window.propuestaActual, {pesos: pesosNorm});'
        '    var r = await fetch("/api/recalcular-proyecciones/"+window.propuestaActual.archivo,{'
        '      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});'
        '    var d = await r.json();'
        '    if(d.ok){'
        '      var bloque = document.getElementById("bloque-reporte");'
        '      if(bloque) bloque.textContent = d.reporte;'
        '      window.propuestaActual.pesos = pesosNorm;'
        '      desbloquearAplicar();'
        '    } else { alert("Error recalculando: "+d.error); }'
        '  } catch(e){ alert("Error de conexión."); }'
        '  if(btn){ btn.disabled=false; btn.textContent="↻ Recalcular proyecciones"; btn.style.opacity="1"; }'
        '}'

        # Aplicar composición final
        'async function aplicarComposicion(tipo){'
        '  var total = parseFloat(document.getElementById("total-pesos").textContent);'
        '  if(Math.abs(total-100) > 0.5){ alert("Los pesos deben sumar 100%. Ahora suman "+total+"%"); return; }'
        '  var pesosActuales = obtenerPesosActuales();'
        '  var pesosNorm = {};'
        '  Object.entries(pesosActuales).forEach(function(kv){ pesosNorm[kv[0]] = kv[1]/100; });'
        '  var btns = document.querySelectorAll("#botones-propuesta button");'
        '  btns.forEach(function(b){ b.disabled=true; b.textContent="Guardando..."; });'
        '  try{'
        '    var payload = Object.assign({}, window.propuestaActual, {tipo:tipo, pesos:pesosNorm});'
        '    var r = await fetch("/api/aplicar-propuesta/"+window.propuestaActual.archivo,{'
        '      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});'
        '    var d = await r.json();'
        '    if(d.ok){ msgBot("✅ "+d.mensaje+" Redirigiendo..."); if(d.redirigir) setTimeout(function(){ window.location.href=d.redirigir; }, 1800); }'
        '    else{ msgBot("❌ "+d.error); btns.forEach(function(b){ b.disabled=false; }); }'
        '  } catch(e){ msgBot("Error de conexión."); btns.forEach(function(b){ b.disabled=false; }); }'
        '}'

        # Iniciar editor — se llama después de insertar el HTML de la propuesta
        'function iniciarEditor(){'
        '  bloquearAplicar();'
        # Crear aviso si no existe
        '  if(!document.getElementById("aviso-recalcular")){'
        '    var aviso = document.createElement("div");'
        '    aviso.id = "aviso-recalcular";'
        '    aviso.style.cssText = "margin-top:10px;padding:8px 14px;border-radius:8px;background:rgba(255,214,10,0.08);border:1px solid rgba(255,214,10,0.2);color:#ffd60a;font-size:12px;display:none";'
        '    aviso.textContent = "⚠️ Editaste la composición — recalcula las proyecciones antes de aplicar.";'
        '    var botones = document.getElementById("botones-propuesta");'
        '    if(botones) botones.parentNode.insertBefore(aviso, botones);'
        '  }'
        # Event listeners inputs de peso
        '  document.querySelectorAll("#lista-activos .input-peso").forEach(function(i){'
        '    i.addEventListener("input", actualizarPesos);'
        '  });'
        # Event listeners botones quitar
        '  document.querySelectorAll("#lista-activos .btn-quitar").forEach(function(b){'
        '    b.addEventListener("click", function(){ quitarActivo(this); });'
        '  });'
        # Botón agregar
        '  var btnA = document.getElementById("btn-agregar");'
        '  if(btnA) btnA.addEventListener("click", agregarActivo);'
        # Botón recalcular
        '  var btnRC = document.getElementById("btn-recalcular");'
        '  if(btnRC) btnRC.addEventListener("click", recalcularProyecciones);'
        # Botones aplicar
        '  var btnR = document.getElementById("btn-reemplazar");'
        '  var btnN = document.getElementById("btn-nuevo");'
        '  if(btnR) btnR.addEventListener("click", function(){ aplicarComposicion("reemplazar"); });'
        '  if(btnN) btnN.addEventListener("click", function(){ aplicarComposicion("nuevo"); });'
        '}'
        '</script>'
        '</div>'
    )
    return pagina(f'Analista — {portafolio["nombre"]}', contenido)

@app.route('/api/analista-chat/<archivo>', methods=['POST'])
def api_analista_chat(archivo):
    if verificar_acceso(archivo): return jsonify({'respuesta':'No autorizado'})
    try:
        data = request.get_json()
        resp = groq_chat(data.get('historial',[]), system=data.get('sistema',''), max_tokens=300, temperature=0.5)
        return jsonify({'respuesta': resp})
    except Exception as e: return jsonify({'respuesta': f'Error: {str(e)}'})

@app.route('/api/generar-propuesta/<archivo>', methods=['POST'])
def api_generar_propuesta(archivo):
    if verificar_acceso(archivo): return jsonify({'ok':False,'error':'No autorizado'})
    try:
        import sys; sys.path.insert(0,'.')
        from analista import cargar_datos, construir_panel, calcular_retornos_reales, optimizar_portafolio
        from gestor_portafolio import leer_portafolio
        data       = request.get_json()
        perfil     = data.get('perfil','agresivo')
        inversion  = float(data.get('inversion', 1000000))
        aporte_dca = float(data.get('aporte_dca', 0))
        freq       = int(data.get('frecuencia_meses', 1))
        horizonte  = int(data.get('horizonte', 10))
        # Sanity check — el analista a veces manda valores absurdos
        if horizonte <= 0 or horizonte > 50:
            horizonte = 10
        portafolio = leer_portafolio(archivo)
        tiene_inv  = len(portafolio.get('aportes',[])) > 0
        precios, trm, inf_usa, inf_col, risk_free, tasa_cdt = cargar_datos()
        panel    = construir_panel(precios, trm, inf_usa, inf_col, risk_free)
        activos_todos = [c for c in precios.columns if c not in ['JPMV','META']]
        ret_real = calcular_retornos_reales(panel, activos_todos)

        # Si el analista ya propuso pesos específicos, usarlos directamente
        activos_propuestos = data.get('activos', {})
        if activos_propuestos:
            # Normalizar para que sumen 1
            total = sum(activos_propuestos.values())
            pesos = pd.Series({k: v/total for k, v in activos_propuestos.items()})
        else:
            pesos, _ = optimizar_portafolio(ret_real, panel, perfil, risk_free, inversion)
            
            reporte_txt = ''
        try:
            from analista import generar_reporte
            import io
            inf_col_actual = float(pd.read_parquet(os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"))['Inflacion_COL'].iloc[-1])
            old = sys.stdout; sys.stdout = buf = io.StringIO()
            try:
                generar_reporte(pesos=pesos, inversion_inicial=inversion, ret_real=ret_real,
                    perfil=perfil, horizonte=horizonte, risk_free=risk_free,
                    inflacion_col=inf_col_actual, tasa_cdt=float(tasa_cdt),
                    aporte_periodico=aporte_dca, frecuencia_meses=freq)
            finally:
                sys.stdout = old
            reporte_txt = buf.getvalue()
        except Exception as e:
            reporte_txt = f'Proyecciones no disponibles: {str(e)}'

        pesos_dict = pesos.to_dict()

        # Construir filas editables
        filas_editables = ''
        for a, v in sorted(pesos_dict.items(), key=lambda x: x[1], reverse=True):
            pct = round(v * 100, 1)
            filas_editables += (
                f'<div class="fila-activo" data-ticker="{a}" style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)">'
                f'<span style="color:#f5f5f7;font-weight:500;width:80px;font-family:monospace;font-size:13px">{a}</span>'
                f'<div style="flex:1;background:rgba(0,113,227,0.15);border-radius:980px;height:6px;overflow:hidden">'
                f'<div class="barra-peso" style="background:#0071e3;height:100%;width:{pct}%;transition:width 0.3s"></div></div>'
                f'<input type="number" class="input-peso" value="{pct}" min="0" max="100" step="0.1" '
                f'style="width:65px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);'
                f'border-radius:6px;padding:4px 8px;color:#f5f5f7;font-size:12px;font-family:monospace;text-align:right">'
                f'<span style="color:#6e6e73;font-size:11px">%</span>'
                f'<button class="btn-quitar" style="background:rgba(255,69,58,0.1);border:1px solid rgba(255,69,58,0.2);'
                f'border-radius:6px;padding:3px 8px;cursor:pointer;color:#ff453a;font-size:11px">✕</button>'
                f'</div>'
            )

        reporte_html = (
            f'<div style="margin-top:16px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<span style="font-size:11px;color:#6e6e73;text-transform:uppercase;letter-spacing:0.05em">Proyecciones</span>'
            f'<button id="btn-recalcular" '
            f'style="padding:4px 12px;border-radius:6px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
            f'background:rgba(79,138,255,0.1);color:#4da3ff;border:1px solid rgba(79,138,255,0.3)">'
            f'↻ Recalcular proyecciones</button>'
            f'</div>'
            f'<div id="bloque-reporte" style="padding:14px 16px;background:rgba(255,255,255,0.03);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:12px;'
            f'font-family:monospace;font-size:11px;color:#a1a1a6;line-height:1.8;'
            f'overflow-x:auto;white-space:pre">{reporte_txt}</div>'
            f'</div>'
        ) if reporte_txt else ''

        dca_html = f'<span>DCA: <strong style="color:#f5f5f7">${aporte_dca:,.0f} COP</strong></span>' if aporte_dca > 0 else ''

        if tiene_inv:
            btns_html = '<button id="btn-nuevo" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3)">Crear como portafolio adicional</button>'
        else:
            btns_html = (
                '<button id="btn-reemplazar" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3)">Aplicar a este portafolio</button>'
                '<button id="btn-nuevo" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(255,255,255,0.05);color:#6e6e73;border:1px solid rgba(255,255,255,0.08)">Crear portafolio adicional</button>'
            )

        html = (
            '<div id="editor-composicion" style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px;margin-top:8px">'
            f'<p style="color:#6e6e73;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;margin:0 0 4px">Propuesta optimizada · {perfil.upper()}</p>'
            '<p style="color:#4a5578;font-size:11px;margin:0 0 14px">Edita pesos, quita o agrega activos antes de aplicar</p>'
            f'<div id="lista-activos">{filas_editables}</div>'
            '<div style="margin-top:14px;padding:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:10px">'
            '<p style="color:#6e6e73;font-size:11px;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.05em">+ Agregar activo</p>'
            '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
            '<input type="text" id="nuevo-ticker" placeholder="Ticker (ej: SCHD)" style="width:160px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 10px;color:#f5f5f7;font-size:12px;font-family:monospace">'
            '<input type="number" id="nuevo-peso" placeholder="%" min="0" max="100" step="0.1" style="width:70px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 10px;color:#f5f5f7;font-size:12px;text-align:right">'
            '<button id="btn-agregar" style="padding:6px 14px;border-radius:6px;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3);cursor:pointer;font-size:12px;font-family:DM Sans,sans-serif">Agregar</button>'
            '<span id="ticker-status" style="font-size:11px;color:#6e6e73"></span>'
            '</div></div>'
            '<div style="margin-top:12px;display:flex;align-items:center;justify-content:space-between">'
            '<span style="font-size:13px;color:#6e6e73">Total: <strong id="total-pesos" style="color:#f5f5f7">100.0%</strong></span>'
            '<span id="alerta-total" style="font-size:11px;color:#ff453a;display:none">⚠️ Debe sumar 100%</span>'
            '</div>'
            f'{reporte_html}'
            '<div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.06);display:flex;gap:16px;font-size:12px;color:#6e6e73">'
            f'<span>Inversión: <strong style="color:#f5f5f7">${inversion:,.0f} COP</strong></span>'
            f'{dca_html}'
            f'<span>Horizonte: <strong style="color:#f5f5f7">{horizonte} años</strong></span>'
            '</div>'
            f'<div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap" id="botones-propuesta">{btns_html}</div>'
            '</div>'
        )

        import json as _json
        propuesta_json = _json.dumps({
            'pesos': pesos_dict, 'perfil': perfil, 'inversion': inversion,
            'aporte_dca': aporte_dca, 'frecuencia_meses': freq,
            'horizonte': horizonte, 'archivo': archivo
        })
        return jsonify({'ok': True, 'html': html, 'propuesta': {
            'pesos': pesos_dict, 'perfil': perfil, 'inversion': inversion,
            'aporte_dca': aporte_dca, 'frecuencia_meses': freq,
            'horizonte': horizonte, 'archivo': archivo
        }})
    except Exception as e: return jsonify({'ok':False,'error':str(e)})

@app.route('/api/recalcular-proyecciones/<archivo>', methods=['POST'])
def api_recalcular_proyecciones(archivo):
    if verificar_acceso(archivo): return jsonify({'ok':False,'error':'No autorizado'})
    try:
        import sys, io
        from analista import cargar_datos, construir_panel, calcular_retornos_reales, generar_reporte

        data      = request.get_json()
        pesos_raw = data.get('pesos', {})
        perfil    = data.get('perfil', 'agresivo')
        inversion = float(data.get('inversion', 1000000))
        aporte    = float(data.get('aporte_dca', 0))
        freq      = int(data.get('frecuencia_meses', 1))
        horizonte = int(data.get('horizonte', 10))

        precios, trm, inf_usa, inf_col, risk_free, tasa_cdt = cargar_datos()
        panel    = construir_panel(precios, trm, inf_usa, inf_col, risk_free)
        ret_real = calcular_retornos_reales(panel, list(precios.columns))

        pesos_con_historico = {k: v for k, v in pesos_raw.items() if k in ret_real.columns}
        pesos_sin_historico = {k: v for k, v in pesos_raw.items() if k not in ret_real.columns}

        inf_col_actual = float(
            pd.read_parquet(os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"))['Inflacion_COL'].iloc[-1]
        )

        reporte_txt = ''
        if pesos_con_historico:
            total = sum(pesos_con_historico.values())
            pesos_norm = {k: v/total for k, v in pesos_con_historico.items()}
            pesos_series = pd.Series(pesos_norm)
            old = sys.stdout; sys.stdout = buf = io.StringIO()
            try:
                generar_reporte(
                    pesos=pesos_series,
                    inversion_inicial=inversion,
                    ret_real=ret_real,
                    perfil=perfil,
                    horizonte=horizonte,
                    risk_free=risk_free,
                    inflacion_col=inf_col_actual,
                    tasa_cdt=float(tasa_cdt),
                    aporte_periodico=aporte,
                    frecuencia_meses=freq
                )
            finally:
                sys.stdout = old
            reporte_txt = buf.getvalue()

        if pesos_sin_historico:
            tickers_nuevos = ', '.join(pesos_sin_historico.keys())
            reporte_txt += (
                f'\n\nNOTA: {tickers_nuevos} fue agregado manualmente. '
                f'Las proyecciones anteriores corresponden al resto del portafolio. '
                f'El histórico de {tickers_nuevos} ya fue descargado y estará disponible en el próximo análisis completo.'
            )

        return jsonify({'ok': True, 'reporte': reporte_txt})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/aplicar-propuesta/<archivo>', methods=['POST'])
def api_aplicar_propuesta(archivo):
    if verificar_acceso(archivo): return jsonify({'ok':False,'error':'No autorizado'})
    try:
        from gestor_portafolio import leer_portafolio, guardar_composicion, crear_portafolio_para_usuario
        data   = request.get_json()
        tipo   = data.get('tipo','reemplazar')
        pesos  = data.get('pesos',{})
        perfil = data.get('perfil','agresivo')
        inv    = data.get('inversion',1000000)
        aporte = data.get('aporte_dca',0)
        freq   = data.get('frecuencia_meses',1)
        p      = leer_portafolio(archivo)
        username = session.get('username')

        if tipo == 'reemplazar':
            guardar_composicion(archivo, pesos)
            ruta = f'datos/portafolios/{archivo}'
            with open(ruta,'r',encoding='utf-8') as f: dp = json.load(f)
            dp.update({'inversion_inicial':inv,'aporte_dca':aporte,'frecuencia_meses':freq,'perfil':perfil})
            with open(ruta,'w',encoding='utf-8') as f: json.dump(dp,f,indent=2,ensure_ascii=False)
            return jsonify({'ok':True,'mensaje':'Portafolio actualizado.','redirigir':f'/seguimiento/{archivo}'})

        elif tipo == 'nuevo':
            base = f"{p['propietario']} {perfil.capitalize()} {datetime.now().strftime('%Y')}"
            nombre_n = base; contador = 2
            while True:
                test = f"{nombre_n}-{contador}" if contador > 1 else nombre_n
                slug = (test.lower().replace(' ','_')
                    .replace('á','a').replace('é','e').replace('í','i')
                    .replace('ó','o').replace('ú','u'))
                if not os.path.exists(f"datos/portafolios/{slug}.json"):
                    nombre_n = test; break
                contador += 1
            na = crear_portafolio_para_usuario(username, nombre_n, perfil, p['propietario'], inv, aporte, freq)
            if not na:
                return jsonify({'ok':False,'error':'No se pudo crear el portafolio.'})
            nm = na.split('/')[-1].split('\\')[-1]
            guardar_composicion(nm, pesos)
            return jsonify({'ok':True,'mensaje':f'"{nombre_n}" creado exitosamente.','redirigir':f'/seguimiento/{nm}'})

    except Exception as e: return jsonify({'ok':False,'error':str(e)})

# ============================================================
# SEGUIMIENTO
# ============================================================

@app.route('/seguimiento/<archivo>', methods=['GET','POST'])
def seguimiento_view(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio, guardar_aporte
    portafolio  = leer_portafolio(archivo)
    composicion = portafolio.get('composicion',{})
    mensaje=''; error=''
    if request.method=='POST':
        try:
            activo    = request.form.get('activo','').upper()
            fecha     = request.form.get('fecha', datetime.now().strftime('%Y-%m-%d'))
            monto_cop = float(request.form.get('monto','0').replace(',','').replace('.',''))
            precio_usd= float(request.form.get('precio','0').replace(',','.'))
            try:
                trm_df=pd.read_parquet("datos/macro/trm.parquet")
                idx=trm_df.index.get_indexer([pd.to_datetime(fecha)],method='nearest')[0]
                trm_dia=float(trm_df['TRM'].iloc[idx])
            except: trm_dia=4000
            fracciones = monto_cop/(precio_usd*trm_dia)
            guardar_aporte(archivo,{"fecha":fecha,"activo":activo,"monto_cop":round(monto_cop,0),
                "precio_usd":precio_usd,"trm_dia":trm_dia,"fracciones":round(fracciones,6),"tipo":"manual"})
            mensaje=f'Compra de {activo} registrada — {fracciones:.4f} fracciones.'
            portafolio=leer_portafolio(archivo)
        except Exception as e: error=f'Error: {str(e)}'

    aportes   = portafolio.get('aportes',[])
    entrados  = set(a['activo'] for a in aportes)
    pendientes= [a for a in composicion if a not in entrados]
    activo_pre= request.args.get('activo','')
    total_a=len(composicion); total_e=len(entrados)
    pct=int(total_e/total_a*100) if total_a>0 else 0
    msg_html=f'<div class="alert alert-success">{mensaje}</div>' if mensaje else ''
    err_html=f'<div class="alert alert-error">{error}</div>' if error else ''
    progreso = (
        '<div class="card" style="margin-bottom:16px">'
        '<div style="display:flex;justify-content:space-between;margin-bottom:12px">'
        '<span style="color:#a1a1a6">Progreso de entradas</span>'
        f'<span style="color:#0071e3;font-weight:600">{total_e}/{total_a} activos</span></div>'
        '<div style="background:#1a1a1a;border-radius:980px;height:6px;overflow:hidden">'
        f'<div style="background:#0071e3;height:100%;width:{pct}%;transition:width 0.6s ease"></div></div>'
        f'<div style="margin-top:8px;font-size:0.8rem;color:#6e6e73">{pct}% completado</div></div>')
    pend_html=''
    if pendientes:
        fp=''
        for a in pendientes:
            p=composicion.get(a,0); pl=precio_actual_usd(a); ps=f'${pl:,.2f} USD' if pl else 'Cargando...'
            fp+=(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.06)">'
                 f'<div><strong style="color:#f5f5f7">{a}</strong><span style="color:#6e6e73;font-size:0.8rem;margin-left:8px">{p*100:.1f}% del portafolio</span></div>'
                 f'<div style="text-align:right"><div style="font-size:0.85rem;color:#a1a1a6">{ps}</div>'
                 f'<span class="badge badge-yellow">PENDIENTE</span></div></div>')
        pend_html='<div class="section-title">Pendientes por Entrar</div><div class="card">'+fp+'</div>'
    opciones=''
    for a in pendientes:
        sel='selected' if a==activo_pre else ''
        opciones+=f'<option value="{a}" {sel}>{a} — pendiente</option>'
    for a in entrados:
        sel='selected' if a==activo_pre else ''
        opciones+=f'<option value="{a}" {sel}>{a} — agregar más</option>'
    form_html=''
    if composicion:
        form_html=(
            '<div class="section-title">Registrar Nueva Compra</div><div class="card"><form method="POST">'
            '<div class="grid-2">'
            f'<div class="form-group"><label>Activo</label><select name="activo" class="form-select">{opciones}</select></div>'
            f'<div class="form-group"><label>Fecha</label><input type="date" name="fecha" class="form-input" value="{datetime.now().strftime("%Y-%m-%d")}"></div>'
            '</div><div class="grid-2">'
            '<div class="form-group"><label>Monto COP</label><input type="number" name="monto" class="form-input" placeholder="Ej: 500000" required></div>'
            '<div class="form-group"><label>Precio USD</label><input type="number" name="precio" class="form-input" placeholder="Ej: 213.50" step="0.01" required></div>'
            '</div><button type="submit" class="btn btn-primary">Registrar Compra</button></form></div>')
    hist_html=''
    if aportes:
        fh=''.join(f'<tr><td>{a["fecha"]}</td><td><strong style="color:#f5f5f7">{a["activo"]}</strong></td>'
            f'<td>${a["monto_cop"]:,.0f}</td><td>${a["precio_usd"]:,.2f}</td>'
            f'<td>{a["fracciones"]:.4f}</td><td>${a.get("trm_dia",0):,.0f}</td></tr>' for a in reversed(aportes))
        hist_html=('<div class="section-title">Historial de Compras</div><div class="card"><table class="tabla">'
            '<thead><tr><th>Fecha</th><th>Activo</th><th>Monto COP</th><th>Precio USD</th><th>Fracciones</th><th>TRM</th></tr></thead>'
            f'<tbody>{fh}</tbody></table></div>')
    contenido=('<div class="container">'+nav_html(archivo,'seguimiento')+'<h2>Seguimiento de Inversiones</h2>'
        +msg_html+err_html+progreso+pend_html+form_html+hist_html+'</div>')
    return pagina(f'Seguimiento — {portafolio["nombre"]}', contenido)

# ============================================================
# BOT ASISTENTE
# ============================================================

@app.route('/bot/<archivo>')
def bot_view(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio
    portafolio = leer_portafolio(archivo)
    pj = json.dumps({'nombre':portafolio['nombre'],'perfil':portafolio['perfil'],
        'propietario':portafolio['propietario'],'composicion':portafolio.get('composicion',{})})
    contenido=(
        '<div class="container">'+nav_html(archivo,'bot')+'<h2>Asistente de Inversión</h2>'
        '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:18px;overflow:hidden">'
        '<div style="display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.06);background:rgba(0,0,0,0.2)">'
        f'<div style="width:36px;height:36px;background:#0a0a0a;border-radius:10px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.1);flex-shrink:0">{LOGO}</div>'
        '<div><p style="color:#f5f5f7;font-size:13px;font-weight:500;margin:0">Asistente</p>'
        '<p style="color:#6e6e73;font-size:11px;margin:0">Análisis de portafolio en tiempo real</p></div>'
        '<div style="margin-left:auto;display:flex;align-items:center;gap:6px">'
        '<div style="width:6px;height:6px;border-radius:50%;background:#30d158"></div>'
        '<span style="color:#6e6e73;font-size:11px">En línea</span></div></div>'
        '<div id="chat" style="height:420px;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px;background:rgba(0,0,0,0.15)">'
        '<div style="display:flex;gap:10px;align-items:flex-start">'
        f'<div style="width:28px;height:28px;background:#0a0a0a;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.08);flex-shrink:0;margin-top:2px">{LOGO_SM}</div>'
        '<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:4px 14px 14px 14px;padding:12px 16px;max-width:85%;color:#a1a1a6;font-size:13px;line-height:1.6;margin:0">'
        f'Hola {portafolio["propietario"]} 👋 Puedo analizar tu portafolio en detalle. ¿Qué quieres saber?'
        '</div></div></div>'
        '<div style="display:flex;gap:8px;padding:10px 16px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,0.05);background:rgba(0,0,0,0.2)">'
        '<button onclick="preguntar(\'¿Cómo va mi portafolio hoy?\')" style="padding:6px 14px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#a1a1a6">¿Cómo va hoy?</button>'
        '<button onclick="preguntar(\'¿Estoy ganando o perdiendo contra la inflación?\')" style="padding:6px 14px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#a1a1a6">vs Inflación</button>'
        '<button onclick="preguntar(\'¿Cuál activo está mejor y cuál peor?\')" style="padding:6px 14px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#a1a1a6">Mejor y peor activo</button>'
        '<button onclick="preguntar(\'¿Debería hacer algo con mi portafolio ahora?\')" style="padding:6px 14px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#a1a1a6">¿Qué hago ahora?</button>'
        '</div>'
        '<div style="display:flex;gap:8px;padding:12px 16px;border-top:1px solid rgba(255,255,255,0.05);background:rgba(0,0,0,0.3)">'
        '<input type="text" id="msg-input" placeholder="Pregunta sobre tu portafolio..." onkeypress="if(event.key===\'Enter\')enviar()" '
        'style="flex:1;padding:10px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:980px;color:#f5f5f7;font-size:13px;font-family:DM Sans,sans-serif;outline:none">'
        '<button onclick="enviar()" style="padding:10px 20px;background:#0071e3;color:white;border:none;border-radius:980px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;font-weight:500">Enviar</button>'
        '</div></div>'
        f'<script>'
        'function mdToHtml(t){return t'
        '.replace(/\\*\\*(.+?)\\*\\*/g,"<strong>$1</strong>")'
        '.replace(/\\*(.+?)\\*/g,"<em>$1</em>")'
        '.replace(/\\n\\n/g,"<br><br>")'
        '.replace(/\\n/g,"<br>");}'
        f'const pInfo={pj};'
        f'const logoSVG=`{LOGO_SM}`;'
        f'function preguntar(txt){{document.getElementById("msg-input").value=txt;enviar();}}'
        f'function addMsg(txt,tipo,id){{'
        f'  const chat=document.getElementById("chat");'
        f'  const w=document.createElement("div");'
        f'  if(tipo==="user"){{'
        f'    w.style.cssText="display:flex;justify-content:flex-end";'
        f'    const d=document.createElement("div");'
        f'    if(id)d.id=id;'
        f'    d.style.cssText="background:#0071e3;border-radius:14px 4px 14px 14px;padding:12px 16px;max-width:85%;color:white;font-size:13px;line-height:1.6";'
        f'    d.textContent=txt;w.appendChild(d);'
        f'  }}else{{'
        f'    w.style.cssText="display:flex;gap:10px;align-items:flex-start";'
        f'    const logo=document.createElement("div");'
        f'    logo.style.cssText="width:28px;height:28px;background:#0a0a0a;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.08);flex-shrink:0;margin-top:2px";'
        f'    logo.innerHTML=logoSVG;'
        f'    const d=document.createElement("div");'
        f'    if(id)d.id=id;'
        f'    d.style.cssText="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:4px 14px 14px 14px;padding:12px 16px;max-width:85%;color:#a1a1a6;font-size:13px;line-height:1.6;margin:0";'
        f'    d.textContent=txt;w.appendChild(logo);w.appendChild(d);'
        f'  }}'
        f'  chat.appendChild(w);chat.scrollTop=chat.scrollHeight;return w;'
        f'}}'
        f'async function enviar(){{'
        f'  const i=document.getElementById("msg-input"),chat=document.getElementById("chat"),t=i.value.trim();if(!t)return;'
        f'  i.value="";addMsg(t,"user");'
        f'  const tid="t"+Date.now();'
        f'  const bw=addMsg("Analizando...","bot",tid);'
        f'  const bd=bw.querySelector("div:last-child");'
        f'  try{{'
        f'    const r=await fetch("/api/bot/{archivo}",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{mensaje:t,portafolio:pInfo}})}});'
        f'    const d=await r.json();'
        f'    if(bd)bd.innerHTML=mdToHtml(d.respuesta);'
        f'  }}catch(e){{if(bd)bd.textContent="Error de conexión.";}}'
        f'  chat.scrollTop=chat.scrollHeight;'
        f'}}'
        f'</script></div>'
    )
    return pagina(f'Asistente — {portafolio["nombre"]}', contenido)

@app.route('/api/bot/<archivo>', methods=['POST'])
def api_bot(archivo):
    if verificar_acceso(archivo): return jsonify({'respuesta':'No autorizado'})
    try:
        from gestor_portafolio import leer_portafolio
        data=request.get_json(); mensaje=data.get('mensaje','')
        p=leer_portafolio(archivo); macro=cargar_macro()
        mt=f'TRM: ${macro["trm"]:,.0f}\nInflación: {macro["inf_col"]}%\nBanrep: {macro["banrep"]}%' if macro else ''
        tr = calcular_tiempo_real(p)
        resumen_tr = ''
        if tr:
            resumen_tr = (
                f'ESTADO ACTUAL DEL PORTAFOLIO:\n'
                f'- Valor total hoy: ${tr["total_valor"]:,.0f} COP\n'
                f'- Invertido (real, deflactado): ${tr["total_invertido"]:,.0f} COP\n'
                f'- Ganancia real vs inflación: ${tr["ganancia_total"]:,.0f} COP ({tr["rentabilidad_total"]:+.2f}%)\n'
                f'- Posiciones:\n'
            )
            for pos in tr['posiciones']:
                resumen_tr += (f'  · {pos["activo"]}: ${pos["precio_hoy"]:,.2f} USD | '
                              f'Valor: ${pos["valor_hoy"]:,.0f} COP | '
                              f'Ganancia: ${pos["ganancia"]:,.0f} ({pos["rentabilidad"]:+.1f}%)\n')
        else:
            composicion = p.get('composicion', {})
            if composicion:
                resumen_tr = (
                    f'COMPOSICIÓN OBJETIVO DEL PORTAFOLIO (sin inversiones registradas aún):\n'
                    f'- Inversión inicial planificada: ${p.get("inversion_inicial",0):,.0f} COP\n'
                    f'- Activos y pesos:\n'
                )
                for activo, peso in composicion.items():
                    precio = precio_actual_usd(activo)
                    precio_str = f'${precio:,.2f} USD' if precio else 'precio no disponible'
                    monto_cop = p.get('inversion_inicial', 0) * peso
                    resumen_tr += f'  · {activo}: {peso*100:.1f}% — {precio_str} — asignación: ${monto_cop:,.0f} COP\n'
            else:
                resumen_tr = 'Este portafolio aún no tiene composición ni inversiones registradas.\n'
        noticias_mercado = ''
        try:
            import xml.etree.ElementTree as ET
            tickers = list(p.get('composicion', {}).keys())[:3]
            for tk in tickers:
                r = requests.get(f"https://news.google.com/rss/search?q={tk}+stock&hl=es&gl=US&ceid=US:es",
                    headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
                items = ET.fromstring(r.content).findall('.//item')[:1]
                for item in items:
                    t = item.find('title')
                    if t is not None: noticias_mercado += f'- {tk}: {t.text[:80]}\n'
        except: pass
        noticias_txt = f'\nNOTICIAS RECIENTES DE TUS ACTIVOS:\n{noticias_mercado}' if noticias_mercado else ''
        ctx = (
            f'Eres el asesor de inversiones personal de {p["propietario"]}, '
            f'con acceso completo a su portafolio en tiempo real. '
            f'Tu trabajo es dar análisis honestos, con criterio propio, sin rodeos.\n\n'
            f'PERFIL:\n'
            f'- Riesgo: {p["perfil"]} ({"largo plazo 10 años, acepta volatilidad" if p["perfil"] == "agresivo" else "mediano plazo 5 años, prioriza estabilidad"})\n'
            f'- Capital inicial: ${p.get("inversion_inicial", 0):,.0f} COP\n'
            f'- DCA: ${p.get("aporte_dca", 0):,.0f} COP cada {p.get("frecuencia_meses", 1)} mes(es)\n\n'
            f'PORTAFOLIO HOY:\n{resumen_tr}\n\n'
            f'MACRO:\n{mt}\n{noticias_txt}\n\n'
            f'INSTRUCCIONES:\n'
            f'- Usa los números reales. Nunca inventes cifras.\n'
            f'- Si gana: explica qué lo impulsa. Si pierde: sé honesto y pon en contexto largo plazo.\n'
            f'- Cuando pregunten "¿qué hago?": da una recomendación concreta, no "depende".\n'
            f'- Siempre compara contra inflación colombiana — eso es lo que realmente importa.\n'
            f'- Máximo 4 párrafos. Sin asteriscos. Sin bullets. Español directo.'
        )
        resp = groq_chat([{'role':'user','content':mensaje}], system=ctx, max_tokens=800, temperature=0.4)
        return jsonify({'respuesta':resp})
    except Exception as e: return jsonify({'respuesta':f'Error: {str(e)}'})

# ============================================================
# MONITOR
# ============================================================

def leer_estado_monitor(archivo):
    ruta = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

from monitor import mercado_abierto, hora_colombia, chat_id_de

@app.route('/monitor/<archivo>')
def monitor_view(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio
    portafolio  = leer_portafolio(archivo)
    composicion = portafolio.get('composicion', {})
    monitoreo   = portafolio.get('monitoreo_activo', False)
    estado      = leer_estado_monitor(archivo)   # helper abajo

    # ── Botón y badge de estado ─────────────────────────────
    if monitoreo:
        btn_m = (
            f'<form method="POST" action="/api/toggle-monitor/{archivo}">'
            '<button type="submit" style="padding:8px 20px;border-radius:980px;font-size:12px;'
            'font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(255,69,58,0.1);'
            'color:#ff453a;border:1px solid rgba(255,69,58,0.2)">Detener monitoreo</button></form>'
        )
        estado_badge = (
            '<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;'
            'border-radius:980px;font-size:12px;background:rgba(48,209,88,0.1);color:#30d158;'
            'border:1px solid rgba(48,209,88,0.2)">'
            '<span style="width:6px;height:6px;border-radius:50%;background:#30d158;'
            'animation:pulse 2s infinite"></span>Monitoreando activamente</span>'
        )
    else:
        btn_m = (
            f'<form method="POST" action="/api/toggle-monitor/{archivo}">'
            '<button type="submit" style="padding:8px 20px;border-radius:980px;font-size:12px;'
            'font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(0,113,227,0.12);'
            'color:#4da3ff;border:1px solid rgba(0,113,227,0.3)">Activar monitoreo</button></form>'
        )
        estado_badge = (
            '<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;'
            'border-radius:980px;font-size:12px;background:rgba(255,255,255,0.04);color:#6e6e73;'
            'border:1px solid rgba(255,255,255,0.08)">⚪ Inactivo</span>'
        )

    # ── Badge mercado ───────────────────────────────────────
    from monitor import mercado_abierto, hora_colombia
    if mercado_abierto():
        mercado_badge = (
            '<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;'
            'border-radius:980px;font-size:12px;margin-bottom:20px;'
            'background:rgba(48,209,88,0.08);color:#30d158;border:1px solid rgba(48,209,88,0.2)">'
            '<span style="width:6px;height:6px;border-radius:50%;background:#30d158;'
            'animation:pulse 2s infinite"></span>Mercado abierto · NYSE</div>'
        )
    else:
        ahora = hora_colombia()
        msg_c = 'Reabre el lunes a las 9:30 AM' if ahora.weekday() >= 5 else 'Reabre mañana a las 9:30 AM'
        mercado_badge = (
            f'<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;'
            f'border-radius:980px;font-size:12px;margin-bottom:20px;'
            f'background:rgba(255,255,255,0.04);color:#6e6e73;border:1px solid rgba(255,255,255,0.08)">'
            f'🔒 Mercado cerrado · {msg_c}</div>'
        )

    # ── Métricas rápidas ────────────────────────────────────
    resultados   = estado.get('resultados', [])
    dias_sin     = estado.get('dias_consecutivos_sin_senal', 0)
    n_entrar     = sum(1 for r in resultados if r['senal'] == 'ENTRAR')
    n_vigilar    = sum(1 for r in resultados if r['senal'] == 'VIGILAR')
    n_neutral    = sum(1 for r in resultados if r['senal'] == 'NEUTRAL')
    ultimo_ts    = estado.get('timestamp', '—')

    metricas_html = (
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">'
        f'<div style="background:rgba(48,209,88,0.06);border:1px solid rgba(48,209,88,0.15);'
        f'border-radius:12px;padding:14px 16px;text-align:center">'
        f'<p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 4px">Entrar</p>'
        f'<p style="color:#30d158;font-size:26px;font-weight:600;margin:0">{n_entrar}</p></div>'
        f'<div style="background:rgba(255,214,10,0.06);border:1px solid rgba(255,214,10,0.15);'
        f'border-radius:12px;padding:14px 16px;text-align:center">'
        f'<p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 4px">Vigilar</p>'
        f'<p style="color:#ffd60a;font-size:26px;font-weight:600;margin:0">{n_vigilar}</p></div>'
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        f'border-radius:12px;padding:14px 16px;text-align:center">'
        f'<p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 4px">Neutral</p>'
        f'<p style="color:#6e6e73;font-size:26px;font-weight:600;margin:0">{n_neutral}</p></div>'
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        f'border-radius:12px;padding:14px 16px;text-align:center">'
        f'<p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 4px">Días sin señal</p>'
        f'<p style="color:{"#ff453a" if dias_sin >= 5 else "#a1a1a6"};font-size:26px;font-weight:600;margin:0">{dias_sin}</p></div>'
        '</div>'
    )

    # ── Cards por activo ────────────────────────────────────
    activos_html = ''
    if resultados:
        for r in sorted(resultados, key=lambda x: x['score'], reverse=True):
            s   = r['senal']
            col = {'ENTRAR': '#30d158', 'VIGILAR': '#ffd60a', 'NEUTRAL': '#6e6e73'}.get(s, '#6e6e73')
            bg  = {'ENTRAR': 'rgba(48,209,88,0.06)', 'VIGILAR': 'rgba(255,214,10,0.06)',
                   'NEUTRAL': 'rgba(255,255,255,0.03)'}.get(s, 'rgba(255,255,255,0.03)')
            bd  = {'ENTRAR': 'rgba(48,209,88,0.18)', 'VIGILAR': 'rgba(255,214,10,0.18)',
                   'NEUTRAL': 'rgba(255,255,255,0.07)'}.get(s, 'rgba(255,255,255,0.07)')
            em  = {'ENTRAR': '🟢', 'VIGILAR': '🟡', 'NEUTRAL': '⚪'}.get(s, '⚪')

            # Barra de score
            barra_w  = int(r['score'] * 10)
            barra_c  = '#30d158' if r['score'] >= 6.5 else '#ffd60a' if r['score'] >= 4.5 else '#3d3d3f'

            btn_c = ''
            if s == 'ENTRAR':
                btn_c = (
                    f'<a href="/seguimiento/{archivo}?activo={r["ticker"]}" '
                    f'style="padding:6px 14px;border-radius:980px;font-size:11px;text-decoration:none;'
                    f'background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3);'
                    f'white-space:nowrap">Comprar →</a>'
                )

            peso_port = composicion.get(r['ticker'], 0)

            activos_html += (
                f'<div style="background:{bg};border:1px solid {bd};border-radius:14px;'
                f'padding:16px 20px;margin-bottom:10px">'

                # Encabezado
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
                f'<div style="display:flex;align-items:center;gap:10px">'
                f'<strong style="color:#f5f5f7;font-size:15px;font-family:monospace">{r["ticker"]}</strong>'
                f'<span style="color:#6e6e73;font-size:12px">{peso_port*100:.1f}% del portafolio</span>'
                f'</div>'
                f'<div style="display:flex;align-items:center;gap:10px">'
                f'<span style="padding:4px 12px;border-radius:980px;font-size:11px;font-weight:500;'
                f'background:{bg};color:{col};border:1px solid {bd}">{em} {s}</span>'
                f'{btn_c}</div></div>'

                # Precio grande
                f'<div style="margin-bottom:12px">'
                f'<span style="color:#f5f5f7;font-size:22px;font-weight:600">${r["precio"]:,.2f}</span>'
                f'<span style="color:{"#30d158" if r["tendencia"]>0 else "#ff453a"};font-size:13px;margin-left:8px">'
                f'{r["tendencia"]:+.1f}% (20d)</span>'
                f'</div>'

                # Score bar
                f'<div style="margin-bottom:12px">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
                f'<span style="font-size:11px;color:#6e6e73;text-transform:uppercase;letter-spacing:0.05em">Score de entrada</span>'
                f'<span style="font-size:13px;font-weight:600;color:{barra_c}">{r["score"]}/10</span></div>'
                f'<div style="background:rgba(255,255,255,0.06);border-radius:980px;height:5px;overflow:hidden">'
                f'<div style="background:{barra_c};height:100%;width:{barra_w}%;transition:width 0.4s"></div>'
                f'</div></div>'

                # Métricas
                f'<div style="display:flex;gap:16px;flex-wrap:wrap">'
                f'<div><p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 2px">RSI</p>'
                f'<p style="color:{"#30d158" if r["rsi"]<40 else "#ffd60a" if r["rsi"]<55 else "#ff453a"};font-size:13px;font-weight:500;margin:0">{r["rsi"]}</p></div>'
                f'<div><p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 2px">MA20</p>'
                f'<p style="color:#a1a1a6;font-size:13px;font-weight:500;margin:0">${r["ma20"]:,.2f}</p></div>'
                f'<div><p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 2px">MA50</p>'
                f'<p style="color:#a1a1a6;font-size:13px;font-weight:500;margin:0">${r["ma50"]:,.2f}</p></div>'
                f'<div><p style="color:#6e6e73;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 2px">Vol ratio</p>'
                f'<p style="color:{"#ffd60a" if r["vol_ratio"]>1.5 else "#a1a1a6"};font-size:13px;font-weight:500;margin:0">{r["vol_ratio"]}x</p></div>'
                f'</div></div>'
            )
    elif composicion and not estado:
        activos_html = (
        '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:14px;padding:40px;text-align:center;color:#6e6e73">'
        'Activa el monitoreo para ver el análisis en tiempo real.<br>'
        '<span style="font-size:12px;display:block;margin-top:8px">'
        'El primer análisis arranca automáticamente.</span></div>'
    )
    elif composicion and estado and not resultados:   # ← NUEVO CASO
        activos_html = (
        '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:14px;padding:40px;text-align:center;color:#6e6e73">'
        '⏳ Esperando primer ciclo de análisis...<br>'
        '<span style="font-size:12px;display:block;margin-top:8px">'
        'El monitor está activo. El análisis corre cuando el mercado abre (9:30am).</span></div>'
    )
    else:
        activos_html = (
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        f'border-radius:14px;padding:40px;text-align:center;color:#6e6e73">'
        f'Sin composición definida.<br>'
        f'<a href="/analista/{archivo}" style="color:#4da3ff;font-size:13px;'
        f'text-decoration:none;margin-top:12px;display:inline-block">Ir al Analista →</a></div>'
    )

    # ── Análisis IA del ciclo ───────────────────────────────
    ia_html = ''
    if estado.get('justificacion') or estado.get('prediccion'):
        pred = estado.get('prediccion', '')
        just = estado.get('justificacion', '')
        pc   = '#30d158' if '🟢' in pred else '#ffd60a' if '👁' in pred else '#6e6e73'
        ia_html = (
            '<div style="margin-top:20px">'
            '<p style="color:#6e6e73;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">Análisis del último ciclo</p>'
            '<div style="background:rgba(0,113,227,0.05);border:1px solid rgba(0,113,227,0.12);'
            'border-radius:14px;padding:18px 20px">'
            f'<div style="display:flex;gap:10px;align-items:flex-start">'
            f'<div style="width:28px;height:28px;background:#0a0a0a;border-radius:8px;display:flex;'
            f'align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.08);'
            f'flex-shrink:0;margin-top:2px">{LOGO_SM}</div>'
            f'<div style="flex:1">'
            + (f'<p style="color:#a1a1a6;font-size:13px;line-height:1.6;margin:0 0 10px">{just}</p>' if just else '')
            + f'<div style="padding:8px 12px;border-radius:8px;background:rgba(255,255,255,0.04);'
            f'border:1px solid rgba(255,255,255,0.07)">'
            f'<p style="color:{pc};font-size:13px;font-weight:500;margin:0">{pred}</p></div>'
            f'<p style="color:#6e6e73;font-size:10px;margin:8px 0 0">Último análisis: {ultimo_ts}</p>'
            f'</div></div></div></div>'
        )

    # ── Alerta subóptima ────────────────────────────────────
    sub_html = ''
    if estado.get('alerta_suboptimal') and dias_sin >= 5:
        sub_html = (
            '<div style="margin-top:16px;background:rgba(255,159,10,0.06);'
            'border:1px solid rgba(255,159,10,0.2);border-radius:14px;padding:18px 20px">'
            '<div style="display:flex;gap:10px;align-items:flex-start">'
            '<div style="font-size:20px;flex-shrink:0">⚠️</div>'
            '<div>'
            f'<p style="color:#ff9f0a;font-size:13px;font-weight:500;margin:0 0 6px">'
            f'{dias_sin} días sin señal ideal — considera entrada parcial</p>'
            f'<p style="color:#a1a1a6;font-size:13px;line-height:1.6;margin:0">'
            f'{estado["alerta_suboptimal"]}</p>'
            '</div></div></div>'
        )

    # ── Reporte de cierre guardado ──────────────────────────
    cierre_html = ''
    if estado.get('reporte_cierre') and estado.get('reporte_cierre_fecha') == hora_colombia().strftime('%Y-%m-%d'):
        cierre_html = (
            '<div style="margin-top:20px">'
            '<p style="color:#6e6e73;font-size:11px;text-transform:uppercase;'
            'letter-spacing:0.06em;margin-bottom:10px">Reporte de cierre de hoy</p>'
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
            'border-radius:14px;padding:18px 20px;font-size:13px;color:#a1a1a6;'
            'line-height:1.7;white-space:pre-wrap">'
            + estado.get('reporte_cierre', '').replace('<b>', '').replace('</b>', '')
              .replace('<i>', '').replace('</i>', '').replace('<br>', '\n')
            + '</div></div>'
        )

    # ── Configuración del ciclo ─────────────────────────────
    config_html = (
        '<div style="margin-top:20px;padding:14px 18px;background:rgba(255,255,255,0.02);'
        'border:1px solid rgba(255,255,255,0.06);border-radius:12px;'
        'display:flex;gap:24px;flex-wrap:wrap">'
        f'<span style="font-size:12px;color:#6e6e73">🔄 Ciclo cada <strong style="color:#a1a1a6">18 min</strong></span>'
        f'<span style="font-size:12px;color:#6e6e73">🟢 Umbral entrada <strong style="color:#a1a1a6">≥ 6.5/10</strong></span>'
        f'<span style="font-size:12px;color:#6e6e73">📋 Cierre <strong style="color:#a1a1a6">4:30pm Colombia</strong></span>'
        f'<span style="font-size:12px;color:#6e6e73">⚠️ Alerta subóptima <strong style="color:#a1a1a6">≥ 5 días sin señal</strong></span>'
        f'<span style="font-size:12px;color:#6e6e73">📲 Notificaciones <strong style="color:#a1a1a6">Telegram + app</strong></span>'
        + (
    '<div style="width:100%;margin-top:8px;padding:8px 10px;background:rgba(255,214,10,0.06);'
    'border-radius:8px;border:1px solid rgba(255,214,10,0.15)">'
    '<p style="font-size:11px;color:#ffd60a;margin:0">⚠️ Sin Telegram configurado — '
    've a <a href="/settings" style="color:#ffd60a">Mi Perfil</a> para activar las alertas</p>'
    '</div>'
    if not portafolio.get('telegram_chat_id') and not chat_id_de(portafolio) else ''
)
+ '</div>'
    )

    contenido = (
        '<div class="container">'
        + nav_html(archivo, 'monitor') +
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'margin-bottom:20px;flex-wrap:wrap;gap:12px">'
        '<div>'
        '<h2 style="margin:0 0 4px">Monitor de Mercado</h2>'
        '<p style="color:#6e6e73;font-size:13px;margin:0">'
        'Análisis automático · NYSE 9:30am–4:00pm Colombia</p></div>'
        f'<div style="display:flex;align-items:center;gap:12px">{estado_badge}{btn_m}</div></div>'
        + mercado_badge
        + metricas_html
        + '<p style="color:#6e6e73;font-size:11px;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:10px">Estado de activos</p>'
        + activos_html
        + ia_html
        + sub_html
        + cierre_html
        + config_html
        + '<div style="text-align:center;margin-top:24px;padding-bottom:32px">'
        '<button onclick="location.reload()" style="padding:8px 24px;border-radius:980px;'
        'font-size:12px;font-family:DM Sans,sans-serif;cursor:pointer;'
        'background:rgba(255,255,255,0.05);color:#6e6e73;border:1px solid rgba(255,255,255,0.08)">'
        'Actualizar</button>'
        '<p style="color:#3d3d3f;font-size:11px;margin-top:8px">'
        'Se actualiza automáticamente cada 60 segundos</p>'
        '</div></div>'
        '<style>@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}</style>'
        '<script>setTimeout(()=>location.reload(),60000);</script>'
    )
    return pagina(f'Monitor — {portafolio["nombre"]}', contenido)

@app.route('/api/toggle-monitor/<archivo>', methods=['POST'])
def api_toggle_monitor(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    try:
        ruta = f'datos/portafolios/{archivo}'
        with open(ruta, 'r', encoding='utf-8') as f:
            d = json.load(f)
 
        nuevo_estado = not d.get('monitoreo_activo', False)
        d['monitoreo_activo'] = nuevo_estado
 
        # Si se está ACTIVANDO: desactivar todos los demás portafolios del usuario
        if nuevo_estado:
            username = session.get('username', '')
            from gestor_portafolio import listar_portafolios_de_usuario
            todos = listar_portafolios_de_usuario(username)
            for p in todos:
                if p['archivo'] != archivo:
                    otra_ruta = f'datos/portafolios/{p["archivo"]}'
                    try:
                        with open(otra_ruta, 'r', encoding='utf-8') as f2:
                            otro = json.load(f2)
                        if otro.get('monitoreo_activo'):
                            otro['monitoreo_activo'] = False
                            with open(otra_ruta, 'w', encoding='utf-8') as f2:
                                json.dump(otro, f2, indent=2, ensure_ascii=False)
                            print(f"🔴 Monitor desactivado en {p['archivo']} (exclusividad)")
                    except:
                        pass
 
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
 
        # Si se acaba de activar, disparar primer ciclo inmediatamente
        if nuevo_estado:
            from monitor import ciclo_portafolio
            def primer_ciclo():
                import time
                time.sleep(2)
                try:
                    ciclo_portafolio(archivo, d)
                except Exception as e:
                    print(f"❌ Primer ciclo error: {e}")
            threading.Thread(target=primer_ciclo, daemon=True).start()
 
    except Exception as e:
        print(f"❌ toggle-monitor error: {e}")
    return redirect(url_for('monitor_view', archivo=archivo))
 


# ============================================================
# CONFIGURACIÓN
# ============================================================

@app.route('/config/<archivo>', methods=['GET','POST'])
def config_view(archivo):
    redir = verificar_acceso(archivo)
    if redir: return redir
    from gestor_portafolio import leer_portafolio, activar_portafolio
    import hashlib
    portafolio=leer_portafolio(archivo); mensaje=''; error=''
    if request.method=='POST':
        accion=request.form.get('accion','')
        if accion=='actualizar':
            try:
                ruta=f'datos/portafolios/{archivo}'
                with open(ruta,'r',encoding='utf-8') as f: d=json.load(f)
                d['email']=request.form.get('email','').strip()
                d['telegram_chat_id']=request.form.get('telegram','').strip()
                npw=request.form.get('nueva_password','').strip()
                if npw: d['password_hash']=hashlib.sha256(npw.encode()).hexdigest()
                with open(ruta,'w',encoding='utf-8') as f: json.dump(d,f,indent=2,ensure_ascii=False)
                portafolio=d; mensaje='Configuración actualizada.'
            except Exception as e: error=f'Error: {str(e)}'
        elif accion=='activar':
            activar_portafolio(archivo); mensaje='Portafolio activado.'
    msg_html=f'<div class="alert alert-success">{mensaje}</div>' if mensaje else ''
    err_html=f'<div class="alert alert-error">{error}</div>' if error else ''
    est=('<span class="badge badge-green">ACTIVO para monitoreo</span>' if portafolio.get('activo') else '<span class="badge badge-gray">INACTIVO</span>')
    btn_act=('' if portafolio.get('activo') else
        '<form method="POST" style="margin-top:12px"><input type="hidden" name="accion" value="activar">'
        '<button type="submit" class="btn btn-secondary" style="width:auto">Activar para monitoreo</button></form>')
    contenido=(
        '<div class="container" style="max-width:600px">'+nav_html(archivo,'config')+'<h2>Configuración</h2>'
        +msg_html+err_html+
        '<div class="card" style="margin-bottom:16px">'
        '<div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:rgba(0,113,227,0.06);'
        'border-radius:10px;border:1px solid rgba(0,113,227,0.15)">'
        '<span style="font-size:20px">ℹ️</span>'
        '<div>'
        '<p style="color:#f5f5f7;font-size:13px;font-weight:500;margin:0 0 2px">Datos personales</p>'
        '<p style="color:#6e6e73;font-size:12px;margin:0">Para cambiar tu email, Telegram o contraseña ve a '
        '<a href="/settings" style="color:#4da3ff">Mi Perfil</a>. '
        'Aquí solo se configura lo relacionado al portafolio.</p>'
        '</div></div></div>'
        '<div class="card"><form method="POST"><input type="hidden" name="accion" value="actualizar">'
        '<div class="form-group"><label>Nueva contraseña del portafolio (vacío = no cambiar)</label>'
        '<input type="password" name="nueva_password" class="form-input" placeholder="Nueva contraseña"></div>'
        '<button type="submit" class="btn btn-primary">Guardar cambios</button></form></div>'
        f'<div class="card"><h3>Estado</h3><div style="margin:12px 0;color:#a1a1a6">Estado actual: {est}</div>{btn_act}</div>'
        '<div class="card" style="border-color:rgba(255,69,58,0.2)">'
        '<h3 style="color:#ff453a">Zona de peligro</h3>'
        '<p style="color:#6e6e73;font-size:13px;margin-bottom:16px">Estas acciones son permanentes y no se pueden deshacer.</p>'
        f'<button onclick="confirmarEliminar()" '
        'style="padding:8px 20px;border-radius:980px;font-size:12px;font-family:DM Sans,sans-serif;'
        'cursor:pointer;background:rgba(255,69,58,0.1);color:#ff453a;'
        'border:1px solid rgba(255,69,58,0.3);margin-right:10px">Eliminar portafolio</button>'
        '<button onclick="eliminarCuenta()" '
        'style="padding:8px 20px;border-radius:980px;font-size:12px;font-family:DM Sans,sans-serif;'
        'cursor:pointer;background:rgba(255,69,58,0.15);color:#ff453a;'
        'border:1px solid rgba(255,69,58,0.4)">🗑 Eliminar mi cuenta</button>'
        '</div></div>'
        '<script>'
        f'async function eliminarCuenta(){{'
        f'  if(!confirm("¿Eliminar tu cuenta y TODOS tus portafolios? Esta acción no se puede deshacer.")){{'
        f'    return;'
        f'  }}'
        f'  if(!confirm("Segunda confirmación: ¿realmente quieres eliminar tu cuenta?"))'
        f'    return;'
        f'  const r = await fetch("/api/eliminar-cuenta", {{method:"POST"}});'
        f'  const d = await r.json();'
        f'  if(d.ok) window.location.href = "/login";'
        f'  else alert("Error: " + d.error);'
        f'}}'
        f'function confirmarEliminar(){{'
        f'  if(confirm("¿Estás seguro? Esta acción eliminará el portafolio {portafolio["nombre"]} permanentemente.")){{'
        f'    if(confirm("Segunda confirmación: ¿realmente quieres eliminar {portafolio["nombre"]}?")){{'
        f'      fetch("/api/eliminar-portafolio/{archivo}",{{method:"POST"}})'
        f'        .then(r=>r.json())'
        f'        .then(d=>{{if(d.ok)window.location.href="/mis-portafolios";else alert("Error: "+d.error);}});'
        f'    }}'
        f'  }}'
        f'}}'
        '</script>'
    )
    return pagina(f'Configuración — {portafolio["nombre"]}', contenido)

# ============================================================
# ADMIN
# ============================================================

@app.route('/admin')
def admin_panel():
    if not session.get('es_admin'):
        return redirect(url_for('mis_portafolios'))
    from gestor_portafolio import _leer_usuarios, listar_portafolios, leer_portafolio
    usuarios    = _leer_usuarios()
    portafolios = listar_portafolios()
    ports_por_usuario = {}
    for p in portafolios:
        try:
            data = leer_portafolio(p['archivo'])
            owner = data.get('owner', '—')
            ports_por_usuario[owner] = ports_por_usuario.get(owner, 0) + 1
        except: continue
    filas_usuarios = ''
    for u in usuarios.values():
        admin_badge = '<span class="badge badge-yellow">ADMIN</span>' if u.get('es_admin') else ''
        n_ports = ports_por_usuario.get(u['username'], 0)
        filas_usuarios += (
            f'<tr>'
            f'<td><strong style="color:#f5f5f7">{u["username"]}</strong></td>'
            f'<td>{u["email"]}</td>'
            f'<td>{u.get("telegram_chat_id") or "—"}</td>'
            f'<td>{n_ports}</td>'
            f'<td>{u.get("fecha_registro","—")}</td>'
            f'<td>{admin_badge}</td>'
            f'<td style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">'
            f'<button onclick="toggleAdmin(\'{u["username"]}\',{str(u.get("es_admin",False)).lower()})" '
            f'style="padding:4px 12px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
            f'background:rgba(255,255,255,0.05);color:#6e6e73;border:1px solid rgba(255,255,255,0.1)">'
            f'{"Quitar admin" if u.get("es_admin") else "Hacer admin"}</button>'
            f'<button onclick="resetPassword(\'{u["username"]}\')" '
            f'style="padding:4px 12px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
            f'background:rgba(255,69,58,0.08);color:#ff453a;border:1px solid rgba(255,69,58,0.2)">'
            f'Reset contraseña</button>'
            + (
            f'<button onclick="desbloquear(\'{u["username"]}\')" '
            f'style="padding:4px 12px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
            f'background:rgba(255,214,10,0.08);color:#ffd60a;border:1px solid rgba(255,214,10,0.2)">'
            f'🔓 Desbloquear</button>'
            if u.get("bloqueado_hasta") else ''
            ) +
            f'<button onclick="eliminarUsuario(\'{u["username"]}\')" '
            f'style="padding:4px 12px;border-radius:980px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
            f'background:rgba(255,69,58,0.06);color:#ff453a;border:1px solid rgba(255,69,58,0.15)">'
            f'🗑 Eliminar</button>'
            f'</td>'
            f'</tr>'
        )
    filas_ports = ''
    for p in portafolios:
        try:
            mon = ('<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;'
                   'border-radius:980px;font-size:11px;background:rgba(48,209,88,0.1);'
                   'color:#30d158;border:1px solid rgba(48,209,88,0.2)">'
                   '<span style="width:5px;height:5px;border-radius:50%;background:#30d158"></span>Activo</span>'
                   if p.get('monitoreo_activo')
                   else '<span style="color:#3d3d3f;font-size:12px">Inactivo</span>')
            senal = p.get('ultima_senal', '—')
            ts    = p.get('ultimo_analisis', '—')
            if ts and ts != '—' and len(ts) > 16:
                ts = ts[:16]
            filas_ports += (
                f'<tr>'
                f'<td><strong style="color:#f5f5f7">{p["nombre"]}</strong></td>'
                f'<td style="color:#a1a1a6">{p.get("owner","—")}</td>'
                f'<td>{p["perfil"].upper()}</td>'
                f'<td>{p["fecha_inicio"]}</td>'
                f'<td>{mon}</td>'
                f'<td>{senal}</td>'
                f'<td style="font-size:11px;color:#6e6e73">{ts}</td>'
                f'</tr>'
            )
        except: continue
        from gestor_portafolio import _leer_logs
    logs_actividad = list(reversed(_leer_logs()))[:100]

    iconos = {
        'login_ok':      '✅',
        'login_fail':    '❌',
        'registro_nuevo':'🆕',
        'logout':        '👋'
    }
    colores = {
        'login_ok':      'rgba(48,209,88,0.08)',
        'login_fail':    'rgba(255,69,58,0.08)',
        'registro_nuevo':'rgba(0,113,227,0.08)',
        'logout':        'rgba(255,255,255,0.03)'
    }
    filas_logs = ''
    for log in logs_actividad:
        icono  = iconos.get(log['tipo'], '•')
        color  = colores.get(log['tipo'], 'transparent')
        filas_logs += (
            f'<tr style="background:{color}">'
            f'<td style="font-size:16px">{icono}</td>'
            f'<td>{log["fecha"]}</td>'
            f'<td><strong style="color:#f5f5f7">{log["username"]}</strong></td>'
            f'<td style="color:#6e6e73">{log["email"]}</td>'
            f'<td>{log["detalle"]}</td>'
            f'<td style="font-family:var(--font-mono,monospace);font-size:11px;color:#6e6e73">{log["ip"]}</td>'
            f'<td style="font-size:11px;color:#3d3d3f;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{log["dispositivo"]}</td>'
            f'</tr>'
        )
    if not filas_logs:
        filas_logs = '<tr><td colspan="7" style="text-align:center;color:#3d3d3f;padding:20px">Sin actividad registrada aún</td></tr>'
    contenido = (
        '<div class="container">'
        '<div style="margin-bottom:24px"><a href="/mis-portafolios" style="color:#6e6e73;font-size:0.85rem;text-decoration:none">← Volver</a></div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:28px">'
        '<h2 style="margin:0">Panel de Administración</h2>'
        f'<span style="color:#6e6e73;font-size:13px">{len(usuarios)} usuarios · {len(portafolios)} portafolios</span></div>'
        '<div class="grid-4" style="margin-bottom:28px">'
        f'<div class="card"><h3>Usuarios</h3><div class="metric-value">{len(usuarios)}</div></div>'
        f'<div class="card"><h3>Portafolios</h3><div class="metric-value">{len(portafolios)}</div></div>'
        f'<div class="card"><h3>Monitoreando</h3><div class="metric-value">{sum(1 for p in portafolios if p.get("monitoreo_activo"))}</div></div>'
        f'<div class="card"><h3>Admins</h3><div class="metric-value">{sum(1 for u in usuarios.values() if u.get("es_admin"))}</div></div>'
        '</div>'
        '<div class="section-title">Usuarios registrados</div>'
        '<div class="card" style="margin-bottom:24px"><table class="tabla">'
        '<thead><tr><th>Usuario</th><th>Email</th><th>Telegram</th><th>Portafolios</th><th>Registro</th><th>Rol</th><th>Acciones</th></tr></thead>'
        f'<tbody>{filas_usuarios}</tbody></table></div>'
        '<div class="section-title">Todos los portafolios</div>'
        '<div class="card"><table class="tabla">'
        '<thead><tr><th>Nombre</th><th>Dueño</th><th>Perfil</th><th>Fecha inicio</th><th>Monitor</th><th>Última señal</th><th>Último análisis</th></tr></thead>'
        f'<tbody>{filas_ports}</tbody></table></div>'

        '<div class="section-title" style="margin-top:28px">Registro de Actividad</div>'
        '<div class="card"><div style="overflow-x:auto"><table class="tabla">'
        '<thead><tr><th></th><th>Fecha</th><th>Usuario</th><th>Email</th><th>Evento</th><th>IP</th><th>Dispositivo</th></tr></thead>'
        f'<tbody>{filas_logs}</tbody>'
        '</table></div></div></div>'
        '<script>'
        'async function resetPassword(username) {'
'  if (!confirm(`¿Resetear contraseña de ${username} a "cambiar123"?`)) return;'
'  const r = await fetch("/api/admin/reset-password", {'
'    method: "POST",'
'    headers: {"Content-Type": "application/json"},'
'    body: JSON.stringify({username})'
'  });'
'  const d = await r.json();'
'  if (d.ok) alert(d.mensaje);'
'  else alert("Error: " + d.error);'
'}'
        'async function eliminarUsuario(username) {'
        '  if (!confirm(`¿Eliminar la cuenta de ${username} y todos sus portafolios? Esta acción no se puede deshacer.`)) return;'
        '  if (!confirm(`Segunda confirmación: ¿realmente quieres eliminar a ${username}?`)) return;'
        '  const r = await fetch("/api/admin/eliminar-usuario", {'
        '    method: "POST",'
        '    headers: {"Content-Type": "application/json"},'
        '    body: JSON.stringify({username})'
        '  });'
        '  const d = await r.json();'
        '  if (d.ok) { alert(`✅ Usuario ${username} eliminado`); location.reload(); }'
        '  else alert("Error: " + d.error);'
        '}'
        'async function desbloquear(username) {'
        '  if (!confirm(`¿Desbloquear la cuenta de ${username}?`)) return;'
        '  const r = await fetch("/api/admin/desbloquear", {'
        '    method: "POST",'
        '    headers: {"Content-Type": "application/json"},'
        '    body: JSON.stringify({username})'
        '  });'
        '  const d = await r.json();'
        '  if (d.ok) { alert(`✅ ${username} desbloqueado`); location.reload(); }'
        '  else alert("Error: " + d.error);'
        '}'
        'async function toggleAdmin(username, esAdmin) {'
        '  if (!confirm(`¿${esAdmin?"quitar":"dar"} permisos de admin a ${username}?`)) return;'
        '  const r = await fetch("/api/admin/toggle-admin", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,es_admin:!esAdmin})});'
        '  const d = await r.json();'
        '  if (d.ok) location.reload(); else alert("Error: "+d.error);'
        '}'
        '</script>'
    )
    return pagina('Administración', contenido)

@app.route('/api/admin/reset-password', methods=['POST'])
def api_reset_password():
    if not session.get('es_admin'):
        return jsonify({'ok': False, 'error': 'No autorizado'})
    from gestor_portafolio import resetear_password
    data     = request.get_json()
    username = data.get('username')
    ok = resetear_password(username)
    return jsonify({'ok': ok, 'mensaje': f'Contraseña de {username} reseteada a: cambiar123'})

@app.route('/api/admin/desbloquear', methods=['POST'])
def api_desbloquear():
    if not session.get('es_admin'):
        return jsonify({'ok': False, 'error': 'No autorizado'})
    from gestor_portafolio import desbloquear_usuario
    data = request.get_json()
    ok = desbloquear_usuario(data.get('username'))
    return jsonify({'ok': ok})

@app.route('/api/admin/toggle-admin', methods=['POST'])
def api_toggle_admin():
    if not session.get('es_admin'):
        return jsonify({'ok': False, 'error': 'No autorizado'})
    from gestor_portafolio import actualizar_usuario
    data = request.get_json()
    ok = actualizar_usuario(data.get('username'), {'es_admin': data.get('es_admin', False)})
    return jsonify({'ok': ok})

# ============================================================
# APIs
# ============================================================

@app.route('/api/eliminar-cuenta', methods=['POST'])
def api_eliminar_cuenta():
    if not session.get('username'):
        return jsonify({'ok': False, 'error': 'No autorizado'})
    from gestor_portafolio import eliminar_usuario
    username = session.get('username')
    # El admin no puede eliminarse a sí mismo
    if session.get('es_admin'):
        return jsonify({'ok': False, 'error': 'El admin no puede eliminarse desde aquí. Hazlo desde el panel.'})
    ok = eliminar_usuario(username)
    if ok:
        session.clear()
    return jsonify({'ok': ok})

@app.route('/api/admin/eliminar-usuario', methods=['POST'])
def api_admin_eliminar_usuario():
    if not session.get('es_admin'):
        return jsonify({'ok': False, 'error': 'No autorizado'})
    from gestor_portafolio import eliminar_usuario, registrar_actividad
    data     = request.get_json()
    username = data.get('username')
    if username == session.get('username'):
        return jsonify({'ok': False, 'error': 'No puedes eliminarte a ti mismo'})
    ok = eliminar_usuario(username)
    if ok:
        registrar_actividad('eliminacion', username, detalle='Cuenta eliminada por admin',
            ip=request.headers.get('X-Forwarded-For', request.remote_addr or '—').split(',')[0].strip(),
            dispositivo=request.headers.get('User-Agent','—')[:120])
    return jsonify({'ok': ok})

@app.route('/api/eliminar-portafolio/<archivo>', methods=['POST'])
def api_eliminar_portafolio(archivo):
    if verificar_acceso(archivo): return jsonify({'ok': False, 'error': 'No autorizado'})
    try:
        ruta = f'datos/portafolios/{archivo}'
        ruta_monitor = f'datos/portafolios/monitor_{archivo}'
        if os.path.exists(ruta): os.remove(ruta)
        if os.path.exists(ruta_monitor): os.remove(ruta_monitor)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/fix-banrep')
def fix_banrep():
    if not session.get('es_admin'):
        return jsonify({'error': 'No autorizado'})
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ruta = os.path.join(BASE_DIR, "datos", "macro", "tasa_banrep.parquet")
    if os.path.exists(ruta):
        os.remove(ruta)
        return jsonify({'ok': True, 'mensaje': 'Archivo borrado. Ahora haz clic en Actualizar datos.'})
    return jsonify({'ok': False, 'mensaje': 'Archivo no encontrado'})

@app.route('/api/verificar-ticker/<ticker>')
def api_verificar_ticker(ticker):
    if not session.get('username'):
        return jsonify({'valido': False})
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        hoy = datetime.now()
        df  = yf.download(ticker, start=(hoy-timedelta(days=5)).strftime("%Y-%m-%d"),
                          end=hoy.strftime("%Y-%m-%d"), interval="1d",
                          auto_adjust=True, progress=False)
        if df.empty:
            return jsonify({'valido': False})
        if hasattr(df.columns, 'get_level_values'):
            df.columns = df.columns.get_level_values(0)
        precio = round(float(df['Close'].iloc[-1]), 2)
        try:
            info   = yf.Ticker(ticker).info
            nombre = info.get('shortName', ticker)
        except:
            nombre = ticker
        # Verificar si ya está en el histórico
        precios_path = os.path.join(DATOS_DIR, "precios", "precios.parquet")
        es_nuevo = True
        if os.path.exists(precios_path):
            import pandas as pd
            cols = pd.read_parquet(precios_path).columns.tolist()
            es_nuevo = ticker not in cols
        # Si es nuevo lanzar descarga en background
        if es_nuevo:
            def descargar_historico(tk):
                try:
                    import pandas as pd
                    hoy2   = datetime.now()
                    inicio = (hoy2 - timedelta(days=365*10)).strftime("%Y-%m-%d")
                    df2    = yf.download(tk, start=inicio, end=hoy2.strftime("%Y-%m-%d"),
                                        interval="1d", auto_adjust=True, progress=False)
                    if df2.empty:
                        return
                    if hasattr(df2.columns, 'get_level_values'):
                        df2.columns = df2.columns.get_level_values(0)
                    close = df2[['Close']].rename(columns={'Close': tk})
                    if os.path.exists(precios_path):
                        existente = pd.read_parquet(precios_path)
                        if tk not in existente.columns:
                            nuevo = existente.join(close, how='outer')
                            nuevo.to_parquet(precios_path)
                            print(f"✅ Histórico de {tk} agregado")
                    else:
                        close.to_parquet(precios_path)
                    # Marcar como listo
                    listo_path = os.path.join(DATOS_DIR, f"ticker_listo_{tk}.flag")
                    open(listo_path, 'w').close()
                except Exception as e:
                    print(f"❌ Error descargando histórico de {tk}: {e}")
                    # Marcar como fallido
                    listo_path = os.path.join(DATOS_DIR, f"ticker_listo_{tk}.flag")
                    open(listo_path, 'w').close()
            threading.Thread(target=descargar_historico, args=(ticker,), daemon=True).start()
        return jsonify({
            'valido':   True,
            'precio':   precio,
            'nombre':   nombre,
            'es_nuevo': es_nuevo
        })
    except Exception as e:
        return jsonify({'valido': False, 'error': str(e)})

@app.route('/api/ticker-listo/<ticker>')
def api_ticker_listo(ticker):
    """Verifica si el historico de un ticker nuevo ya terminó de descargarse."""
    if not session.get('username'):
        return jsonify({'listo': False})
    # Si ya estaba en el histórico desde el inicio, siempre listo
    precios_path = os.path.join(DATOS_DIR, "precios", "precios.parquet")
    if os.path.exists(precios_path):
        import pandas as pd
        cols = pd.read_parquet(precios_path).columns.tolist()
        if ticker in cols:
            return jsonify({'listo': True})
    # Verificar flag
    flag = os.path.join(DATOS_DIR, f"ticker_listo_{ticker}.flag")
    listo = os.path.exists(flag)
    if listo:
        # Limpiar flag
        try: os.remove(flag)
        except: pass
    return jsonify({'listo': listo})

@app.route('/api/test-telegram')
def api_test_telegram():
    if not session.get('es_admin'):
        return jsonify({'error': 'No autorizado'})
    from gestor_portafolio import _leer_usuarios
    from scheduler import enviar_resumenes_diarios
    usuarios = _leer_usuarios()
    info = []
    for username, u in usuarios.items():
        chat_id = u.get('telegram_chat_id', '').strip()
        info.append({
            'username': username,
            'chat_id': chat_id if chat_id else '— sin configurar —'
        })
    # Intentar enviar
    enviar_resumenes_diarios()
    return jsonify({
        'ok': True,
        'mensaje': 'Resúmenes enviados. Revisa Telegram.',
        'usuarios': info
    })

@app.route('/api/profile', methods=['GET'])
def get_profile():
    if not session.get('username'):
        return jsonify({'error': 'No autorizado'})
    from gestor_portafolio import get_usuario
    u = get_usuario(session['username'])
    if not u:
        return jsonify({'error': 'Usuario no encontrado'})
    return jsonify({
        'username':          u.get('username'),
        'email':             u.get('email'),
        'telegram_chat_id':  u.get('telegram_chat_id', ''),
        'email_notifications': u.get('email_notifications', True)
    })

@app.route('/api/profile', methods=['PUT'])
def update_profile():
    if not session.get('username'):
        return jsonify({'error': 'No autorizado'})
    from gestor_portafolio import actualizar_usuario, get_usuario
    from werkzeug.security import generate_password_hash, check_password_hash
    data     = request.get_json()
    username = session['username']
    campos   = {}
    if 'email' in data and data['email']:
        campos['email'] = data['email'].strip()
    if 'telegram_chat_id' in data:
        campos['telegram_chat_id'] = data['telegram_chat_id'].strip()
    if 'email_notifications' in data:
        campos['email_notifications'] = data['email_notifications']
    if 'new_password' in data and data['new_password']:
        u = get_usuario(username)
        ph = u.get('password_hash', '')
        cur = data.get('current_password', '')
        from gestor_portafolio import hash_password
        if hash_password(cur) != ph:
            return jsonify({'error': 'Contraseña actual incorrecta'}), 400
        campos['password_hash'] = hash_password(data['new_password'])
    if not campos:
        return jsonify({'error': 'Sin cambios'}), 400
    ok = actualizar_usuario(username, campos)
    if ok:
        return jsonify({'ok': True, 'mensaje': 'Perfil actualizado correctamente'})
    return jsonify({'error': 'Error actualizando perfil'}), 500

@app.route('/settings')
def settings():
    if not session.get('username'):
        return redirect(url_for('login'))
    from gestor_portafolio import get_usuario
    u = get_usuario(session['username'])
    contenido = (
        '<div class="container" style="max-width:600px">'
        '<h2 style="margin-bottom:24px">Mi Perfil</h2>'

        # Información personal
        '<div class="card" style="margin-bottom:16px">'
        '<h3 style="margin-bottom:16px">Información personal</h3>'
        f'<div class="form-group"><label>Nombre de usuario</label>'
        f'<input type="text" class="form-input" value="{u.get("username","")}" disabled style="opacity:0.5"></div>'
        f'<div class="form-group"><label>Email</label>'
        f'<input type="email" id="p-email" class="form-input" value="{u.get("email","")}" placeholder="tu@email.com"></div>'
        f'<div class="form-group"><label>Telegram Chat ID</label>'
        f'<input type="text" id="p-telegram" class="form-input" value="{u.get("telegram_chat_id","")}" placeholder="ej: 3002443898">'
       '<div style="margin-top:8px;padding:12px 14px;background:rgba(0,113,227,0.06);border:1px solid rgba(0,113,227,0.15);border-radius:10px">'
'<p style="font-size:12px;color:#4da3ff;font-weight:500;margin:0 0 6px">📲 Cómo activar las alertas de Telegram</p>'
'<p style="font-size:11px;color:#a1a1a6;margin:0 0 4px">1. Abre Telegram y busca <strong style="color:#f5f5f7">@Miportafolio_andrea_bot</strong></p>'
'<p style="font-size:11px;color:#a1a1a6;margin:0 0 4px">2. Presiona <strong style="color:#f5f5f7">Iniciar / Start</strong></p>'
'<p style="font-size:11px;color:#a1a1a6;margin:0 0 4px">3. El bot te enviará tu Chat ID automáticamente</p>'
'<p style="font-size:11px;color:#a1a1a6;margin:0">4. Pega ese número aquí arriba y guarda</p>'
'</div></div>'
        '<button onclick="guardarPerfil()" class="btn btn-primary">Guardar cambios</button>'
        '<div id="msg-perfil" style="margin-top:12px;font-size:13px;display:none"></div>'
        '</div>'

        # Cambiar contraseña
        '<div class="card" style="margin-bottom:16px">'
        '<h3 style="margin-bottom:16px">Cambiar contraseña</h3>'
        '<div class="form-group"><label>Contraseña actual</label>'
        '<input type="password" id="p-cur" class="form-input" placeholder="••••••••"></div>'
        '<div class="form-group"><label>Nueva contraseña</label>'
        '<input type="password" id="p-new" class="form-input" placeholder="Mínimo 6 caracteres"></div>'
        '<button onclick="cambiarPassword()" class="btn btn-secondary">Cambiar contraseña</button>'
        '<div id="msg-pw" style="margin-top:12px;font-size:13px;display:none"></div>'
        '</div>'

        '<script>'
        'async function guardarPerfil(){'
        '  var email=document.getElementById("p-email").value.trim();'
        '  var telegram=document.getElementById("p-telegram").value.trim();'
        '  var msg=document.getElementById("msg-perfil");'
        '  try{'
        '    var r=await fetch("/api/profile",{method:"PUT",headers:{"Content-Type":"application/json"},'
        '      body:JSON.stringify({email:email,telegram_chat_id:telegram})});'
        '    var d=await r.json();'
        '    msg.style.display="block";'
        '    if(d.ok){msg.style.color="#30d158";msg.textContent="✅ "+d.mensaje;}'
        '    else{msg.style.color="#ff453a";msg.textContent="❌ "+(d.error||"Error");}'
        '  }catch(e){msg.style.display="block";msg.style.color="#ff453a";msg.textContent="Error de conexión";}'
        '}'
        'async function cambiarPassword(){'
        '  var cur=document.getElementById("p-cur").value;'
        '  var nw=document.getElementById("p-new").value;'
        '  var msg=document.getElementById("msg-pw");'
        '  if(!cur||!nw){msg.style.display="block";msg.style.color="#ff453a";msg.textContent="Completa ambos campos";return;}'
        '  if(nw.length<6){msg.style.display="block";msg.style.color="#ff453a";msg.textContent="Mínimo 6 caracteres";return;}'
        '  try{'
        '    var r=await fetch("/api/profile",{method:"PUT",headers:{"Content-Type":"application/json"},'
        '      body:JSON.stringify({current_password:cur,new_password:nw})});'
        '    var d=await r.json();'
        '    msg.style.display="block";'
        '    if(d.ok){msg.style.color="#30d158";msg.textContent="✅ Contraseña actualizada";'
        '      document.getElementById("p-cur").value="";document.getElementById("p-new").value="";}'
        '    else{msg.style.color="#ff453a";msg.textContent="❌ "+(d.error||"Error");}'
        '  }catch(e){msg.style.display="block";msg.style.color="#ff453a";msg.textContent="Error de conexión";}'
        '}'
        '</script>'
        '</div>'
    )
    return pagina('Mi Perfil', contenido)

@app.route('/api/recolector', methods=['POST'])
def api_recolector():
    try: subprocess.run(["python","recolector.py"],check=False,timeout=120); return jsonify({'ok':True})
    except Exception as e: return jsonify({'ok':False,'error':str(e)})

@app.route('/api/ultima-actualizacion')
def api_ultima_actualizacion():
    try:
        mtime=os.path.getmtime("datos/macro/trm.parquet")
        hora=datetime.fromtimestamp(mtime).strftime("%d %b %Y · %I:%M %p")
        return jsonify({'timestamp':hora})
    except: return jsonify({'timestamp':'No disponible'})

# ============================================================
# MAIN
# ============================================================

if __name__=="__main__":
    print("="*55)
    print("🌐 DASHBOARD INICIANDO...")
    print("   http://localhost:5000")
    print("="*55)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)