"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { LogoMark } from "@/components/ui/logo";
import { eliminarPortafolio, eliminarCuenta } from "@/lib/api";

interface Props {
  archivo: string;           // el portafolio a eliminar
  onCancelar: () => void;    // cerrar el diálogo
}

export function DialogoUltimoPortafolio({ archivo, onCancelar }: Props) {
  const router = useRouter();
  const [ocupado, setOcupado] = useState(false);

  async function eliminarPort() {
    if (ocupado) return;
    setOcupado(true);
    try {
      const r = await eliminarPortafolio(archivo);
      if (r.ok) { router.push("/bienvenida"); }   // sin portafolios → reinicia onboarding
      else { alert(r.error ?? "No se pudo eliminar"); setOcupado(false); }
    } catch (err) { alert(err instanceof Error ? err.message : "Error"); setOcupado(false); }
  }

  async function eliminarCta() {
    if (ocupado) return;
    setOcupado(true);
    try {
      const r = await eliminarCuenta();
      if (r.ok) { router.push("/register"); }      // el server ya limpió la sesión
      else { alert(r.error ?? "No se pudo eliminar la cuenta"); setOcupado(false); }
    } catch (err) { alert(err instanceof Error ? err.message : "Error"); setOcupado(false); }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      onClick={() => !ocupado && onCancelar()}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(3px)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 380, background: "var(--bg)", border: "1px solid var(--glass-border)", borderRadius: 18, padding: 26, textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}
      >
        <div style={{ display: "inline-flex", marginBottom: 14 }}><LogoMark size={44} /></div>
        <h3 style={{ fontSize: "1.2rem", fontWeight: 600, margin: "0 0 8px", letterSpacing: "-0.01em" }}>¿Qué quieres hacer?</h3>
        <p style={{ color: "var(--text-2)", fontSize: "0.9rem", lineHeight: 1.6, margin: 0 }}>
          Este es tu <strong style={{ color: "var(--text)" }}>único portafolio</strong>. Si lo eliminas, volverás a empezar el onboarding. Y si eliminas tu cuenta… me pondré triste 🥺
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 22 }}>
          <button onClick={eliminarPort} disabled={ocupado}
            style={{ padding: 12, borderRadius: 12, border: "none", background: "#0071e3", color: "#fff", fontSize: 14, fontWeight: 500, fontFamily: "inherit", cursor: ocupado ? "default" : "pointer", opacity: ocupado ? 0.6 : 1 }}>
            Eliminar el portafolio
          </button>
          <button onClick={eliminarCta} disabled={ocupado}
            style={{ padding: 12, borderRadius: 12, background: "none", border: "1px solid rgba(255,69,58,0.35)", color: "#ff6961", fontSize: 14, fontWeight: 500, fontFamily: "inherit", cursor: ocupado ? "default" : "pointer", opacity: ocupado ? 0.6 : 1 }}>
            Eliminar mi cuenta
          </button>
          <button onClick={onCancelar} disabled={ocupado}
            style={{ padding: 8, background: "none", border: "none", color: "var(--text-3)", fontSize: 13, fontFamily: "inherit", cursor: "pointer" }}>
            Cancelar
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}