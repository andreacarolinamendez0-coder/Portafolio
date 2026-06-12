"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { crearPortafolio } from "@/lib/api";

interface Props {
  onClose:   () => void;
  onCreated: () => void;
}

export function NuevoPortafolioDialog({ onClose, onCreated }: Props) {
  const [form, setForm] = useState({
    nombre: "", propietario: "", perfil: "agresivo",
    inversion: "", aporte: "", frecuencia: "1",
  });
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await crearPortafolio({
        nombre:      form.nombre,
        propietario: form.propietario,
        perfil:      form.perfil,
        inversion:   parseFloat(form.inversion || "0"),
        aporte:      parseFloat(form.aporte || "0"),
        frecuencia:  parseInt(form.frecuencia),
      });
      onCreated();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al crear portafolio");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = { background: "#111", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 20, padding: 28, width: "100%", maxWidth: 520, maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <h2 style={{ color: "#f5f5f7", fontSize: "1.1rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>
            Crear Nuevo Portafolio
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#6e6e73", fontSize: 20, cursor: "pointer" }}>×</button>
        </div>

        {error && (
          <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 10, padding: "10px 14px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Nombre *</Label>
              <Input value={form.nombre} onChange={set("nombre")} placeholder="Ej: Agresivo Andrea 2026" required style={inputStyle} />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Propietario *</Label>
              <Input value={form.propietario} onChange={set("propietario")} placeholder="Ej: Andrea" required style={inputStyle} />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Perfil de riesgo</Label>
            <select value={form.perfil} onChange={set("perfil")} style={{ ...inputStyle, padding: "10px 14px", width: "100%", outline: "none" }}>
              <option value="agresivo">Agresivo — mayor riesgo, mayor retorno (10 años)</option>
              <option value="conservador">Conservador — menor riesgo, más estable (5 años)</option>
            </select>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Inversión inicial COP *</Label>
              <Input type="number" value={form.inversion} onChange={set("inversion")} placeholder="Ej: 1000000" required style={inputStyle} />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Aporte DCA COP</Label>
              <Input type="number" value={form.aporte} onChange={set("aporte")} placeholder="Ej: 500000" style={inputStyle} />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Frecuencia de aportes</Label>
            <select value={form.frecuencia} onChange={set("frecuencia")} style={{ ...inputStyle, padding: "10px 14px", width: "100%", outline: "none" }}>
              <option value="1">Mensual</option>
              <option value="3">Trimestral</option>
              <option value="12">Anual</option>
            </select>
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
            <Button type="button" variant="outline" onClick={onClose} style={{ borderColor: "rgba(255,255,255,0.1)", color: "#a1a1a6", background: "#1a1a1a" }}>
              Cancelar
            </Button>
            <Button type="submit" disabled={loading} style={{ background: "#0071e3", color: "#fff", opacity: loading ? 0.7 : 1 }}>
              {loading ? "Creando..." : "Crear Portafolio"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
