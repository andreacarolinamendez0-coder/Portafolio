"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getConfig, updateConfig, activarPortafolio } from "@/lib/api";

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

  useEffect(() => {
    getConfig(archivo)
      .then(d => { setNombre(d.nombre); setActivo(d.activo); setDivisa(d.divisa); })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [archivo, router]);

  async function guardarDivisa(nueva: string) {
    setDivisa(nueva); // actualiza la selección al instante
    try {
      const res = await updateConfig(archivo, nueva);
      setMsg({ text: res.mensaje, ok: true });
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  async function activar() {
    try {
      await activarPortafolio(archivo);
      setActivo(true);
      setMsg({ text: "Portafolio activado para monitoreo", ok: true });
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  if (loading) return <div style={{ background: "#000", color: "#6e6e73", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>Cargando...</div>;

  const cardStyle = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: 20, marginBottom: 16 };

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7" }}>
      <div style={{ maxWidth: 600, margin: "0 auto", padding: 24 }}>

        <Link href={`/portafolio/${archivo}`} style={{ color: "#6e6e73", fontSize: 12, textDecoration: "none" }}>← Volver al portafolio</Link>
        <h2 style={{ fontSize: "1.4rem", margin: "16px 0 24px" }}>Configuración — {nombre}</h2>

        {msg.text && (
          <div style={{ padding: "10px 14px", borderRadius: 10, marginBottom: 16, fontSize: 13,
            background: msg.ok ? "rgba(48,209,88,0.1)" : "rgba(255,69,58,0.1)",
            color: msg.ok ? "#30d158" : "#ff453a" }}>
            {msg.text}
          </div>
        )}

        {/* Divisa */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: "1rem", marginBottom: 6 }}>Divisa de visualización</h3>
          <p style={{ color: "#6e6e73", fontSize: 12, marginBottom: 16 }}>
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
        </div>

        {/* Estado / activar */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>Estado</h3>
          <p style={{ color: "#a1a1a6", fontSize: 13, marginBottom: 12 }}>
            Estado actual: {activo
              ? <span style={{ color: "#30d158" }}>● ACTIVO para monitoreo</span>
              : <span style={{ color: "#6e6e73" }}>○ INACTIVO</span>}
          </p>
          {!activo && (
            <button onClick={activar} style={{ padding: "8px 18px", borderRadius: 980, fontSize: 13, cursor: "pointer", background: "#1c1c1e", color: "#f5f5f7", border: "1px solid rgba(255,255,255,0.1)" }}>
              Activar para monitoreo
            </button>
          )}
        </div>

      </div>
    </div>
  );
}