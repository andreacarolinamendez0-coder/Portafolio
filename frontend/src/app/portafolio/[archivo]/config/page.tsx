"use client";
import { GlassBackground } from "@/components/ui/glass-background";
import { GlassPanel } from "@/components/ui/glass-panel";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getConfig, updateConfig, activarPortafolio, getPortafolios, eliminarCuenta } from "@/lib/api";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { GlowPanel } from "@/components/ui/glow-panel";
import { PageIntro } from "@/components/ui/page-intro";
import { desactivarPortafolio } from "@/lib/api";
import { eliminarPortafolio } from "@/lib/api";
import { DialogoUltimoPortafolio } from "@/components/ui/dialogo-ultimo-portafolio";



const DIVISAS = [
  { code: "USD", label: "Dólar estadounidense", symbol: "US$" },
  { code: "EUR", label: "Euro", symbol: "€" },
  { code: "COP", label: "Peso colombiano", symbol: "COL$" },
];

export default function ConfigPage() {
  const params  = useParams();
  const router  = useRouter();
  const archivo = params.archivo as string;

  const [nombre, setNombre]   = useState("");
  const [activo, setActivo]   = useState(false);
  const [divisa, setDivisa]   = useState("USD");
  const [msg, setMsg]         = useState({ text: "", ok: false });
  const [loading, setLoading] = useState(true);
  const [borrando, setBorrando] = useState(false);

  const [dialogoUltimo, setDialogoUltimo] = useState(false);

  useEffect(() => {
    getConfig(archivo)
      .then(d => { setNombre(d.nombre); setActivo(d.activo); setDivisa(d.divisa); })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [archivo, router]);

  async function guardarDivisa(nueva: string) {
    setDivisa(nueva); // actualiza la selección al instante
    try {
      const res = await updateConfig(archivo, { divisa: nueva });
      setMsg({ text: res.mensaje, ok: true });
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

    async function guardarNombre() {
    const limpio = nombre.trim();
    if (!limpio) { setMsg({ text: "El nombre no puede estar vacío", ok: false }); return; }
    try {
      const res = await updateConfig(archivo, { nombre: limpio });
      window.dispatchEvent(new CustomEvent("portafolio-renombrado", { detail: { archivo, nombre: limpio } }));
      setMsg({ text: res.mensaje ?? "Nombre actualizado", ok: true });
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  async function eliminar() {
    const { portafolios } = await getPortafolios();
    if (portafolios.length === 1) { setDialogoUltimo(true); return; }   // único → diálogo de Atom
    if (!confirm(`¿Eliminar el portafolio "${nombre}"?\n\nSe borra junto con todo su historial. Esto no se puede deshacer.`)) return;
    setBorrando(true);
    try {
      const r = await eliminarPortafolio(archivo);
      if (r.ok) {
        router.push("/");
      } else {
        setMsg({ text: r.error ?? "No se pudo eliminar", ok: false });
        setBorrando(false);
      }
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
      setBorrando(false);
    }
  }

  async function activar() {
  try {
    await activarPortafolio(archivo);   // ← esta sí llama a lib/api.ts
    setActivo(true);
    setMsg({ text: "Portafolio activado para monitoreo", ok: true });
  } catch (e: unknown) {
    setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
  }
}

  if (loading) return <div style={{ background: "var(--bg)", color: "var(--text-3)", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>Cargando...</div>;

  

  return (
    <>
        {msg.text && (
          <div style={{ padding: "10px 14px", borderRadius: 10, marginBottom: 16, fontSize: 13,
            background: msg.ok ? "rgba(48,209,88,0.1)" : "rgba(255,69,58,0.1)",
            color: msg.ok ? "#30d158" : "#ff453a" }}>
            {msg.text}
          </div>
        )}
        <PageIntro
                       archivo={archivo}
                       texto="Configura tu portafolio: activa el monitoreo en tiempo real, ajusta tus preferencias y gestiona la conexión con el bot de Telegram."
                     /> 
        {/* Nombre */}
        <GlowPanel>
          <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 6 }}>NOMBRE DEL PORTAFOLIO</h3>
          <p style={{ color: "var(--text-3)", fontSize: 12, marginBottom: 16 }}>
            Como se muestra en tu lista de portafolios.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={nombre}
              onChange={e => setNombre(e.target.value)}
              maxLength={60}
                            style={{ flex: 1, minWidth: 0, boxSizing: "border-box", background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 10, color: "var(--text)", fontSize: 14, padding: "11px 14px", fontFamily: "inherit", outline: "none" }}
            />
            <button
              onClick={guardarNombre}
              style={{ padding: "11px 20px", borderRadius: 10, border: "none", background: "#0071e3", color: "#fff", fontSize: 14, fontWeight: 500, fontFamily: "inherit", cursor: "pointer" }}
            >
              Guardar
            </button>
          </div>
        </GlowPanel>
        
        {/* Divisa */}
        <GlowPanel>
          <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 6 }}>DIVISA DE VISUALIZACIÓN</h3>
          <p style={{ color: "var(--text-3)", fontSize: 12, marginBottom: 16 }}>
            Elige en qué moneda quieres ver los montos de este portafolio.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {DIVISAS.map(d => (
              <button
                key={d.code}
                onClick={() => guardarDivisa(d.code)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 16px", borderRadius: 10, cursor: "pointer", fontSize: 14,
                  background: divisa === d.code ? "rgba(0,113,227,0.12)" : "transparent",
                  border: divisa === d.code ? "1px solid rgba(0,113,227,0.4)" : "1px solid rgba(255,255,255,0.08)",
                  color: "#f5f5f7", textAlign: "left",
                }}
              >
                <span><strong>{d.symbol}</strong> &nbsp; {d.label}</span>
                {divisa === d.code && <span style={{ color: "#0071e3" }}>✓</span>}
              </button>
            ))}
          </div>
        </GlowPanel>

        {/* Estado / activar */}
        <GlowPanel>
          <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 6 }}>ESTADO</h3>
          <p style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 12 }}>
            Estado actual: {activo
              ? <span style={{ color: "#30d158" }}>● ACTIVO para monitoreo</span>
              : <span style={{ color: "#6e6e73" }}>○ INACTIVO</span>}
          </p>
          {activo ? (
  <LiquidButton
    onClick={async () => {
      try {
        await desactivarPortafolio(archivo);
        setActivo(false);
        setMsg({ text: "Monitoreo detenido", ok: true });
      } catch (e: unknown) {
        setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
      }
    }}
    className="text-white font-semibold !px-12 !py-3.5 text-base"
  >
    Detener monitoreo
  </LiquidButton>
) : (
  <LiquidButton onClick={activar} className="text-white font-semibold !px-12 !py-3.5 text-base">
    Activar para monitoreo
  </LiquidButton>
)}
        </GlowPanel>

 {/* Zona peligrosa */}
        <GlowPanel>
          <h3 style={{ fontSize: "1rem", marginBottom: 12, color: "#ff453a" }}>Eliminar portafolio</h3>
          <p style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 16 }}>
            Borra este portafolio y todo su historial de forma permanente. Esta acción no se puede deshacer.
          </p>
          <button
            onClick={eliminar}
            disabled={borrando}
            style={{
              padding: "11px 24px", borderRadius: 12, cursor: borrando ? "default" : "pointer",
              fontFamily: "inherit", fontSize: 14, fontWeight: 500,
              background: "rgba(255,69,58,0.1)", color: "#ff453a",
              border: "1px solid rgba(255,69,58,0.3)",
              opacity: borrando ? 0.5 : 1,
            }}
          >
            {borrando ? "Eliminando..." : "Eliminar este portafolio"}
          </button>
        </GlowPanel>
  {dialogoUltimo && (
    <DialogoUltimoPortafolio
      archivo={archivo}
      onCancelar={() => setDialogoUltimo(false)}
    />
  )}
    </>
  );
}