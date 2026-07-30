"use client";
import { crearPortafolio, getPortafolios, authMe } from "@/lib/api";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { LogoMark } from "@/components/ui/logo";

interface EscenaProps { onReady: () => void }

const useReady = (onReady: () => void, ms: number) => {
  useEffect(() => { const t = setTimeout(onReady, ms); return () => clearTimeout(t); }, [onReady]);
};
const useShow = (delay = 100) => {
  const [show, setShow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setShow(true), delay); return () => clearTimeout(t); }, [delay]);
  return show;
};

// ── Atom: logo animado que narra (flota + ondas) ─────────────
function AtomGuia({ narrando }: { narrando: boolean }) {
  return (
    <div style={{ position: "relative", width: 46, height: 46, flexShrink: 0 }}>
      {narrando && [0, 1, 2].map(i => (
        <span key={i} style={{ position: "absolute", inset: 4, borderRadius: "50%", border: "1.5px solid rgba(0,113,227,0.4)", animation: `atom-wave 2.1s ease-out ${i * 0.6}s infinite` }} />
      ))}
      <div style={{ animation: "atom-float 3s ease-in-out infinite", position: "relative" }}>
        <LogoMark size={46} />
      </div>
      <style>{`
        @keyframes atom-wave { 0% { transform: scale(0.9); opacity: 0.7; } 100% { transform: scale(1.9); opacity: 0; } }
        @keyframes atom-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
      `}</style>
    </div>
  );
}

// ── 1. Filosofía: el tiempo hace crecer el dinero ────────────
function EscenaFilosofia({ onReady }: EscenaProps) {
  const show = useShow();
  useReady(onReady, 2200);
  return (
    <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 16, padding: 25 }}>
      <p style={{ fontSize: 9, color: "var(--text-3)", margin: "0 0 12px", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "justify"}}>$100 al mes · el poder del tiempo</p>
      <svg viewBox="0 0 280 130" style={{ width: "100%", height: 180 }}>
        <defs>
          <linearGradient id="grow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(48,209,88,0.35)" />
            <stop offset="100%" stop-color="rgba(48,209,88,0)" />
          </linearGradient>
        </defs>
        {/* baseline */}
        <line x1="0" y1="100" x2="280" y2="100" stroke="var(--glass-border)" strokeWidth="1" />
        {/* área */}
        <path d="M0,98 C60,96 110,88 160,66 C210,44 250,20 280,8 L280,100 L0,100 Z" fill="url(#grow)" style={{ opacity: show ? 1 : 0, transition: "opacity 1s 0.6s" }} />
        {/* línea */}
        <path d="M0,98 C60,96 110,88 160,66 C210,44 250,20 280,8" fill="none" stroke="#30d158" strokeWidth="2.5" strokeDasharray="420" strokeDashoffset={show ? 0 : 420} style={{ transition: "stroke-dashoffset 1.8s ease 0.3s" }} />
        {/* punto final */}
        <circle cx="280" cy="8" r="5" fill="#30d158" style={{ opacity: show ? 1 : 0, transition: "opacity 0.4s 1.8s" }} />
        {/* años */}
        {["Año 1", "Año 15", "Año 30"].map((t, i) => (
          <text key={t} x={i * 130 + 8} y="112" fontSize="8" fill="var(--text-3)" style={{ opacity: show ? 1 : 0, transition: `opacity 0.5s ${1 + i * 0.2}s` }}>{t}</text>
        ))}
      </svg>
      <p style={{ fontSize: 11, color: "#30d158", textAlign: "center", margin: "20px 0 0", opacity: show ? 1 : 0, transition: "opacity 0.6s 1.6s" }}>
        El tiempo trabaja gratis y nunca renuncia
      </p>
    </div>
  );
}

