"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { getPortafolios, eliminarPortafolio, type PortafolioSummary } from "@/lib/api";
import { DialogoUltimoPortafolio } from "@/components/ui/dialogo-ultimo-portafolio";

interface Props {
  abierto: boolean;
  onCerrar: () => void;
  archivoActual: string;
  onCrear: () => void;
}

export function SelectorPortafolios({ abierto, onCerrar, archivoActual, onCrear }: Props) {
  const router = useRouter();
  const [portafolios, setPortafolios] = useState<PortafolioSummary[]>([]);
  const [cargando, setCargando] = useState(true);
  const [borrando, setBorrando] = useState<string | null>(null);
  const [dialogoUltimo, setDialogoUltimo] = useState<PortafolioSummary | null>(null);

  useEffect(() => {
    if (abierto) {
      setCargando(true);
      getPortafolios()
        .then(({ portafolios }) => setPortafolios(portafolios))
        .catch(() => {})
        .finally(() => setCargando(false));
    }
  }, [abierto]);

  function irA(archivo: string) {
    onCerrar();
    if (archivo !== archivoActual) router.push(`/portafolio/${archivo}`);
  }

  async function eliminar(e: React.MouseEvent, p: PortafolioSummary) {
    e.stopPropagation();  // NO navegar al portafolio al hacer clic en la basura
    if (portafolios.length === 1) { setDialogoUltimo(p); return; }
    if (!confirm(`¿Eliminar el portafolio "${p.nombre}"?\n\nSe borra junto con todo su historial. Esto no se puede deshacer.`)) return;
    setBorrando(p.archivo);
    try {
      const r = await eliminarPortafolio(p.archivo);
      if (r.ok) {
        const quedan = portafolios.filter(x => x.archivo !== p.archivo);
        setPortafolios(quedan);
        // Si borraste el que estabas viendo, hay que salir de esa pantalla
        if (p.archivo === archivoActual) {
          if (quedan.length > 0) { onCerrar(); router.push(`/portafolio/${quedan[0].archivo}`); }
          else { onCerrar(); router.push("/"); }
        }
      } else {
        alert(r.error ?? "No se pudo eliminar");
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Error");
    } finally {
      setBorrando(null);
    }
  }

  return (
    <>
      <AnimatePresence>
        {abierto && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={onCerrar}
              style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)", zIndex: 50 }}
            />

            <motion.div
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}
              style={{
                position: "fixed", top: 0, left: 0, bottom: 0, width: 340, maxWidth: "85vw", zIndex: 51,
                background: "var(--bg)", borderRight: "1px solid var(--glass-border)",
                display: "flex", flexDirection: "column", padding: 20,
                boxShadow: "8px 0 40px rgba(0,0,0,0.4)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0, letterSpacing: "-0.01em" }}>Mis portafolios</h3>
                <button onClick={onCerrar} style={{ background: "none", border: "none", color: "var(--text-3)", fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
              </div>

              <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
                {cargando ? (
                  <p style={{ color: "var(--text-3)", fontSize: 13, textAlign: "center", marginTop: 20 }}>Cargando...</p>
                ) : portafolios.length === 0 ? (
                  <p style={{ color: "var(--text-3)", fontSize: 13, textAlign: "center", marginTop: 20 }}>No tienes portafolios aún.</p>
                ) : (
                  portafolios.map(p => {
                    const activo = p.archivo === archivoActual;
                    const seBorra = borrando === p.archivo;
                    return (
                      <div
                        key={p.archivo}
                        onClick={() => irA(p.archivo)}
                        style={{
                          position: "relative", cursor: "pointer", borderRadius: 12, padding: "14px 16px",
                          background: activo ? "rgba(0,113,227,0.10)" : "var(--glass)",
                          border: `1px solid ${activo ? "rgba(0,113,227,0.3)" : "var(--glass-border)"}`,
                          transition: "border-color 0.15s", opacity: seBorra ? 0.5 : 1,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", display: "flex", alignItems: "center", gap: 7 }}>
                            {p.nombre}
                            {p.monitoreo_activo && <span style={{ fontSize: 10, color: "#30d158", fontWeight: 400 }}>● en vivo</span>}
                          </span>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{
                              fontSize: "0.6rem", padding: "2px 7px", borderRadius: 980, fontWeight: 500, letterSpacing: "0.04em",
                              ...(p.perfil === "agresivo"
                                ? { background: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "1px solid rgba(255,214,10,0.2)" }
                                : { background: "rgba(0,113,227,0.12)", color: "#4da3ff", border: "1px solid rgba(0,113,227,0.2)" }),
                            }}>
                              {p.perfil.toUpperCase()}
                            </span>
                            {/* Boton eliminar */}
                            <button
                              onClick={(e) => eliminar(e, p)}
                              disabled={seBorra}
                              title="Eliminar portafolio"
                              style={{
                                background: "none", border: "none", cursor: seBorra ? "default" : "pointer",
                                color: "var(--text-3)", fontSize: 15, lineHeight: 1, padding: 2,
                                opacity: 0.6, transition: "color 0.15s, opacity 0.15s",
                              }}
                              onMouseEnter={(e) => { e.currentTarget.style.color = "#ff453a"; e.currentTarget.style.opacity = "1"; }}
                              onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-3)"; e.currentTarget.style.opacity = "0.6"; }}
                            >
                              🗑
                            </button>
                          </div>
                        </div>
                        <span style={{ fontSize: 12, color: "var(--text-3)" }}>{p.propietario} · Desde {p.fecha_inicio}</span>
                      </div>
                    );
                  })
                )}
              </div>

              <button
                onClick={() => { onCerrar(); onCrear(); }}
                style={{
                  marginTop: 16, padding: "12px", borderRadius: 12, cursor: "pointer", fontFamily: "inherit",
                  background: "#0071e3", color: "#fff", border: "none", fontSize: 14, fontWeight: 500,
                }}
              >
                + Crear nuevo portafolio
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {dialogoUltimo && (
          <DialogoUltimoPortafolio
            archivo={dialogoUltimo.archivo}
            onCancelar={() => setDialogoUltimo(null)}
          />
        )}
      </AnimatePresence>
    </>
  );}
