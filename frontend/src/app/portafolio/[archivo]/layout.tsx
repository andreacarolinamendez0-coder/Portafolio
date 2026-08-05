"use client";
import { useEffect, useState, useRef, Fragment } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { LogoMark } from "@/components/ui/logo";
import { getConfig, authLogout, authMe } from "@/lib/api";
import { SelectorPortafolios } from "@/components/ui/selector-portafolios";
import { NuevoPortafolioDialog } from "@/components/portfolio/nuevo-portafolio-dialog";

const TABS = [
  { id: "dashboard",   sub: "",             label: "Dashboard" },
  { id: "analista",    sub: "/analista",    label: "Analista" },
  { id: "seguimiento", sub: "/seguimiento", label: "Seguimiento" },
  { id: "bot",         sub: "/bot",         label: "Asistente" },
  { id: "monitor",     sub: "/monitor",     label: "Monitor" },
  { id: "config",      sub: "/config",      label: "Config" },
];

export default function PortafolioLayout({ children }: { children: React.ReactNode }) {
  const params   = useParams();
  const pathname = usePathname();
  const router   = useRouter();
  const archivo  = params.archivo as string;

  const [info, setInfo] = useState<{ nombre: string; perfil: string; propietario: string; fecha_inicio: string } | null>(null);
  const [selectorAbierto, setSelectorAbierto] = useState(false);
  const [crearAbierto, setCrearAbierto] = useState(false);
  const [esAdmin, setEsAdmin] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && archivo) {
      localStorage.setItem("ultimoPortafolio", archivo);
    }
    getConfig(archivo).then(d => setInfo({ nombre: d.nombre, perfil: d.perfil, propietario: d.propietario, fecha_inicio: d.fecha_inicio })).catch(() => {});
    authMe().then(me => setEsAdmin(me.es_admin)).catch(() => {});
  }, [archivo]);

    useEffect(() => {
    function onRename(e: Event) {
      const d = (e as CustomEvent<{ archivo: string; nombre: string }>).detail;
      if (d.archivo === archivo) setInfo(prev => (prev ? { ...prev, nombre: d.nombre } : prev));
    }
    window.addEventListener("portafolio-renombrado", onRename);
    return () => window.removeEventListener("portafolio-renombrado", onRename);
  }, [archivo]);

  // Detectar pestaña activa por la URL
  const base = `/portafolio/${archivo}`;
  const resto = pathname.replace(base, "");
  const activa = TABS.find(t => t.sub === resto)?.id ?? "dashboard";

  // Indicador magnético
  const [hovered, setHovered] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const w = useMotionValue(0);
  const h = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 300, damping: 25 });
  const springW = useSpring(w, { stiffness: 300, damping: 25 });

  useEffect(() => {
    const id = hovered ?? activa;
    const btn = tabRefs.current[id];
    const cont = containerRef.current;
    if (btn && cont) {
      const c = cont.getBoundingClientRect();
      const t = btn.getBoundingClientRect();
      x.set(t.left - c.left);
      y.set(t.top - c.top);
      w.set(t.width);
      h.set(t.height);
    }
  }, [hovered, activa, info, x, y, w, h]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      {/* Glows de fondo */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0 }}>
        <div style={{ position: "absolute", top: "-10%", left: "-5%", width: 500, height: 500, background: "radial-gradient(circle, rgba(0,113,227,0.10), transparent 70%)", filter: "blur(60px)" }} />
        <div style={{ position: "absolute", bottom: "-10%", right: "-5%", width: 500, height: 500, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(60px)" }} />
      </div>

      {/* Header fijo */}
      <header style={{ position: "relative", zIndex: 1, maxWidth: 1100, margin: "0 auto", padding: "20px 24px 0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
          <LogoMark size={34} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <button onClick={() => setSelectorAbierto(true)} style={{ display: "flex", alignItems: "center", gap: 8, background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", padding: 0, minWidth: 0, maxWidth: "100%" }}>
              <p style={{ fontSize: 15, fontWeight: 600, margin: 0, letterSpacing: "-0.01em", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>{info?.nombre || "Portafolio"}</p>
              <span style={{ color: "var(--text-3)", fontSize: 12, flexShrink: 0 }}>▾</span>
              {info?.perfil && (
                <span style={{
                  fontSize: "0.62rem", padding: "2px 8px", borderRadius: 980, fontWeight: 500, letterSpacing: "0.04em", flexShrink: 0,
                  ...(info.perfil === "agresivo"
                    ? { background: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "1px solid rgba(255,214,10,0.2)" }
                    : { background: "rgba(0,113,227,0.12)", color: "#4da3ff", border: "1px solid rgba(0,113,227,0.2)" }),
                }}>
                  {info.perfil.toUpperCase()}
                </span>
              )}
            </button>
            {info && (
              <p style={{ fontSize: 11, color: "var(--text-3)", margin: "2px 0 0" }}>
                {info.propietario}{info.fecha_inicio ? ` · Desde ${info.fecha_inicio}` : ""}
              </p>
            )}
          </div>
          {esAdmin && (
          <Link href="/admin" style={{ fontSize: 12, color: "#4da3ff", textDecoration: "none", padding: "7px 12px", display: "inline-flex", alignItems: "center", gap: 4 }}>
          🛡 Admin
          </Link>
          )}
          <Link href="/settings" style={{ fontSize: 12, color: "var(--text-3)", textDecoration: "none", padding: "7px 12px" }}>Mi Perfil</Link>
          <button onClick={async () => { await authLogout(); router.push("/login"); }} style={{ background: "none", border: "none", color: "var(--text-3)", fontSize: 12, cursor: "pointer" }}>Salir</button>
        </div>

        {/* Nav magnético glass */}
          <div
            ref={containerRef}
            className="nav-tabs"
            style={{ position: "relative", display: "inline-flex", gap: 2, padding: 4, background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12, backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", flexWrap: "wrap" }}
          >
            <motion.div
              style={{ position: "absolute", left: springX, top: y, width: springW, height: h, background: "rgba(255,255,255,0.10)", border: "1px solid var(--glass-border)", borderRadius: 8, backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)", pointerEvents: "none" }}
            />
            {TABS.map(t => (
              <Link
                key={t.id}
                href={`${base}${t.sub}`}
                ref={(el) => { tabRefs.current[t.id] = el; }}
                onMouseEnter={() => setHovered(t.id)}
                onMouseLeave={() => setHovered(null)}
                style={{
                  position: "relative", zIndex: 1, padding: "8px 18px", borderRadius: 8,
                  fontSize: "0.85rem", textDecoration: "none", fontWeight: activa === t.id ? 500 : 400,
                  color: activa === t.id ? "var(--text)" : "var(--text-3)", transition: "color 0.2s",
                }}
              >
                {t.label}
              </Link>
            ))}
          </div>
        <style>{`@media (max-width: 560px) { .nav-tabs { justify-content: center; } }`}</style>
      </header>

      {/* Contenido de la pestaña */}
      <main style={{ position: "relative", zIndex: 1, maxWidth: 1100, margin: "0 auto", padding: "24px" }}>
        {children}
      </main>
      <SelectorPortafolios
        abierto={selectorAbierto}
        onCerrar={() => setSelectorAbierto(false)}
        archivoActual={archivo}
        onCrear={() => setCrearAbierto(true)}
      />
      {crearAbierto && <NuevoPortafolioDialog onClose={() => setCrearAbierto(false)} onCreated={() => { setCrearAbierto(false); router.refresh(); }} />}
    </div>
  );
}