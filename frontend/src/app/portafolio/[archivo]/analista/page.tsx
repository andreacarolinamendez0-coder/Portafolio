"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getDashboard, type DashboardData } from "@/lib/api";

export default function AnalistaPage() {
  const params  = useParams();
  const router  = useRouter();
  const archivo = params.archivo as string;

  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard(archivo)
      .then(d => setData(d))
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [archivo, router]);

  if (loading) return <div style={s.load}>Cargando...</div>;
  if (!data)   return <div style={s.load}>No se pudo cargar</div>;

  const composicion = data.composicion || {};
  const tieneComposicion = Object.keys(composicion).length > 0;

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7" }}>
      <div style={{ maxWidth: 700, margin: "0 auto", padding: 24 }}>

        <Link href={`/portafolio/${archivo}`} style={{ color: "#6e6e73", fontSize: 12, textDecoration: "none" }}>← Volver al portafolio</Link>
        <h2 style={{ fontSize: "1.4rem", margin: "16px 0 24px" }}>Analista — {data.portafolio.nombre}</h2>

        {tieneComposicion ? (
          <>
            <div style={{ ...s.card, background: "rgba(0,113,227,0.06)", border: "1px solid rgba(0,113,227,0.15)" }}>
              <p style={{ color: "#4da3ff", fontSize: 13, margin: 0 }}>
                Este portafolio ya tiene una composición generada. Abajo puedes verla.
              </p>
            </div>
            <div style={s.card}>
              <h3 style={s.h3}>Composición actual</h3>
              {Object.entries(composicion).map(([activo, peso]) => (
                <div key={activo} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                  <span>{activo}</span>
                  <span style={{ color: "#30d158", fontWeight: 600 }}>{(peso * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div style={s.card}>
            <h3 style={s.h3}>Sin composición todavía</h3>
            <p style={{ color: "#a1a1a6", fontSize: 14, lineHeight: 1.6 }}>
              Este portafolio aún no tiene una propuesta de inversión. El chat con el analista de IA —que te guía para generar la composición— estará disponible próximamente en esta pantalla.
            </p>
          </div>
        )}

        <div style={{ ...s.card, opacity: 0.5 }}>
          <h3 style={s.h3}>Chat con el analista</h3>
          <p style={{ color: "#6e6e73", fontSize: 13 }}>Próximamente — chat con IA para generar y ajustar tu portafolio.</p>
        </div>

      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  load: { background: "#000", color: "#6e6e73", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 },
  card: { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: 20, marginBottom: 16 },
  h3:   { fontSize: "1rem", marginBottom: 12 },
};
