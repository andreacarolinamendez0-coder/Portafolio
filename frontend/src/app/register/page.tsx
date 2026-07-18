"use client";

import { useState } from "react";
import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { GlowCard } from "@/components/ui/spotlight-card";
import { authRegister } from "@/lib/api";

export default function RegisterPage() {
  const [form, setForm]       = useState({ username: "", email: "", password: "", telegram: "" });
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent]       = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (form.password.length < 6) { setError("La contraseña debe tener al menos 6 caracteres"); return; }
    setLoading(true);
    try {
      await authRegister(form);
      setSent(true);
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

  const campos = [
    { key: "username" as const, label: "Nombre de usuario", type: "text", placeholder: "ej: andrea", required: true },
    { key: "email" as const,    label: "Email",             type: "email", placeholder: "tu@email.com", required: true },
    { key: "password" as const, label: "Contraseña",        type: "password", placeholder: "Mínimo 6 caracteres", required: true },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", position: "relative", overflow: "hidden" }}>
      {/* Glows de fondo */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, minHeight: "100vh", display: "grid", gridTemplateColumns: "1fr 1fr", maxWidth: 1100, margin: "0 auto" }} className="reg-grid">

        {/* Lado izquierdo — marca */}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px", gap: 26 }} className="reg-brand">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <LogoMark size={40} />
            <span style={{ fontSize: 14, color: "var(--text-3)", letterSpacing: "0.02em" }}>Tu portafolio de inversiones</span>
          </div>

          <div>
            <h1 style={{ fontSize: "2.4rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.1, margin: 0 }}>
              Tu viaje empieza aquí.
            </h1>
            <p style={{ fontSize: "1.05rem", lineHeight: 1.7, maxWidth: 400, margin: "12px 0 0", color: "var(--text-2)", fontWeight: 500 }}>
              Crea tu cuenta y deja que Atom te guíe a invertir con{" "}
              <span className="highlight-sweep">claridad y sin miedo</span>.
            </p>
          </div>

          {/* 3 puntos */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {[
              { n: "1", t: "Conversa con Atom", d: "Te hace preguntas y entiende tus metas." },
              { n: "2", t: "Arma tu portafolio", d: "Una propuesta a tu medida, que puedes ajustar." },
              { n: "3", t: "Invierte con claridad", d: "Sigue tu progreso y aprende en el camino." },
            ].map(p => (
              <div key={p.n} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                <div style={{ width: 26, height: 26, borderRadius: "50%", background: "var(--glass)", border: "1px solid var(--glass-border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, color: "#4da3ff", flexShrink: 0 }}>{p.n}</div>
                <div>
                  <p style={{ fontSize: 13.5, fontWeight: 600, margin: 0 }}>{p.t}</p>
                  <p style={{ fontSize: 12.5, color: "var(--text-3)", margin: "2px 0 0", lineHeight: 1.5 }}>{p.d}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Lado derecho — formulario */}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px" }}>
          <div style={{ width: "100%", maxWidth: 380, margin: "0 auto" }}>
            <div style={{ marginBottom: 22 }}>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Crear cuenta</h2>
              <p style={{ color: "var(--text-3)", fontSize: "0.85rem", margin: "4px 0 0" }}>Es rápido y gratis</p>
            </div>

            {sent ? (
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>📬</div>
                <h2 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Revisa tu correo</h2>
                <p style={{ color: "var(--text-2)", fontSize: "0.9rem", lineHeight: 1.6, margin: "10px 0 0" }}>
                  Enviamos un enlace de activación a <strong style={{ color: "var(--text)" }}>{form.email}</strong>.
                  Ábrelo para activar tu cuenta — revisa también el spam.
                </p>
                <p style={{ color: "var(--text-3)", fontSize: "0.82rem", margin: "20px 0 0" }}>
                  ¿Ya activaste?{" "}
                  <Link href="/login" style={{ color: "#4da3ff", textDecoration: "none", fontWeight: 500 }}>Inicia sesión</Link>
                </p>
              </div>
            ) : (
              <>
                {error && (
                  <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
                    {error}
                  </div>
                )}

                <GlowCard glowColor="blue">
                  <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {campos.map(({ key, label, type, placeholder, required }) => (
                      <div key={key} style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                        <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>{label}</label>
                        <input type={type} value={form[key]} onChange={set(key)} placeholder={placeholder} required={required} style={inputStyle} />
                      </div>
                    ))}

                    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                      <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>
                        Telegram Chat ID <span style={{ opacity: 0.6, fontWeight: 400 }}>(opcional — para alertas)</span>
                      </label>
                      <input type="text" value={form.telegram} onChange={set("telegram")} placeholder="ej: 6999614895" style={inputStyle} />
                      <p style={{ color: "var(--text-3)", fontSize: 11, margin: "2px 0 0", opacity: 0.7 }}>
                        Envía /start a @userinfobot para obtener tu ID
                      </p>
                    </div>

                    <Button type="submit" disabled={loading} style={{ marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", height: "auto", opacity: loading ? 0.7 : 1 }}>
                      {loading ? "Creando cuenta..." : "Crear cuenta"}
                    </Button>
                  </form>
                </GlowCard>

                <p style={{ textAlign: "center", marginTop: 18, color: "var(--text-3)", fontSize: "0.82rem" }}>
                  ¿Ya tienes cuenta?{" "}
                  <Link href="/login" style={{ color: "#4da3ff", textDecoration: "none", fontWeight: 500 }}>Inicia sesión</Link>
                </p>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @media (max-width: 820px) {
          .reg-grid { grid-template-columns: 1fr !important; }
          .reg-brand { padding: 36px 32px 0 !important; }
        }
        .highlight-sweep {
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