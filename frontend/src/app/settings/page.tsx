"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LogoMark } from "@/components/ui/logo";
import { authMe, authLogout, getProfile, updateProfile } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [profile, setProfile]   = useState({ username: "", email: "", telegram_chat_id: "", email_notifications: true });
  const [curPw, setCurPw]       = useState("");
  const [newPw, setNewPw]       = useState("");
  const [msgProfile, setMsgProfile] = useState({ text: "", ok: false });
  const [msgPw, setMsgPw]       = useState({ text: "", ok: false });
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    authMe().then(async me => {
      if (!me.authenticated) { router.push("/login"); return; }
      const p = await getProfile();
      setProfile(p);
    }).catch(() => router.push("/login")).finally(() => setLoading(false));
  }, [router]);

  async function saveProfile() {
    try {
      const res = await updateProfile({ email: profile.email, telegram_chat_id: profile.telegram_chat_id, email_notifications: profile.email_notifications });
      setMsgProfile({ text: res.mensaje, ok: true });
    } catch (e: unknown) {
      setMsgProfile({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  async function changePassword() {
    if (!curPw || !newPw) { setMsgPw({ text: "Completa ambos campos", ok: false }); return; }
    if (newPw.length < 6) { setMsgPw({ text: "Mínimo 6 caracteres", ok: false }); return; }
    try {
      const res = await updateProfile({ current_password: curPw, new_password: newPw });
      setMsgPw({ text: "Contraseña actualizada", ok: true });
      setCurPw(""); setNewPw("");
    } catch (e: unknown) {
      setMsgPw({ text: e instanceof Error ? e.message : "Error", ok: false });
    }
  }

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: "#000", color: "#6e6e73", fontSize: 14 }}>Cargando...</div>;

  const inputStyle = { background: "#111", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem" };

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7" }}>
      <div style={{ maxWidth: 600, margin: "0 auto", padding: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
          <LogoMark size={32} />
          <Link href="/portafolios" style={{ color: "#6e6e73", fontSize: 12, textDecoration: "none" }}>← Portafolios</Link>
          <span style={{ color: "#6e6e73", fontSize: 12 }}>/ Mi Perfil</span>
          <button onClick={async () => { await authLogout(); router.push("/login"); }} style={{ marginLeft: "auto", background: "none", border: "none", color: "#6e6e73", fontSize: 12, cursor: "pointer" }}>Salir</button>
        </div>

        <h2 style={{ fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.02em", marginBottom: 24 }}>Mi Perfil</h2>

        {/* Personal info */}
        <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24, marginBottom: 16 }}>
          <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 20 }}>Información personal</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem" }}>Nombre de usuario</Label>
              <Input value={profile.username} disabled style={{ ...inputStyle, opacity: 0.5 }} />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem" }}>Email</Label>
              <Input type="email" value={profile.email} onChange={e => setProfile(p => ({ ...p, email: e.target.value }))} placeholder="tu@email.com" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem" }}>Telegram Chat ID</Label>
              <Input value={profile.telegram_chat_id} onChange={e => setProfile(p => ({ ...p, telegram_chat_id: e.target.value }))} placeholder="ej: 3002443898" style={inputStyle} />
              <div style={{ marginTop: 8, padding: "12px 14px", background: "rgba(0,113,227,0.06)", border: "1px solid rgba(0,113,227,0.15)", borderRadius: 10 }}>
                <p style={{ fontSize: 12, color: "#4da3ff", fontWeight: 500, margin: "0 0 6px" }}>📲 Cómo activar las alertas de Telegram</p>
                {["Abre Telegram y busca @Miportafolio_andrea_bot","Presiona Iniciar / Start","El bot te enviará tu Chat ID automáticamente","Pega ese número aquí arriba y guarda"].map((s, i) => (
                  <p key={i} style={{ fontSize: 11, color: "#a1a1a6", margin: "0 0 4px" }}>{i+1}. {s}</p>
                ))}
              </div>
            </div>
          </div>
          <Button onClick={saveProfile} style={{ marginTop: 20, background: "#0071e3", color: "#fff", borderRadius: 12, width: "100%", padding: "12px", height: "auto", fontSize: "0.95rem" }}>
            Guardar cambios
          </Button>
          {msgProfile.text && (
            <p style={{ marginTop: 10, fontSize: 13, color: msgProfile.ok ? "#30d158" : "#ff453a" }}>
              {msgProfile.ok ? "✅" : "❌"} {msgProfile.text}
            </p>
          )}
        </div>

        {/* Change password */}
        <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24 }}>
          <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 20 }}>Cambiar contraseña</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem" }}>Contraseña actual</Label>
              <Input type="password" value={curPw} onChange={e => setCurPw(e.target.value)} placeholder="••••••••" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem" }}>Nueva contraseña</Label>
              <Input type="password" value={newPw} onChange={e => setNewPw(e.target.value)} placeholder="Mínimo 6 caracteres" style={inputStyle} />
            </div>
          </div>
          <Button onClick={changePassword} variant="outline" style={{ marginTop: 20, borderColor: "rgba(255,255,255,0.1)", color: "#f5f5f7", background: "#1a1a1a", borderRadius: 12, width: "100%", padding: "12px", height: "auto" }}>
            Cambiar contraseña
          </Button>
          {msgPw.text && (
            <p style={{ marginTop: 10, fontSize: 13, color: msgPw.ok ? "#30d158" : "#ff453a" }}>
              {msgPw.ok ? "✅" : "❌"} {msgPw.text}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
