"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { GlowCard } from "@/components/ui/spotlight-card";
import { authLogin } from "@/lib/api";

const TRIVIA_BIENVENIDA = [
  "Comprar caro y vender barato es una estrategia. Mala, pero estrategia.",
  "El mercado puede permanecer irracional más tiempo del que tú puedes aguantar sin mirar el celular.",
  "Tu cuenta de ahorros le tiene tanto miedo a la inflación como tú a tu ex. Y con razón.",
  "Regla #1: no pierdas dinero. Regla #2: no olvides la regla #1. (Gracias, Warren.)",
  "Invertir sin diversificar es como pedir un solo plato en un buffet. Técnicamente válido, pero ¿por qué?",
  "El interés compuesto trabaja mientras duermes. Es el único empleado que nunca renuncia.",
  "Si entiendes en qué inviertes, ya le ganas a la mitad de Wall Street.",
  "La bolsa transfiere dinero de los impacientes a los pacientes. No seas el impaciente.",
  "No necesitas ser rico para empezar a invertir. Pero sí necesitas empezar (spoiler: ese es el chiste).",
  "El mejor momento para invertir fue hace 10 años. El segundo mejor es hoy. El peor es «mañana lo hago».",
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [triviaIdx, setTriviaIdx] = useState(0);
  const [avisoPw, setAvisoPw]   = useState(false);

  useEffect(() => {
    setTriviaIdx(Math.floor(Math.random() * TRIVIA_BIENVENIDA.length));
    const t = setInterval(() => setTriviaIdx(i => (i + 1) % TRIVIA_BIENVENIDA.length), 9000);
    return () => clearInterval(t);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authLogin(email, password);
      // Decidir a dónde ir tras login
      const { getPortafolios } = await import("@/lib/api");
      const { portafolios } = await getPortafolios();
      if (portafolios.length === 0) {
        // Sin portafolios → crear el primero
        router.push("/bienvenida");
      } else {
        // Ir al último usado si existe y sigue válido, si no al primero
        const ultimo = typeof window !== "undefined" ? localStorage.getItem("ultimoPortafolio") : null;
        const existe = ultimo && portafolios.some(p => p.archivo === ultimo);
        router.push(`/portafolio/${existe ? ultimo : portafolios[0].archivo}`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", background: "var(--bg-2)", border: "1px solid var(--glass-border)",
    borderRadius: 12, color: "var(--text)", fontSize: "0.9rem", padding: "11px 14px",
    fontFamily: "inherit", outline: "none", boxSizing: "border-box",
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", position: "relative", overflow: "hidden" }}>
      {/* Glows de fondo */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, minHeight: "100vh", display: "grid", gridTemplateColumns: "1fr 1fr", maxWidth: 1100, margin: "0 auto" }} className="login-grid">

        {/* Lado izquierdo — marca + trivia */}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px", gap: 28 }} className="login-brand">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <LogoMark size={40} />
            <span style={{ fontSize: 14, color: "var(--text-3)", letterSpacing: "0.02em" }}>Tu portafolio de inversiones</span>
          </div>

          <div>
            <h1 style={{ fontSize: "2.4rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.1, margin: 0 }}>
              Invierte con claridad.
            </h1>
            <p style={{ fontSize: "1.4rem", fontWeight: 500, letterSpacing: "-0.02em", margin: "6px 0 0", color: "var(--text-2)" }}>
              Sin jerga, sin humo, sin miedo.
            </p>
          </div>

          <p style={{ fontSize: "1.05rem", lineHeight: 1.7, maxWidth: 400, margin: 0, color: "var(--text-2)", fontWeight: 500 }}>
            Construye tu portafolio conversando con un analista que te explica el{" "}
            <span className="highlight-sweep">porqué de cada decisión</span>. Finanzas e inversiones, en español de verdad.
          </p>

          <div style={{ background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 14, padding: "16px 18px", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", maxWidth: 400 }}>
            <p style={{ fontSize: 10.5, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 8px" }}>Mientras tanto...</p>
            <div style={{ minHeight: 44, position: "relative" }}>
              <AnimatePresence mode="wait">
                <motion.p
                  key={triviaIdx}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -12 }}
                  transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                  style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.6, margin: 0 }}
                >
                  {TRIVIA_BIENVENIDA[triviaIdx]}
                </motion.p>
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Lado derecho — formulario */}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px" }}>
          <div style={{ width: "100%", maxWidth: 360, margin: "0 auto" }}>
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Bienvenido de vuelta</h2>
              <p style={{ color: "var(--text-3)", fontSize: "0.85rem", margin: "4px 0 0" }}>Ingresa para ver tu portafolio</p>
            </div>

            {error && (
              <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
                {error}
              </div>
            )}

            <GlowCard glowColor="blue">
              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Email</label>
                  <input
                    type="email" value={email} onChange={e => setEmail(e.target.value)}
                    placeholder="tu@email.com" required autoFocus style={inputStyle}
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Contraseña</label>
                  <input
                    type="password" value={password} onChange={e => setPassword(e.target.value)}
                    placeholder="••••••••" required style={inputStyle}
                  />
                </div>
                <Button
                  type="submit" disabled={loading}
                  style={{ marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", height: "auto", opacity: loading ? 0.7 : 1 }}
                >
                  {loading ? "Entrando..." : "Entrar"}
                </Button>

                {/* Olvidé mi contraseña — gracioso */}
                <button
                  type="button"
                  onClick={() => setAvisoPw(true)}
                  style={{ background: "none", border: "none", color: "var(--text-3)", fontSize: "0.78rem", cursor: "pointer", textAlign: "center", fontFamily: "inherit", marginTop: 2 }}
                >
                  ¡Perdón! Se me olvidó la contraseña, ayúdame
                </button>
                {avisoPw && (
                  <p style={{ fontSize: "0.74rem", color: "var(--text-3)", textAlign: "center", margin: 0, lineHeight: 1.5 }}>
                    Tranqui, le pasa a todos. Esta función llega pronto — por ahora escríbele a soporte y te ayudamos.
                  </p>
                )}
              </form>
            </GlowCard>

            <p style={{ textAlign: "center", marginTop: 20, color: "var(--text-3)", fontSize: "0.82rem", lineHeight: 1.5 }}>
              ¿Es así de fácil y aún no tengo cuenta?{" "}
              <Link href="/register" style={{ color: "#4da3ff", textDecoration: "none", fontWeight: 500 }}>Registrarme</Link>
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @media (max-width: 820px) {
          .login-grid { grid-template-columns: 1fr !important; }
          .login-brand { padding: 36px 32px 0 !important; }
        }
        .highlight-sweep {
          position: relative;
          background-image: linear-gradient(120deg, rgba(255,255,255,0.22), rgba(255,255,255,0.22));
          background-repeat: no-repeat;
          background-position: 0 0;
          background-size: 0% 100%;
          padding: 2px 4px;
          margin: 0 -4px;
          border-radius: 4px;
          color: var(--text);
          animation: sweep-highlight 1.1s cubic-bezier(0.65, 0, 0.35, 1) 0.6s forwards;
        }
        @keyframes sweep-highlight {
          to { background-size: 100% 100%; }
        }
      `}</style>
    </div>
  );
}