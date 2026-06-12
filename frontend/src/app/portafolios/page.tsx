"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { authMe, authLogout, getPortafolios, activarPortafolio, type PortafolioSummary } from "@/lib/api";
import { NuevoPortafolioDialog } from "@/components/portfolio/nuevo-portafolio-dialog";

export default function PortafoliosPage() {
  const router = useRouter();
  const [username, setUsername]       = useState("");
  const [esAdmin, setEsAdmin]         = useState(false);
  const [portafolios, setPortafolios] = useState<PortafolioSummary[]>([]);
  const [loading, setLoading]         = useState(true);
  const [showNew, setShowNew]         = useState(false);

  async function load() {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      setUsername(me.username);
      setEsAdmin(me.es_admin);
      const { portafolios: list } = await getPortafolios();
      setPortafolios(list);
    } catch {
      router.push("/login");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleLogout() {
    await authLogout();
    router.push("/login");
  }

  async function handleActivar(archivo: string) {
    await activarPortafolio(archivo);
    load();
  }

  const nActivos = portafolios.filter(p => p.monitoreo_activo).length;

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "#000" }}>
      <div style={{ color: "#6e6e73", fontSize: 14 }}>Cargando...</div>
    </div>
  );

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "40px 24px" }}>

        {/* Header */}
        <div style={{ textAlign: "center", padding: "56px 40px 48px", marginBottom: 40, borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
            <LogoMark size={52} />
          </div>
          <h1 style={{ fontSize: "clamp(2rem,5vw,3.2rem)", fontWeight: 600, letterSpacing: "-0.03em", marginBottom: 8, lineHeight: 1.1 }}>
            Sistema de Portafolio
          </h1>
          <p style={{ color: "#6e6e73", fontSize: "0.9rem" }}>Gestión inteligente de inversiones</p>
        </div>

        {/* Toolbar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Mis Portafolios</h2>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ color: "#6e6e73", fontSize: 13 }}>Hola, {username}</span>
            {esAdmin && (
              <Link href="/admin">
                <Button variant="outline" size="sm" style={{ fontSize: 12, borderColor: "rgba(255,255,255,0.1)", color: "#a1a1a6", background: "#1a1a1a" }}>
                  🛡 Admin
                </Button>
              </Link>
            )}
            <Link href="/settings">
              <Button variant="outline" size="sm" style={{ fontSize: 12, borderColor: "rgba(255,255,255,0.1)", color: "#a1a1a6", background: "#1a1a1a" }}>
                Mi Perfil
              </Button>
            </Link>
            <Button variant="outline" size="sm" onClick={handleLogout} style={{ fontSize: 12, borderColor: "rgba(255,255,255,0.1)", color: "#a1a1a6", background: "#1a1a1a" }}>
              Cerrar sesión
            </Button>
            <Button size="sm" onClick={() => setShowNew(true)} style={{ background: "#0071e3", color: "#fff", fontSize: 12, borderRadius: 980 }}>
              + Crear Portafolio
            </Button>
          </div>
        </div>

        {/* Duplicate monitor warning */}
        {nActivos > 1 && (
          <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", marginBottom: 16, display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 18 }}>⚠️</span>
            <div>
              <p style={{ color: "#ff453a", fontSize: 13, fontWeight: 500, margin: "0 0 2px" }}>Más de un portafolio monitoreado</p>
              <p style={{ color: "#6e6e73", fontSize: 12, margin: 0 }}>Solo debería estar activo uno a la vez. Desactiva los que no necesites desde el Monitor.</p>
            </div>
          </div>
        )}

        {/* Portfolio cards */}
        {portafolios.length === 0 ? (
          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 40, textAlign: "center" }}>
            <p style={{ color: "#6e6e73", marginBottom: 16 }}>No tienes portafolios aún.</p>
            <Button onClick={() => setShowNew(true)} style={{ background: "#0071e3", color: "#fff", borderRadius: 980 }}>
              Crear mi primer portafolio
            </Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {portafolios.map(p => (
              <PortafolioCard key={p.archivo} portafolio={p} onActivar={handleActivar} />
            ))}
          </div>
        )}
      </div>

      {showNew && <NuevoPortafolioDialog onClose={() => setShowNew(false)} onCreated={load} />}
    </div>
  );
}

function PortafolioCard({ portafolio: p, onActivar }: { portafolio: PortafolioSummary; onActivar: (a: string) => void }) {
  const borde = p.monitoreo_activo ? "rgba(48,209,88,0.25)" : "rgba(255,255,255,0.07)";
  const fondo = p.monitoreo_activo ? "rgba(48,209,88,0.04)" : "rgba(255,255,255,0.04)";

  return (
    <div style={{ position: "relative" }}>
      <Link href={`/portafolio/${p.archivo}`} style={{ display: "block", textDecoration: "none" }}>
        <div
          style={{
            background: fondo, border: `1px solid ${borde}`,
            borderRadius: 18, padding: "24px 28px",
            backdropFilter: "blur(20px)", transition: "all 0.2s ease",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderColor = p.monitoreo_activo ? "rgba(48,209,88,0.4)" : "rgba(255,255,255,0.16)"; (e.currentTarget as HTMLDivElement).style.transform = "translateY(-1px)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor = borde; (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)"; }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
            <div>
              <div style={{ fontSize: "1.15rem", fontWeight: 600, color: "#f5f5f7", marginBottom: 2, letterSpacing: "-0.02em", display: "flex", alignItems: "center", gap: 8 }}>
                {p.nombre}
                {p.monitoreo_activo && (
                  <span style={{ fontSize: 11, color: "#30d158", fontWeight: 400 }}>● en vivo</span>
                )}
              </div>
              <div style={{ color: "#6e6e73", fontSize: "0.85rem" }}>{p.propietario}</div>
            </div>
            <Badge
              variant="outline"
              style={p.perfil === "agresivo"
                ? { background: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "1px solid rgba(255,214,10,0.2)", fontSize: "0.7rem" }
                : { background: "rgba(0,113,227,0.12)", color: "#4da3ff", border: "1px solid rgba(0,113,227,0.2)", fontSize: "0.7rem" }}
            >
              {p.perfil.toUpperCase()}
            </Badge>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
            <div style={{ color: "#6e6e73", fontSize: "0.78rem" }}>Desde {p.fecha_inicio}</div>
            {p.monitoreo_activo ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "#30d158", padding: "5px 12px", borderRadius: 980, background: "rgba(48,209,88,0.08)", border: "1px solid rgba(48,209,88,0.2)" }}>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#30d158", animation: "pulse-dot 2s infinite", display: "inline-block" }} />
                Monitoreando activamente
              </span>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={e => { e.preventDefault(); onActivar(p.archivo); }}
                style={{ padding: "5px 14px", borderRadius: 980, fontSize: 11, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.06)", color: "#6e6e73" }}
              >
                Activar monitoreo
              </Button>
            )}
          </div>
        </div>
      </Link>
    </div>
  );
}
