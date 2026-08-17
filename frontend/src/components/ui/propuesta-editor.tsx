"use client";
import { useState, useEffect, useRef } from "react";
import { GlowPanel } from "@/components/ui/glow-panel";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { ReporteTarjetas, type DatosReporte } from "@/components/ui/reporte-tarjetas";
import { useIsDemo, MENSAJE_DEMO } from "@/lib/useIsDemo";

export interface Propuesta {
  pesos: Record<string, number>;
  perfil: string;
  inversion: number;
  aporte_dca: number;
  frecuencia_meses: number;
  horizonte: number;
  archivo: string;
  advertencia?: string;
}

const COLORES = ["#0071e3", "#30d158", "#ff9f0a", "#bf5af2", "#ff453a", "#5ac8fa", "#ffd60a", "#64d2ff", "#ff375f", "#a2845e"];

const TRIVIA = [
  "La Bolsa de Nueva York (NYSE) nació en 1792 bajo un árbol de sicómoro en Wall Street. El acuerdo se llamó el «Buttonwood Agreement».",
  "El término «mercado alcista» (bull) viene de cómo el toro ataca: lanzando los cuernos hacia arriba. El oso (bear) golpea hacia abajo.",
  "Si hubieras invertido $1.000 en Apple en su salida a bolsa en 1980, hoy valdrían más de un millón de dólares.",
  "El «Flash Crash» de 2010 borró casi un billón de dólares del mercado en minutos… y se recuperó casi todo el mismo día.",
  "Warren Buffett compró su primera acción a los 11 años. Dice que fue «demasiado tarde».",
  "El índice S&P 500 no tiene 500 empresas exactas: a veces son 503, porque algunas compañías tienen varias clases de acciones.",
  "Holanda tuvo la primera bolsa moderna en 1602. También sufrió la primera burbuja: la «tulipomanía», donde un bulbo de tulipán llegó a costar más que una casa.",
  "El «efecto enero» es la tendencia histórica de que las acciones suban más en enero. Nadie se pone de acuerdo en por qué.",
  "El mercado pasa más tiempo subiendo que bajando, pero las caídas son más rápidas y memorables. Por eso dan más miedo de lo que deberían.",
  "El DCA (comprar montos fijos cada cierto tiempo) existe porque nadie —ni los expertos— sabe cuándo el mercado está en su punto más bajo.",
];

interface Props {
  propuesta: Propuesta;
  tieneInv: boolean;
  onAplicar: (tipo: "reemplazar" | "nuevo", pesos: Record<string, number>) => void;
  aplicando: boolean;
  msgEstado: string;
}

