"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getSeguimiento, registrarCompra, type SeguimientoData } from "@/lib/api";
import { GlassBackground } from "@/components/ui/glass-background";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowPanel } from "@/components/ui/glow-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PageIntro } from "@/components/ui/page-intro";

export default function SeguimientoPage() {
  const params  = useParams();
  const router  = useRouter();
  const archivo = params.archivo as string;

  const [data, setData]       = useState<SeguimientoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg]         = useState({ text: "", ok: false });

  // Campos del formulario
  const hoy = new Date().toISOString().slice(0, 10);
  const [activo, setActivo]         = useState("");
  const [fecha, setFecha]           = useState(hoy);
  const [montoUsd, setMontoUsd]     = useState("");
  const [fracciones, setFracciones] = useState("");

  useEffect(() => {
    getSeguimiento(archivo)
      .then(d => setData(d))
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [archivo, router]);

  async function registrar() {
    if (!activo || !montoUsd || !fracciones) {
      setMsg({ text: "Completa activo, monto y fracciones", ok: false });
      return;
    }
    try {
      const actualizado = await registrarCompra(archivo, {
        activo, fecha,
        monto_usd: parseFloat(montoUsd),
        fracciones: parseFloat(fracciones),
      });
      setData(actualizado);          // refresca con el estado nuevo
      setMsg({ text: `Compra de ${activo} registrada`, ok: true });
      setMontoUsd(""); setFracciones(""); setActivo("");
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  if (loading) return <div style={s.load}>Cargando...</div>;
  if (!data)   return <div style={s.load}>No se pudo cargar</div>;

  const sinComposicion = data.progreso.total === 0;

  return (
    <>
      
        {msg.text && (
          <div style={{ padding: "10px 14px", borderRadius: 10, marginBottom: 16, fontSize: 13,
            background: msg.ok ? "rgba(48,209,88,0.1)" : "rgba(255,69,58,0.1)",
            color: msg.ok ? "#30d158" : "#ff453a" }}>{msg.text}</div>
        )}
        <PageIntro
                       archivo={archivo}
                       texto="Registra tus inversiones reales —qué compraste, cuándo y a qué precio— para que el sistema calcule tu ganancia con datos verdaderos."
                     /> 
        {sinComposicion ? (
          <GlassPanel>
            <p style={{ color: "#a1a1a6", fontSize: 14 }}>
              Este portafolio aún no tiene una composición. Primero corre el <strong>Analista</strong> para generar la propuesta de activos, y luego podrás registrar tus compras aquí.
            </p>
          </GlassPanel>
        ) : (
          <>
            {/* Barra de progreso */}
            <GlassPanel>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                <span style={{ color: "#a1a1a6" }}>Progreso de entradas</span>
                <span style={{ color: "#0071e3", fontWeight: 600 }}>{data.progreso.entrados}/{data.progreso.total} activos</span>
              </div>
              <div style={{ background: "#1a1a1a", borderRadius: 980, height: 6, overflow: "hidden" }}>
                <div style={{ background: "#0071e3", height: "100%", width: `${data.progreso.pct}%`, transition: "width 0.6s ease" }} />
              </div>
              <div style={{ marginTop: 8, fontSize: "0.8rem", color: "#6e6e73" }}>{data.progreso.pct}% completado</div>
            </GlassPanel>

            {/* Pendientes */}
            {data.pendientes.length > 0 && (
              <GlassPanel>
                <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>Pendientes por entrar</h3>
                {data.pendientes.map(p => (
                  <div key={p.activo} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <div>
                      <strong>{p.activo}</strong>
                      <span style={{ color: "#6e6e73", fontSize: "0.8rem", marginLeft: 8 }}>{(p.peso * 100).toFixed(1)}% del portafolio</span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: "0.85rem", color: "#a1a1a6" }}>{p.precio_usd ? `$${p.precio_usd.toFixed(2)} USD` : "—"}</div>
                      <span style={{ fontSize: 11, color: "#e6b800" }}>PENDIENTE</span>
                    </div>
                  </div>
                ))}
              </GlassPanel>
            )}

            {/* Formulario de nueva compra */}
            <GlassPanel>
              <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>Registrar nueva compra</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
                <div>
                  <label style={{ fontSize: "0.85rem", color: "#a1a1a6" }}>Activo</label>
                  <select value={activo} onChange={e => setActivo(e.target.value)} style={{ background: "var(--bg-2)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--text)", padding: "8px 12px", borderRadius: 8 }}>
                    <option value="">Selecciona...</option>
                    {data.pendientes.map(p => <option key={p.activo} value={p.activo}>{p.activo} — pendiente</option>)}
                    {data.entrados.map(a => <option key={a} value={a}>{a} — agregar más</option>)}
                  </select>
                </div>
                <div>
                  <label style={s.label}>Fecha</label>
                  <input type="date" value={fecha} onChange={e => setFecha(e.target.value)} style={s.input} />
                </div>
                <div>
                  <label style={s.label}>Monto total pagado (USD)</label>
                  <input type="number" step="0.01" placeholder="Ej: 54.81" value={montoUsd} onChange={e => setMontoUsd(e.target.value)} style={s.input} />
                </div>
                <div>
                  <label style={s.label}>Fracciones compradas</label>
                  <input type="number" step="0.0001" placeholder="Ej: 0.2523" value={fracciones} onChange={e => setFracciones(e.target.value)} style={s.input} />
                </div>
              </div>
              <div style={{ padding: "10px 14px", background: "rgba(0,113,227,0.06)", border: "1px solid rgba(0,113,227,0.15)", borderRadius: 10, marginBottom: 14 }}>
                <p style={{ color: "#4da3ff", fontSize: 12, margin: 0 }}>El sistema calcula el precio por acción y convierte a COP con la TRM del día.</p>
              </div>
              <LiquidButton onClick={registrar} className="text-white font-semibold !px-10 !py-3">Registrar compra</LiquidButton>
            </GlassPanel>

            {/* Historial */}
            {data.aportes.length > 0 && (
              <GlassPanel>
                <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>Historial de compras</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead>
                      <tr style={{ color: "#6e6e73", textAlign: "left" }}>
                        <th style={s.th}>Fecha</th><th style={s.th}>Activo</th><th style={s.th}>USD</th>
                        <th style={s.th}>COP</th><th style={s.th}>Fracciones</th><th style={s.th}>Precio</th><th style={s.th}>TRM</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.aportes].reverse().map((a, i) => (
                        <tr key={i} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                          <td style={s.td}>{a.fecha}</td>
                          <td style={s.td}><strong>{a.activo}</strong></td>
                          <td style={s.td}>${a.monto_usd.toFixed(2)}</td>
                          <td style={s.td}>${a.monto_cop.toLocaleString()}</td>
                          <td style={s.td}>{a.fracciones.toFixed(6)}</td>
                          <td style={s.td}>${a.precio_usd.toFixed(4)}</td>
                          <td style={s.td}>${a.trm_dia.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </GlassPanel>
            )}
          </>
        )}
    </>
  );
}

const s: Record<string, React.CSSProperties> = {
  load:       { background: "var(--bg)", color: "var(--text-3)", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 },
  card:       { background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 14, padding: 20, marginBottom: 16 },
  h3:         { fontSize: "1rem", marginBottom: 12, color: "var(--text)" },
  label:      { display: "block", fontSize: 12, color: "var(--text-3)", marginBottom: 6 },
  input:      { background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 10, color: "var(--text)", fontSize: "0.9rem", padding: "9px 12px", width: "100%" },
  btnPrimary: { padding: "10px 20px", borderRadius: 980, fontSize: 13, cursor: "pointer", background: "#0071e3", color: "#fff", border: "none" },
  th:         { padding: "8px 10px", fontWeight: 500 },
  td:         { padding: "8px 10px", color: "var(--text)" },
};
