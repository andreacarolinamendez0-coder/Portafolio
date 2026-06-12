"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authRegister } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm]       = useState({ username: "", email: "", password: "", telegram: "" });
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (form.password.length < 6) { setError("La contraseña debe tener al menos 6 caracteres"); return; }
    setLoading(true);
    try {
      await authRegister(form);
      router.push("/portafolios");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12" style={{ background: "#000" }}>
      <div className="w-full max-w-sm">

        <div className="flex flex-col items-center mb-8 gap-3">
          <LogoMark size={48} />
          <div className="text-center">
            <h1 style={{ color: "#f5f5f7", fontSize: "1.3rem", fontWeight: 600, letterSpacing: "-0.02em", marginBottom: 4 }}>
              Crear cuenta
            </h1>
            <p style={{ color: "#6e6e73", fontSize: "0.82rem" }}>Accede a tu sistema de portafolio</p>
          </div>
        </div>

        {error && (
          <div style={{
            background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)",
            borderRadius: 12, padding: "12px 16px", marginBottom: 16,
            color: "#ff6961", fontSize: "0.875rem",
          }}>
            {error}
          </div>
        )}

        <div style={{
          background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 18, padding: 22, backdropFilter: "blur(20px)",
        }}>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {[
              { key: "username" as const, label: "Nombre de usuario", type: "text", placeholder: "ej: andrea" },
              { key: "email" as const,    label: "Email",              type: "email", placeholder: "tu@email.com" },
              { key: "password" as const, label: "Contraseña",         type: "password", placeholder: "Mínimo 6 caracteres" },
            ].map(({ key, label, type, placeholder }) => (
              <div key={key} className="flex flex-col gap-2">
                <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>{label}</Label>
                <Input
                  type={type}
                  value={form[key]}
                  onChange={set(key)}
                  placeholder={placeholder}
                  required
                  style={{ background: "#111", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem" }}
                />
              </div>
            ))}

            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>
                Telegram Chat ID{" "}
                <span style={{ opacity: 0.6, fontWeight: 400 }}>(opcional — para alertas)</span>
              </Label>
              <Input
                type="text"
                value={form.telegram}
                onChange={set("telegram")}
                placeholder="ej: 6999614895"
                style={{ background: "#111", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem" }}
              />
              <p style={{ color: "#3d3d3f", fontSize: 11, marginTop: 4 }}>
                Envía /start a @userinfobot para obtener tu ID
              </p>
            </div>

            <Button
              type="submit"
              disabled={loading}
              style={{
                marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12,
                fontSize: "0.95rem", padding: "12px", height: "auto",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Creando cuenta..." : "Crear cuenta"}
            </Button>
          </form>
        </div>

        <p className="text-center mt-5" style={{ color: "#6e6e73", fontSize: "0.78rem" }}>
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" style={{ color: "#4da3ff", textDecoration: "none" }}>
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  );
}