export function PropuestaEditor({ propuesta, tieneInv, onAplicar, aplicando, msgEstado }: Props) {
  const isDemo = useIsDemo();
  const [pesos, setPesos] = useState<Record<string, number>>(
    Object.fromEntries(Object.entries(propuesta.pesos).map(([k, v]) => [k, +(v * 100).toFixed(1)]))
  );
  const [nuevoTicker, setNuevoTicker] = useState("");
  const [nuevoPeso, setNuevoPeso] = useState("");
  const [tickerStatus, setTickerStatus] = useState("");
  const [agregando, setAgregando] = useState(false);

  const [datos, setDatos] = useState<DatosReporte | null>(null);
  const [notaNuevos, setNotaNuevos] = useState("");
  const [recalculando, setRecalculando] = useState(false);
  const [triviaIdx, setTriviaIdx] = useState(0);
  const triviaTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const total = Object.values(pesos).reduce((a, b) => a + b, 0);
  const sumaOk = Math.abs(total - 100) < 0.1;

  // Rota la trivia mientras recalcula
  useEffect(() => {
    if (recalculando) {
      setTriviaIdx(Math.floor(Math.random() * TRIVIA.length));
      triviaTimer.current = setInterval(() => {
        setTriviaIdx(i => (i + 1) % TRIVIA.length);
      }, 4000);
    } else if (triviaTimer.current) {
      clearInterval(triviaTimer.current);
    }
    return () => { if (triviaTimer.current) clearInterval(triviaTimer.current); };
  }, [recalculando]);

  // En demo el botón "Recalcular" está disabled, así que las proyecciones se
  // calculan solas una vez al montar → la propuesta se ve completa (solo lectura).
  const yaRecalculado = useRef(false);
  useEffect(() => {
    if (isDemo && sumaOk && !yaRecalculado.current) {
      yaRecalculado.current = true;
      recalcular();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, sumaOk]);

  function cambiarPeso(ticker: string, valor: string) {
    const num = parseFloat(valor);
    setPesos(p => ({ ...p, [ticker]: isNaN(num) ? 0 : num }));
  }

  function quitar(ticker: string) {
    setPesos(p => {
      const n = { ...p };
      delete n[ticker];
      return n;
    });
  }

  async function agregarActivo() {
    const tk = nuevoTicker.trim().toUpperCase();
    const peso = parseFloat(nuevoPeso);
    if (!tk) { setTickerStatus("Escribe un ticker"); return; }
    if (isNaN(peso) || peso <= 0) { setTickerStatus("Escribe un peso válido"); return; }
    if (pesos[tk] !== undefined) { setTickerStatus("Ese activo ya está en la lista"); return; }

    setAgregando(true);
    setTickerStatus("Verificando ticker...");
    try {
      const r = await fetch(`/api/verificar-ticker/${tk}`, { credentials: "include" });
      const d = await r.json();
      if (!d.valido) {
        setTickerStatus(`No se encontró "${tk}" en el mercado`);
        setAgregando(false);
        return;
      }
      if (d.es_nuevo) {
        setTickerStatus(`${d.nombre} encontrado ($${d.precio}). Descargando histórico...`);
        // Polling hasta que el histórico esté listo
        const resultado = await esperarTicker(tk);
        if (resultado === "timeout") {
          setTickerStatus(`${tk} agregado, pero su histórico aún se está descargando. El motor lo excluirá del cálculo hasta que esté disponible.`);
        } else if (resultado === "error") {
          setTickerStatus(`No se pudo descargar el histórico de ${tk}. Queda en la lista, pero el motor lo excluirá del cálculo hasta que haya datos válidos.`);
        } else {
          setTickerStatus(`${d.nombre} listo y agregado.`);
        }
      } else {
        setTickerStatus(`${d.nombre} agregado.`);
      }
      setPesos(p => ({ ...p, [tk]: peso }));
      setNuevoTicker("");
      setNuevoPeso("");
    } catch {
      setTickerStatus("Error verificando el ticker");
    } finally {
      setAgregando(false);
    }
  }

  async function esperarTicker(tk: string): Promise<"ok" | "error" | "timeout"> {
    for (let i = 0; i < 20; i++) {  // hasta ~40s
      await new Promise(res => setTimeout(res, 2000));
      try {
        const r = await fetch(`/api/ticker-listo/${tk}`, { credentials: "include" });
        const d = await r.json();
        if (d.listo) return d.exito ? "ok" : "error";
      } catch { /* sigue intentando */ }
    }
    return "timeout";
  }

  async function recalcular() {
    if (!sumaOk) return;
    setRecalculando(true);
    setDatos(null);
    setNotaNuevos("");
    try {
      const pesosDecimal = Object.fromEntries(Object.entries(pesos).map(([k, v]) => [k, v / 100]));
      const r = await fetch(`/api/recalcular-proyecciones/${propuesta.archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pesos: pesosDecimal, perfil: propuesta.perfil, inversion: propuesta.inversion,
          aporte_dca: propuesta.aporte_dca, frecuencia_meses: propuesta.frecuencia_meses,
          horizonte: propuesta.horizonte,
        }),
      });
      const d = await r.json();
      if (d.ok) {
        setDatos(d.datos ?? null);
        setNotaNuevos(d.nota_nuevos ?? "");
      } else {
        setDatos(null);
        setNotaNuevos(`Error: ${d.error}`);
      }
    } catch {
      setDatos(null);
      setNotaNuevos("Error de conexión al recalcular.");
    } finally {
      setRecalculando(false);
    }
  }

  function aplicar(tipo: "reemplazar" | "nuevo") {
    const pesosDecimal = Object.fromEntries(Object.entries(pesos).map(([k, v]) => [k, v / 100]));
    onAplicar(tipo, pesosDecimal);
  }

  const activos = Object.entries(pesos).sort((a, b) => b[1] - a[1]);

  return (
    <GlowPanel>
      <p style={{ color: "var(--text-3)", fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 4px" }}>
        Propuesta optimizada · {propuesta.perfil.toUpperCase()}
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 12, margin: "0 0 16px" }}>
        {isDemo ? MENSAJE_DEMO + " — el Analista es de solo lectura en esta cuenta." : "Edita los pesos, quita o agrega activos, y recalcula las proyecciones antes de aplicar."}
      </p>

      <p style={{ color: "#ff9f0a", fontSize: 11.5, lineHeight: 1.5, margin: "0 0 16px", padding: "9px 12px", background: "rgba(255,159,10,0.08)", border: "1px solid rgba(255,159,10,0.2)", borderRadius: 8 }}>
        Aviso: los pesos que edites aquí se calculan tal cual los dejes — no vuelven a pasar por el
        motor de selección (Sortino, correlación, cobertura sectorial) ni por HRP. Si quitas o
        cambias algo, la combinación ya no es necesariamente la que el motor recomendaría.
      </p>

      {/* Lista de activos editable */}
      {activos.map(([ticker, peso], idx) => {
        const color = COLORES[idx % COLORES.length];
        return (
          <div key={ticker} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderBottom: "1px solid var(--glass-border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, width: 92 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: color, flexShrink: 0 }} />
              <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.01em" }}>{ticker}</span>
            </div>
            <div style={{ flex: 1, background: "var(--bg-2)", borderRadius: 980, height: 7, overflow: "hidden" }}>
              <div style={{ background: color, height: "100%", width: `${Math.min(peso, 100)}%`, borderRadius: 980, transition: "width 0.3s ease" }} />
            </div>
            <input
              type="number" value={peso} min={0} max={100} step={0.1}
              onChange={e => cambiarPeso(ticker, e.target.value)}
              disabled={isDemo}
              style={{ width: 64, background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 6, padding: "4px 8px", color: "var(--text)", fontSize: 13, textAlign: "right", fontVariantNumeric: "tabular-nums" }}
            />
            <span style={{ color: "var(--text-3)", fontSize: 12 }}>%</span>
            <button onClick={() => quitar(ticker)} disabled={isDemo} title={isDemo ? MENSAJE_DEMO : undefined} style={{ background: "rgba(255,69,58,0.1)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 6, padding: "3px 9px", cursor: isDemo ? "default" : "pointer", color: "#ff453a", fontSize: 12, opacity: isDemo ? 0.5 : 1 }}>✕</button>
          </div>
        );
      })}

      {/* Total */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
        <span style={{ fontSize: 13, color: "var(--text-3)" }}>
          Total: <strong style={{ color: sumaOk ? "#30d158" : "#ff453a" }}>{total.toFixed(1)}%</strong>
        </span>
        {!sumaOk && <span style={{ fontSize: 11, color: "#ff453a" }}>Debe sumar 100% para recalcular o aplicar</span>}
      </div>

      {/* Agregar activo */}
      <GlassPanel style={{ marginTop: 14, marginBottom: 0, padding: 14 }}>
        <p style={{ color: "var(--text-3)", fontSize: 11, margin: "0 0 8px", textTransform: "uppercase", letterSpacing: "0.05em" }}>+ Agregar activo</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="text" value={nuevoTicker} placeholder="Ticker (ej: SCHD)"
            onChange={e => setNuevoTicker(e.target.value)}
            disabled={isDemo}
            style={{ width: 150, background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 6, padding: "6px 10px", color: "var(--text)", fontSize: 13 }}
          />
          <input
            type="number" value={nuevoPeso} placeholder="%" min={0} max={100} step={0.1}
            onChange={e => setNuevoPeso(e.target.value)}
            disabled={isDemo}
            style={{ width: 70, background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 6, padding: "6px 10px", color: "var(--text)", fontSize: 13, textAlign: "right" }}
          />
          <LiquidButton onClick={agregarActivo} disabled={agregando || isDemo} title={isDemo ? MENSAJE_DEMO : undefined} className="text-white font-semibold !px-5 !py-2">
            {agregando ? "..." : "Agregar"}
          </LiquidButton>
        </div>
        {tickerStatus && <p style={{ fontSize: 12, color: "var(--text-2)", margin: "8px 0 0" }}>{tickerStatus}</p>}
      </GlassPanel>

      {/* Recalcular proyecciones */}
      <div style={{ marginTop: 16 }}>
        <LiquidButton onClick={recalcular} disabled={recalculando || !sumaOk || isDemo} title={isDemo ? MENSAJE_DEMO : undefined} className="text-white font-semibold !px-8 !py-2.5">
          {recalculando ? "Calculando..." : "↻ Recalcular proyecciones"}
        </LiquidButton>
      </div>

      {/* Loading trivia mientras recalcula */}
      {recalculando && (
        <GlassPanel style={{ marginTop: 14, marginBottom: 0, padding: 16, textAlign: "center" }}>
          <p style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 8px" }}>¿Sabías que...?</p>
          <p style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.6, margin: 0, transition: "opacity 0.3s" }}>{TRIVIA[triviaIdx]}</p>
        </GlassPanel>
      )}

      {/* Resultado en tarjetas */}
      {datos && !recalculando && <ReporteTarjetas datos={datos} notaNuevos={notaNuevos} advertenciaCategoria={propuesta.advertencia} />}

      {/* Resumen + aplicar */}
      <div style={{ marginTop: 16, display: "flex", gap: 16, fontSize: 12, color: "var(--text-3)", flexWrap: "wrap", paddingTop: 12, borderTop: "1px solid var(--glass-border)" }}>
        <span>Inversión: <strong style={{ color: "var(--text)" }}>${propuesta.inversion.toLocaleString("en-US")} COP</strong></span>
        {propuesta.aporte_dca > 0 && <span>DCA: <strong style={{ color: "var(--text)" }}>${propuesta.aporte_dca.toLocaleString("en-US")} COP</strong></span>}
        <span>Horizonte: <strong style={{ color: "var(--text)" }}>{propuesta.horizonte} años</strong></span>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 10, flexWrap: "wrap" }}>
        {!tieneInv && (
          <LiquidButton onClick={() => aplicar("reemplazar")} disabled={aplicando || !sumaOk || isDemo} title={isDemo ? MENSAJE_DEMO : undefined} className="text-white font-semibold !px-8 !py-3">
            {aplicando ? "Aplicando..." : "Aplicar a este portafolio"}
          </LiquidButton>
        )}
        <LiquidButton onClick={() => aplicar("nuevo")} disabled={aplicando || !sumaOk || isDemo} title={isDemo ? MENSAJE_DEMO : undefined} className="text-white font-semibold !px-8 !py-3">
          {aplicando ? "Aplicando..." : "Crear portafolio adicional"}
        </LiquidButton>
      </div>

      {msgEstado && <p style={{ marginTop: 12, fontSize: 13, color: msgEstado.startsWith("Error") ? "#ff453a" : "#30d158" }}>{msgEstado}</p>}
    </GlowPanel>
  );
}