// ── 2. Analista: chat → propuesta → proyecciones ─────────────
function EscenaAnalista({ onReady }: EscenaProps) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const ts = [setTimeout(() => setStep(1), 400), setTimeout(() => setStep(2), 1100), setTimeout(() => setStep(3), 1800), setTimeout(() => setStep(4), 2600)];
    return () => ts.forEach(clearTimeout);
  }, []);
  useReady(onReady, 3200);
  const activos = [
    { t: "VTI", w: "32%", c: "#0071e3" }, { t: "AAPL", w: "24%", c: "#30d158" },
    { t: "MSFT", w: "22%", c: "#ff9f0a" }, { t: "GOOGL", w: "22%", c: "#bf5af2" },
  ];
  const proy = [
    { l: "Pesimista", v: "$8.2M", c: "#ff453a" }, { l: "Base", v: "$14.6M", c: "#0071e3" }, { l: "Optimista", v: "$23.1M", c: "#30d158" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {[{ yo: false, t: "¿Qué quieres lograr?" }, { yo: true, t: "Crecer mi plata a largo plazo, sin estrés" }].map((m, i) => (
        <div key={i} style={{ display: "flex", justifyContent: m.yo ? "flex-end" : "flex-start", opacity: step > i ? 1 : 0, transform: step > i ? "translateY(0)" : "translateY(8px)", transition: "all 0.4s" }}>
          <div style={{ maxWidth: "76%", fontSize: 12.5, padding: "9px 13px", borderRadius: m.yo ? "14px 14px 4px 14px" : "14px 14px 14px 4px", background: m.yo ? "#0071e3" : "var(--glass)", color: m.yo ? "#fff" : "var(--text)", border: m.yo ? "none" : "1px solid var(--glass-border)" }}>{m.t}</div>
        </div>
      ))}
      {/* propuesta */}
      <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: 14, opacity: step >= 3 ? 1 : 0, transform: step >= 3 ? "translateY(0)" : "translateY(10px)", transition: "all 0.5s" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <p style={{ fontSize: 9, color: "var(--text-3)", margin: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>Propuesta · editable</p>
          <span style={{ fontSize: 9, color: "#0071e3", padding: "2px 8px", borderRadius: 980, background: "rgba(0,113,227,0.12)", border: "1px solid rgba(0,113,227,0.25)" }}>↻ recalcular</span>
        </div>
        {activos.map((a, i) => (
          <div key={a.t} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
            <span style={{ width: 44, fontSize: 11, fontWeight: 600 }}>{a.t}</span>
            <div style={{ flex: 1, height: 6, background: "var(--bg-2)", borderRadius: 980, overflow: "hidden" }}>
              <div style={{ height: "100%", width: step >= 3 ? a.w : "0%", background: a.c, borderRadius: 980, transition: `width 0.9s ease ${0.2 + i * 0.1}s` }} />
            </div>
            <span style={{ width: 32, fontSize: 11, textAlign: "right", color: "var(--text-3)" }}>{a.w}</span>
          </div>
        ))}
      </div>
      {/* proyecciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, opacity: step >= 4 ? 1 : 0, transform: step >= 4 ? "translateY(0)" : "translateY(10px)", transition: "all 0.5s" }}>
        {proy.map(p => (
          <div key={p.l} style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 10, padding: "10px 8px", textAlign: "center" }}>
            <p style={{ fontSize: 8, color: "var(--text-3)", margin: "0 0 4px", textTransform: "uppercase" }}>{p.l}</p>
            <p style={{ fontSize: 14, fontWeight: 600, margin: 0, color: p.c }}>{p.v}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 3. Dashboard: macro + TRM + composición ──────────────────
function EscenaDashboard({ onReady }: EscenaProps) {
  const show = useShow();
  useReady(onReady, 2600);
  const macro = [
    { l: "TRM hoy", v: "$4.012", c: "#0071e3" }, { l: "Inflación", v: "6.6%", c: "#ff9f0a" },
    { l: "T-Bond", v: "4.0%", c: "#d13058" }, { l: "Tu rentab.", v: "+24.6%", c: "#30d158" },
  ];
  const comp = [{ t: "VTI", w: "32%", c: "#0071e3" }, { t: "AAPL", w: "22%", c: "#30d158" }, { t: "MSFT", w: "26%", c: "#ff9f0a" }, { t: "LLY", w: "20%", c: "#ff0a53" }];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 7 }}>
        {macro.map((m, i) => (
          <div key={m.l} style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 10, padding: "12px 8px", opacity: show ? 1 : 0, transform: show ? "translateY(0)" : "translateY(12px)", transition: `all 0.5s ${i * 0.1}s` }}>
            <p style={{ fontSize: 10, color: "var(--text-3)", margin: "0 0 4px", textTransform: "uppercase", letterSpacing: "0.04em" }}>{m.l}</p>
            <p style={{ fontSize: 15, fontWeight: 600, margin: 0, color: m.c }}>{m.v}</p>
          </div>
        ))}
      </div>
      <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: 30, opacity: show ? 1 : 0, transition: "opacity 0.5s 0.4s" }}>
        <p style={{ fontSize: 9, color: "var(--text-3)", margin: "0 0 8px", textTransform: "uppercase", letterSpacing: "0.05em" }}>TRM · últimos 90 días</p>
        <svg viewBox="0 0 260 80" style={{ width: "100%", height: 120 }}>
          <path d="M0,40 L26,35 L52,38 L78,28 L104,30 L130,20 L156,24 L182,12 L208,16 L234,9 L260,6" fill="none" stroke="#0071e3" strokeWidth="2" strokeDasharray="420" strokeDashoffset={show ? 0 : 420} style={{ transition: "stroke-dashoffset 1.7s ease 0.5s" }} />
          <text x="0" y="78" fontSize="7" fill="var(--text-3)">Mar</text>
          <text x="52" y="78" fontSize="7" fill="var(--text-3)"textAnchor="middle">Abr</text>
          <text x="104" y="78" fontSize="7" fill="var(--text-3)"textAnchor="end">May</text>
          <text x="156" y="78" fontSize="7" fill="var(--text-3)"textAnchor="end">Jun</text>
          <text x="208" y="78" fontSize="7" fill="var(--text-3)"textAnchor="end">Jul</text>          
          <text x="260" y="78" fontSize="7" fill="var(--text-3)"textAnchor="end">Ago</text>
          <line x1="0" y1="46" x2="260" y2="46" stroke="var(--glass-border)" strokeWidth="1"/>
        </svg>
      </div>
      <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: 14, opacity: show ? 1 : 0, transition: "opacity 0.5s 0.6s" }}>
        <p style={{ fontSize: 10, color: "var(--text-3)", margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Tu composición</p>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ flex: 1 }}>
        {comp.map((a, i) => (
          <div key={a.t} style={{ display: "flex", alignItems: "center", gap: 15, marginBottom: 7 }}>
            <span style={{ width: 44, fontSize: 15, fontWeight: 600 }}>{a.t}</span>
            <div style={{ flex: 1, height: 6, background: "var(--bg-2)", borderRadius: 980, overflow: "hidden" }}>
              <div style={{ height: "100%", width: show ? a.w : "0%", background: a.c, borderRadius: 980, transition: `width 0.9s ease ${0.7 + i * 0.1}s` }} />
            </div>
          </div>
        ))}
        </div>
          <svg viewBox="0 0 80 80" style={{ width: 80, height: 80, flexShrink: 0 }}>
            <circle cx="40" cy="40" r="30" fill="none" stroke="#0071e3" strokeWidth="12" strokeDasharray="60.32 188.5" strokeDashoffset="0" transform="rotate(-90 40 40)" />
            <circle cx="40" cy="40" r="30" fill="none" stroke="#30d158" strokeWidth="12" strokeDasharray="41.47 188.5" strokeDashoffset="-60.32" transform="rotate(-90 40 40)" />
            <circle cx="40" cy="40" r="30" fill="none" stroke="#ff9f0a" strokeWidth="12" strokeDasharray="49.01 188.5" strokeDashoffset="-101.79" transform="rotate(-90 40 40)" />
            <circle cx="40" cy="40" r="30" fill="none" stroke="#ff0a53" strokeWidth="12" strokeDasharray="37.7 188.5" strokeDashoffset="-150.8" transform="rotate(-90 40 40)" />
          </svg>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: "10px 14px", marginTop: 14 }}>
          <LogoMark size={26} />
          <p style={{ fontSize: 11.5, color: "var(--text-2)", margin: 0, lineHeight: 1.5 }}>
            Tu inversión está concentrada en <span style={{ color: "#0071e3", fontWeight: 600 }}>tecnología</span>
          </p>
        </div>
      </div>
    </div>
  );
}

// ── 4. Monitor: señales con precios que cambian ──────────────
function EscenaMonitor({ onReady }: EscenaProps) {
  const show = useShow();
  const [tick, setTick] = useState(0);
  const [fase, setFase] = useState(0);
  useEffect(() => { const iv = setInterval(() => setTick(t => t + 1), 900); return () => clearInterval(iv); }, []);
  useEffect(() => {
    const ts = [
      setTimeout(() => setFase(1), 1500),
      setTimeout(() => setFase(2), 4000),
      setTimeout(() => setFase(3), 6500),
      setTimeout(() => setFase(4), 9000),
    ];
    return () => ts.forEach(clearTimeout);
  }, []);
  useReady(onReady, 9200);
  const base = [
    { t: "AAPL", p: 182.4, s: "COMPRAR", c: "#30d158", rsi: 0.7 },
    { t: "MSFT", p: 378.1, s: "ESPERAR", c: "#ffd60a", rsi: 0.5 },
    { t: "GOOGL", p: 141.8, s: "COMPRAR", c: "#30d158", rsi: 0.8 },
    { t: "TSLA", p: 242.6, s: "NO ENTRAR", c: "#ff453a", rsi: 0.3 },
    { t: "NVDA", p: 210.6, s: "ESPERAR", c: "#ffd60a", rsi: 0.5 },
    { t: "VTI", p: 369.99, s: "NO ENTRAR", c: "#ff453a", rsi: 0.2 },
  ];
  // Guía de Atom: orden de explicación
  const guia = [
    { s: "COMPRAR", label: "Comprar", c: "#30d158", txt: "Señal de entrada. El precio y los indicadores (medias móviles, RSI, volumen) se alinean a tu favor — buen momento para considerar entrar." },
    { s: "ESPERAR", label: "Esperar", c: "#ffd60a", txt: "Zona neutral. Las señales están mixtas: ni claramente buenas ni malas. Mejor esperar a que el panorama se aclare." },
    { s: "NO ENTRAR", label: "No entrar", c: "#ff453a", txt: "Señal de cautela. Los indicadores sugieren debilidad o sobrevaloración — no es buen momento para entrar." },
  ];
  const enSecuencia = fase >= 1 && fase <= 3;
  const actual = enSecuencia ? guia[fase - 1] : null;
  const resumen = fase >= 4;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#30d158", animation: "pulse-dot 1.6s infinite" }} />
        <span style={{ fontSize: 10, color: "var(--text-3)" }}>Mercado abierto · precios en vivo</span>
      </div>
      {base.map((r, i) => {
        const delta = ((tick * 7 + i * 13) % 10 - 5) / 100;
        const precio = (r.p + delta).toFixed(2);
        const up = delta >= 0;
        const activo = actual && r.s === actual.s;        // ¿esta fila es del veredicto que se explica?
        const atenuado = actual && !activo;               // las demás se atenúan
        return (
          <div key={r.t} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            background: "var(--glass)",
            border: `1px solid ${activo ? r.c : "var(--glass-border)"}`,
            borderRadius: 10, padding: "10px 14px",
            opacity: show ? (atenuado ? 0.35 : 1) : 0,
            transform: show ? "translateX(0)" : "translateX(-12px)",
            boxShadow: activo ? `0 0 0 3px ${r.c}22` : "none",
            transition: `all 0.45s ${show && fase === 0 ? i * 0.12 : 0}s`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 600, fontFamily: "monospace", width: 46 }}>{r.t}</span>
              <span style={{ fontSize: 11, color: up ? "#30d158" : "#ff453a", fontFamily: "monospace", transition: "color 0.3s" }}>${precio}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 36, height: 4, background: "var(--bg-2)", borderRadius: 980, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${r.rsi * 100}%`, background: r.c, borderRadius: 980 }} />
              </div>
              <span style={{ fontSize: 8, color: r.c, fontWeight: 600, padding: "4px 1px", borderRadius: 980, background: `${r.c}1f`, border: `1px solid ${r.c}33`, width: 56, textAlign: "center" }}>{r.s}</span>
            </div>
          </div>
        );
      })}
      {/* Explicación de Atom */}
      <AnimatePresence mode="wait">
        {actual && (
          <motion.div
            key={fase}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.4 }}
            style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "var(--bg-2)", border: `1px solid ${actual.c}40`, borderRadius: 12, padding: "10px 14px", marginTop: 4 }}
          >
            <LogoMark size={24} />
            <div>
              <p style={{ fontSize: 11, fontWeight: 600, margin: "0 0 3px", color: actual.c }}>{actual.label}</p>
              <p style={{ fontSize: 11.5, color: "var(--text-2)", margin: 0, lineHeight: 1.5 }}>{actual.txt}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {/* Resumen final: los tres juntos */}
      <AnimatePresence>
        {resumen && (
          <motion.div
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <LogoMark size={22} />
              <span style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>En resumen</span>
            </div>
            {guia.map(g => (
              <div key={g.s} style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "var(--bg-2)", border: `1px solid ${g.c}40`, borderRadius: 10, padding: "9px 12px" }}>
                <span style={{ fontSize: 10, color: g.c, fontWeight: 600, padding: "3px 9px", borderRadius: 980, background: `${g.c}1f`, border: `1px solid ${g.c}33`, whiteSpace: "nowrap", flexShrink: 0 }}>{g.label}</span>
                <p style={{ fontSize: 11, color: "var(--text-2)", margin: 0, lineHeight: 1.45 }}>{g.txt}</p>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <style>{`@keyframes pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
    </div>
  );
}

// ── 5. Seguimiento: entrados/pendientes + transacciones + form ─
function EscenaSeguimiento({ onReady }: EscenaProps) {
  const show = useShow();
  useReady(onReady, 2400);
  const activos = [{ t: "AAPL", e: true }, { t: "MSFT", e: true }, { t: "GOOGL", e: false }];
  const txs = [{ t: "AAPL", d: "12 jun", m: "$54.81" }, { t: "MSFT", d: "08 jun", m: "$80.00" }, { t: "LLY", d: "10 jun", m: "$20.00" }, { t: "NVDA", d: "10 jun", m: "$50.00" }];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {activos.map((a, i) => (
          <div key={a.t} style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 10, padding: "10px 12px", opacity: show ? 1 : 0, transform: show ? "translateY(0)" : "translateY(10px)", transition: `all 0.45s ${i * 0.1}s` }}>
            <p style={{ fontSize: 12, fontWeight: 600, margin: "0 0 4px" }}>{a.t}</p>
            <span style={{ fontSize: 9, color: a.e ? "#30d158" : "#ffd60a" }}>● {a.e ? "Entrado" : "Pendiente"}</span>
          </div>
        ))}
      </div>
      <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: 14, opacity: show ? 1 : 0, transition: "opacity 0.5s 0.35s" }}>
        <p style={{ fontSize: 9, color: "var(--text-3)", margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Tus transacciones</p>
        {txs.map((tx, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: i < txs.length - 1 ? "1px solid var(--glass-border)" : "none", fontSize: 12 }}>
            <span style={{ fontWeight: 600 }}>{tx.t}</span>
            <span style={{ color: "var(--text-3)" }}>{tx.d}</span>
            <span style={{ color: "#30d158" }}>{tx.m}</span>
          </div>
        ))}
      </div>
      {/* form mock */}
      <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: 14, opacity: show ? 1 : 0, transition: "opacity 0.5s 0.6s" }}>
        <p style={{ fontSize: 9, color: "var(--text-3)", margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Registrar compra</p>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 8.5, color: "var(--text-3)", margin: "0 0 4px" }}>Valor en USD</p>
            <div style={{ background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "var(--text-2)" }}>$80.00</div>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 8.5, color: "var(--text-3)", margin: "0 0 4px" }}>Acción</p>
            <div style={{ background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "var(--text-2)" }}>AAPL</div>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 8.5, color: "var(--text-3)", margin: "0 0 4px" }}>Fecha</p>
            <div style={{ background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "var(--text-2)" }}>12 jun</div>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 8.5, color: "var(--text-3)", margin: "0 0 4px" }}>Cantidad:</p>
            <div style={{ background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "var(--text-2)" }}>0.8</div>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <div style={{ background: "#0071e3", borderRadius: 8, padding: "8px 14px", fontSize: 11, color: "#fff", fontWeight: 500 }}>+ Añadir</div>
          </div>
        </div>
        {/* Nota de Atom */}
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 10, padding: "9px 12px" }}>
          <LogoMark size={22} />
          <p style={{ fontSize: 11, color: "var(--text-2)", margin: 0, lineHeight: 1.5 }}>
            Atom lleva por ti las <span style={{ color: "#0071e3", fontWeight: 600 }}>transacciones ejecutadas</span> , y gracias a su perfecto orden y organización, nunca olvidará una compra. Recuerda que puedes adquirir acciones completas o fracciones.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── 6. Asistente: la casa de Atom ────────────────────────────
function EscenaAsistente({ onReady }: EscenaProps) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const ts = [setTimeout(() => setStep(1), 400), setTimeout(() => setStep(2), 1300)];
    return () => ts.forEach(clearTimeout);
  }, []);
  useReady(onReady, 2400);
  const msgs = [
    { yo: true, t: "¿Cómo va mi portafolio hoy?" },
    { yo: false, t: "Vas +18% real este mes. Y tranquilo: las caídas son parte del juego, lo que cuenta es el largo plazo." },
  ];
  return (
    <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 16, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--glass-border)" }}>
        <LogoMark size={26} />
        <div>
          <p style={{ fontSize: 13, fontWeight: 600, margin: 0 }}>Atom</p>
          <p style={{ fontSize: 10, color: "#30d158", margin: 0 }}>● en línea</p>
        </div>
      </div>
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10, minHeight: 120 }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.yo ? "flex-end" : "flex-start", opacity: step > i ? 1 : 0, transform: step > i ? "translateY(0)" : "translateY(8px)", transition: "all 0.4s" }}>
            <div style={{ maxWidth: "80%", fontSize: 12.5, padding: "9px 13px", borderRadius: m.yo ? "14px 14px 4px 14px" : "14px 14px 14px 4px", background: m.yo ? "#0071e3" : "var(--bg-2)", color: m.yo ? "#fff" : "var(--text)", border: m.yo ? "none" : "1px solid var(--glass-border)", lineHeight: 1.5 }}>{m.t}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, padding: "0 16px 16px" }}>
        <div style={{ flex: 1, background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 980, padding: "8px 14px", fontSize: 11, color: "var(--text-3)" }}>Pregúntale lo que sea a Atom…</div>
      </div>
    </div>
  );
}

interface Paso { eyebrow: string; titulo: string; narracion: string; Escena: React.ComponentType<EscenaProps> }

const PASOS: Paso[] = [
  { eyebrow: "Bienvenido", titulo: "Invertir no es solo para expertos", narracion: "Todo lo que vale la pena asusta al principio, e invertir no es la excepción. Pero no se trata de cuánta plata tienes hoy, sino de cuánto tiempo le das: el tiempo convierte lo pequeño en grande. Solo pide paciencia y un poco de valentía. \n\ A veces, un solo momento de valentía lo cambia todo.", Escena: EscenaFilosofia },
  { eyebrow: "El Analista", titulo: "Conversa y arma tu portafolio", narracion: "Le cuentas en cristiano qué quieres lograr y Atom arma una propuesta de portafolio a tu medida. ¿No te convence? Cambias los pesos, agregas o quitas activos y recalcula las proyecciones al instante. \n\ Y tranquilo, no hay preguntas tontas: queda entre tú y la IA, que no tiene grupo de chismes.", Escena: EscenaAnalista },
  { eyebrow: "El Dashboard", titulo: "Tu sala de control", narracion: "Tu sala de control: la TRM de hoy y su gráfica histórica, los indicadores del mercado y tu composición, todo de un vistazo. Si vas ganando o perdiendo solo lo saben tú y Atom (y Atom no habla). ¿Tienes varios portafolios? Saltas entre ellos sin perderte.", Escena: EscenaDashboard },
  { eyebrow: "El Monitor", titulo: "Un vigía que nunca duerme", narracion: "Atom vigila tus activos leyendo medias móviles, RSI y volumen, y los traduce a un semáforo: verde para entrar, amarillo para esperar, rojo para frenar. \n\ Si te animas, le das tu Telegram y te avisa de una buena entrada. Eso sí: no escribe a medianoche ni manda mensajes coquetos. Trabaja para ti, sin sueldo y sin sentimientos.", Escena: EscenaMonitor },
  { eyebrow: "El Seguimiento", titulo: "Tu contador de bolsillo", narracion: "Registras cuánto invertiste en dólares y Atom registra cuántas acciones compraste — fracciones incluidas — con el precio real del momento. Lleva la cuenta de todo, para que después rías por la ganga que pillaste o llores por haber comprado en el máximo histórico justo antes de la caída. Sí: histórico e histérico.", Escena: EscenaSeguimiento },
  { eyebrow: "El Asistente", titulo: "La casa de Atom", narracion: "Aquí vive Atom, y su casa es tu casa. Pregúntale lo que sea y te traduce tu portafolio a español de humano.\n\ Te da contexto de la economía y, como buen psicólogo financiero, te baja las pulsaciones cuando el mercado hace de las suyas. Con esta familia, tú y tus inversiones nunca están solas. ¿Empezamos el viaje?", Escena: EscenaAsistente },
];

export default function BienvenidaPage() {
  const router = useRouter();
  const [paso, setPaso] = useState(0);
  const [dir, setDir] = useState(1);
  const [ready, setReady] = useState(false);
  const [creando, setCreando] = useState(false);

  const esUltimo = paso === PASOS.length - 1;
  const actual = PASOS[paso];
  const Escena = actual.Escena;

  useEffect(() => { setReady(false); }, [paso]);

  async function siguiente() {
    if (!ready || creando) return;
    if (!esUltimo) { setDir(1); setPaso(p => p + 1); return; }

    // Último paso: crear portafolio borrador y entrar a su Analista
    setCreando(true);
    try {
      const me = await authMe();
      await crearPortafolio({
        nombre: "Mi primer portafolio",
        propietario: me.username,
        perfil: "moderado",
        inversion: 0,
      });
      const { portafolios } = await getPortafolios();
      const nuevo = portafolios.find(p => p.nombre === "Mi primer portafolio");
      if (nuevo) {
        router.push(`/portafolio/${nuevo.archivo}/analista`);
      } else {
        router.push("/");  // respaldo si no se encuentra
      }
    } catch {
      router.push("/");  // respaldo si algo falla
    }
  }
  function atras() { setDir(-1); setPaso(p => Math.max(0, p - 1)); }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", position: "relative", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", justifyContent: "flex-end", padding: "20px 24px", maxWidth: 560, margin: "0 auto", width: "100%" }}>
        {!esUltimo && (
          <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: "var(--text-3)", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Saltar</button>
        )}
      </div>

      <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column", textAlign: "justify", padding: "0 26px", maxWidth: 540, margin: "0 auto", width: "100%" }}>
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div key={paso} custom={dir} initial={{ opacity: 0, x: dir * 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: dir * -40 }} transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}>
            {/* Atom + encabezado */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 14 }}>
              <AtomGuia narrando={!ready} />
              <div>
                <p style={{ fontSize: 15, color: "#4da3ff", textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 6px", fontWeight:600}}>{actual.eyebrow}</p>
                <h1 style={{ fontSize: "1.55rem", fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.15, margin: 0 }}>{actual.titulo}</h1>
              </div>
            </div>
            <p style={{ fontSize: "0.92rem", color: "var(--text-3)", lineHeight: 1.65, margin: "0 0 22px", whiteSpace: "pre-line" }}>{actual.narracion}</p>
            <Escena onReady={() => setReady(true)} />
          </motion.div>
        </AnimatePresence>
      </div>

      <div style={{ position: "relative", zIndex: 1, padding: 24, maxWidth: 540, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", gap: 6 }}>
            {PASOS.map((_, i) => (
              <div key={i} style={{ width: i === paso ? 24 : 8, height: 8, borderRadius: 980, background: i === paso ? "#0071e3" : "var(--glass-border)", transition: "all 0.3s ease" }} />
            ))}
          </div>
          <div style={{ flex: 1 }} />
          {paso > 0 && (
            <button onClick={atras} style={{ padding: "11px 20px", borderRadius: 12, background: "var(--glass)", border: "1px solid var(--glass-border)", color: "var(--text-2)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>Atrás</button>
          )}
          <button onClick={siguiente} disabled={!ready || creando} style={{ padding: "11px 24px", borderRadius: 12, border: "none", fontSize: 14, fontWeight: 500, fontFamily: "inherit", background: (ready && !creando) ? "#0071e3" : "var(--glass)", color: (ready && !creando) ? "#fff" : "var(--text-3)", cursor: (ready && !creando) ? "pointer" : "not-allowed", transition: "all 0.4s" }}>
            {creando ? "Creando tu espacio…" : esUltimo ? "Empezar mi viaje →" : "Siguiente"}
          </button>
        </div>
      </div>
    </div>
  );
}