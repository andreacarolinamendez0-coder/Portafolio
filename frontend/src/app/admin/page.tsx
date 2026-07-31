"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Badge } from "@/components/ui/badge";
import { GlassBackground } from "@/components/ui/glass-background";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowCard } from "@/components/ui/spotlight-card";
import { MagneticTabs } from "@/components/ui/magnetic-tabs";
import {
  authMe,
  authLogout,
  adminListarUsuarios,
  adminActividad,
  adminEliminarUsuario,
  adminResetPassword,
  adminDesbloquear,
  adminToggleAdmin,
  type AdminUsuario,
  type ActividadEntry,
} from "@/lib/api";

// Etiqueta + color de brillo por tipo de evento
const TIPO_META: Record<string, { label: string; danger?: boolean }> = {
  login_ok:              { label: "Login" },
  login_fail:            { label: "Login fallido", danger: true },
  registro_nuevo:        { label: "Registro" },
  logout:                { label: "Logout" },
  eliminacion:           { label: "Usuario eliminado", danger: true },
  reset_password:        { label: "Reset clave" },
  portafolio_nuevo:      { label: "Portafolio creado" },
  portafolio_eliminado:  { label: "Portafolio eliminado", danger: true },
};

export default function AdminPage() {
  const router = useRouter();
  const [miUsuario, setMiUsuario] = useState("");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("usuarios");

  const [usuarios, setUsuarios] = useState<AdminUsuario[]>([]);
  const [actividad, setActividad] = useState<ActividadEntry[]>([]);
  const [resumenTipos, setResumenTipos] = useState<Record<string, number>>({});
  const [expandido, setExpandido] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const me = await authMe();
        if (!me.authenticated) { router.push("/login"); return; }
        if (!me.es_admin) { router.push("/"); return; }
        setMiUsuario(me.username);
        await cargarTodo();
      } catch {
        router.push("/login");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function cargarTodo() {
    const [u, a] = await Promise.all([adminListarUsuarios(), adminActividad(100)]);
    setUsuarios(u.usuarios);
    setActividad(a.actividad);
    setResumenTipos(a.resumen_tipos);
  }

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4500);
  }

  async function eliminar(username: string) {
    if (username === miUsuario) { flash("No puedes eliminarte a ti mismo", false); return; }
    if (!confirm(`¿Eliminar a "${username}"?\n\nEsto borra su cuenta y no se puede deshacer.`)) return;
    try {
      const r = await adminEliminarUsuario(username);
      if (r.ok) { flash(`Usuario ${username} eliminado`, true); cargarTodo(); }
      else flash(r.error ?? "No se pudo eliminar", false);
    } catch (e) { flash(e instanceof Error ? e.message : "Error", false); }
  }

  async function resetPass(username: string) {
    if (!confirm(`¿Resetear la contraseña de "${username}"?`)) return;
    try {
      const r = await adminResetPassword(username);
      if (r.ok) flash(r.mensaje ?? "Contraseña reseteada", true);
      else flash(r.error ?? "No se pudo resetear", false);
    } catch (e) { flash(e instanceof Error ? e.message : "Error", false); }
  }

  async function desbloquear(username: string) {
    try {
      const r = await adminDesbloquear(username);
      if (r.ok) { flash(`${username} desbloqueado`, true); cargarTodo(); }
      else flash(r.error ?? "No se pudo desbloquear", false);
    } catch (e) { flash(e instanceof Error ? e.message : "Error", false); }
  }

  async function toggleAdmin(u: AdminUsuario) {
    if (u.username === miUsuario) { flash("No cambies tu propio rol de admin", false); return; }
    const nuevo = !u.es_admin;
    if (!confirm(`¿${nuevo ? "Dar" : "Quitar"} admin a "${u.username}"?`)) return;
    try {
      const r = await adminToggleAdmin(u.username, nuevo);
      if (r.ok) { flash(`Rol de ${u.username} actualizado`, true); cargarTodo(); }
      else flash(r.error ?? "No se pudo cambiar", false);
    } catch (e) { flash(e instanceof Error ? e.message : "Error", false); }
  }

  async function handleLogout() {
    await authLogout();
    router.push("/login");
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)" }}>
      <div style={{ color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>
    </div>
  );

  const nAdmins = usuarios.filter(u => u.es_admin).length;
  const nBloqueados = usuarios.filter(u => u.bloqueado).length;
  const nEventos = Object.values(resumenTipos).reduce((a, b) => a + b, 0);

  return (
    <GlassBackground>
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px", color: "var(--text)" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <LogoMark size={32} />
            <div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>Panel de administración</div>
              <Link href="/" style={{ color: "var(--text-3)", fontSize: 12, textDecoration: "none" }}>
                ← Volver
              </Link>
            </div>
          </div>
          <button onClick={handleLogout} style={{
            padding: "8px 16px", borderRadius: 10, fontSize: 13, cursor: "pointer",
            background: "var(--glass)", border: "1px solid var(--glass-border)", color: "var(--text-3)",
          }}>Salir</button>
        </div>

        {/* Tarjetas resumen con brillo */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
          <GlowCard glowColor="blue" padding="16px 18px">
            <div style={{ fontSize: 26, fontWeight: 700 }}>{usuarios.length}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Usuarios</div>
          </GlowCard>
          <GlowCard glowColor="purple" padding="16px 18px">
            <div style={{ fontSize: 26, fontWeight: 700 }}>{nAdmins}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Admins</div>
          </GlowCard>
          <GlowCard glowColor={nBloqueados > 0 ? "red" : "green"} padding="16px 18px">
            <div style={{ fontSize: 26, fontWeight: 700 }}>{nBloqueados}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Bloqueados</div>
          </GlowCard>
          <GlowCard glowColor="teal" padding="16px 18px">
            <div style={{ fontSize: 26, fontWeight: 700 }}>{nEventos}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Eventos</div>
          </GlowCard>
        </div>

        {/* Mensaje flash */}
        {msg && (
          <div style={{
            padding: "10px 14px", borderRadius: 10, marginBottom: 16, fontSize: 13,
            background: msg.ok ? "rgba(48,209,88,0.1)" : "rgba(255,69,58,0.1)",
            border: `1px solid ${msg.ok ? "rgba(48,209,88,0.3)" : "rgba(255,69,58,0.3)"}`,
            color: msg.ok ? "#30d158" : "#ff453a",
          }}>{msg.text}</div>
        )}

        {/* Tabs */}
        <div style={{ marginBottom: 18 }}>
          <MagneticTabs
            items={[{ value: "usuarios", label: "Usuarios" }, { value: "actividad", label: "Actividad" }]}
            value={tab}
            onChange={setTab}
          />
        </div>

        {/* ── USUARIOS ── */}
        {tab === "usuarios" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {usuarios.map(u => (
              <GlassPanel key={u.username} style={{ marginBottom: 0, padding: "14px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 200 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{u.username}</span>
                      {u.es_admin && <Badge style={{ background: "rgba(79,138,255,0.15)", color: "#4da3ff" }}>admin</Badge>}
                      {u.bloqueado && <Badge style={{ background: "rgba(255,69,58,0.15)", color: "#ff453a" }}>bloqueado</Badge>}
                    </div>
                    <div style={{ color: "var(--text-3)", fontSize: 12, marginTop: 3 }}>{u.email}</div>
                    <div style={{ color: "var(--text-3)", fontSize: 11, marginTop: 4, opacity: 0.7 }}>
                      {u.n_portafolios} portafolio(s) · último acceso: {u.ultimo_login || "nunca"}
                      {u.intentos_fallidos > 0 && ` · ${u.intentos_fallidos} intentos fallidos`}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {u.bloqueado && <BtnMini onClick={() => desbloquear(u.username)} color="#30d158">Desbloquear</BtnMini>}
                    <BtnMini onClick={() => resetPass(u.username)} color="var(--text-3)">Reset clave</BtnMini>
                    <BtnMini onClick={() => toggleAdmin(u)} color="#4da3ff">{u.es_admin ? "Quitar admin" : "Hacer admin"}</BtnMini>
                    <BtnMini onClick={() => eliminar(u.username)} color="#ff453a">Eliminar</BtnMini>
                  </div>
                </div>
              </GlassPanel>
            ))}
          </div>
        )}

        {/* ── ACTIVIDAD ── */}
        {tab === "actividad" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {actividad.map((a, i) => {
              const meta = TIPO_META[a.tipo] ?? { label: a.tipo };
              const abierto = expandido === i;
              return (
                <GlassPanel key={i} style={{ marginBottom: 0, padding: 0 }}>
                  {/* Fila clickeable */}
                  <div
                    onClick={() => setExpandido(abierto ? null : i)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      gap: 12, flexWrap: "wrap", padding: "12px 16px", cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ color: "var(--text-3)", fontSize: 11, transform: abierto ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}>▸</span>
                      <Badge style={{
                        background: meta.danger ? "rgba(255,69,58,0.12)" : "rgba(255,255,255,0.06)",
                        color: meta.danger ? "#ff453a" : "var(--text-2)", fontSize: 11, padding: "2px 8px",
                      }}>{meta.label}</Badge>
                      <span style={{ fontSize: 13 }}>{a.username || a.email || "—"}</span>
                    </div>
                    <span style={{ color: "var(--text-3)", fontSize: 11, opacity: 0.7 }}>{a.fecha}</span>
                  </div>

                  {/* Detalle expandido */}
                  {abierto && (
                    <div style={{
                      padding: "0 16px 14px 37px", display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "8px 20px",
                      fontSize: 12, color: "var(--text-3)",
                    }}>
                      <Campo label="Usuario" valor={a.username} />
                      <Campo label="Correo" valor={a.email} />
                      <Campo label="Detalle" valor={a.detalle} />
                      <Campo label="IP" valor={a.ip} />
                      <Campo label="Fecha y hora" valor={a.fecha} />
                      <Campo label="Dispositivo" valor={a.dispositivo} />
                    </div>
                  )}
                </GlassPanel>
              );
            })}
            {actividad.length === 0 && (
              <div style={{ color: "var(--text-3)", fontSize: 13, padding: 20, textAlign: "center" }}>
                Sin actividad registrada
              </div>
            )}
          </div>
        )}
      </div>
    </GlassBackground>
  );
}

function Campo({ label, valor }: { label: string; valor: string }) {
  if (!valor) return null;
  return (
    <div>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em", opacity: 0.6, marginBottom: 2 }}>{label}</div>
      <div style={{ color: "var(--text-2)", wordBreak: "break-word" }}>{valor}</div>
    </div>
  );
}

function BtnMini({ onClick, color, children }: { onClick: () => void; color: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{
      padding: "5px 10px", borderRadius: 8, fontSize: 12, cursor: "pointer",
      background: "transparent", border: `1px solid ${color === "var(--text-3)" ? "var(--glass-border)" : color + "44"}`, color,
    }}>{children}</button>
  );
}