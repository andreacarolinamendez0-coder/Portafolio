"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { GlassPanel } from "@/components/ui/glass-panel";

interface Accion {
  id: string;
  label: string;
  sub: string; // suffijo de ruta bajo /portafolio/<archivo>
}

const ACCIONES: Accion[] = [
  { id: "dashboard",   label: "Ir a Dashboard",       sub: "" },
  { id: "analista",    label: "Ir al Analista",       sub: "/analista" },
  { id: "seguimiento", label: "Ir a Seguimiento",     sub: "/seguimiento" },
  { id: "bot",         label: "Abrir el chat de Atom", sub: "/bot" },
  { id: "monitor",     label: "Ir a Monitor",         sub: "/monitor" },
  { id: "config",      label: "Ir a Configuración",   sub: "/config" },
];

// Command palette no-IA (Cmd/Ctrl+K): acceso directo a cualquier pantalla
// del portafolio actual sin pasar por el nav ni por Atom -- la mitad de
// "mano derecha" que no necesita motor de IA, es solo velocidad.
export function CommandPalette({ archivo }: { archivo: string }) {
  const router = useRouter();
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const [activo, setActivo] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtradas = ACCIONES.filter(a => a.label.toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAbierto(v => !v);
        return;
      }
      if (e.key === "Escape" && abierto) {
        e.preventDefault();
        setAbierto(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [abierto]);

  useEffect(() => {
    if (abierto) {
      setQuery("");
      setActivo(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [abierto]);

  useEffect(() => { setActivo(0); }, [query]);

  function ir(a: Accion) {
    setAbierto(false);
    router.push(`/portafolio/${archivo}${a.sub}`);
  }

  if (!abierto) return null;

  return (
    <div
      onClick={() => setAbierto(false)}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)",
        display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "14vh",
      }}
    >
      <div onClick={e => e.stopPropagation()} style={{ width: 480, maxWidth: "calc(100vw - 40px)" }}>
        <GlassPanel style={{ padding: 0, marginBottom: 0, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActivo(i => Math.min(i + 1, filtradas.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActivo(i => Math.max(i - 1, 0)); }
              if (e.key === "Enter" && filtradas[activo]) { e.preventDefault(); ir(filtradas[activo]); }
            }}
            placeholder="Ir a..."
            style={{
              width: "100%", boxSizing: "border-box", background: "none", border: "none",
              borderBottom: "1px solid var(--glass-border)", outline: "none",
              color: "var(--text)", fontSize: "0.95rem", fontFamily: "inherit", padding: "16px 18px",
            }}
          />
          <div style={{ maxHeight: 280, overflowY: "auto", padding: 6 }}>
            {filtradas.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--text-3)", padding: "12px 12px" }}>Sin resultados.</p>
            )}
            {filtradas.map((a, i) => (
              <button
                key={a.id}
                onClick={() => ir(a)}
                onMouseEnter={() => setActivo(i)}
                style={{
                  display: "block", width: "100%", textAlign: "left", cursor: "pointer",
                  background: i === activo ? "rgba(255,255,255,0.08)" : "transparent",
                  border: "none", borderRadius: 10, padding: "10px 12px",
                  color: "var(--text)", fontSize: "0.88rem", fontFamily: "inherit",
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
