"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { crearPortafolio, getPortafolios, authMe } from "@/lib/api";
import { LiquidButton } from "@/components/ui/liquid-glass-button";

interface Props {
  onClose:   () => void;
  onCreated: () => void;
}

export function NuevoPortafolioDialog({ onClose, onCreated }: Props) {
  const router = useRouter();
  const [nombre, setNombre]           = useState("");
  const [propietario, setPropietario] = useState("");
  const [error, setError]             = useState("");
  const [loading, setLoading]         = useState(false);

  // Propietario por defecto = usuario de la sesión
  useEffect(() => {
    authMe().then(me => setPropietario(p => p || me.username)).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const nombreLimpio = nombre.trim();
      await crearPortafolio({
        nombre:      nombreLimpio,
        propietario: propietario.trim(),
        perfil:      "moderado",   // el perfil real se define en el chat del Analista
        inversion:   0,
      });
      const { portafolios } = await getPortafolios();
      const nuevo = portafolios.find(p => p.nombre === nombreLimpio);
      onCreated();
      onClose();
      router.push(nuevo ? `/portafolio/${nuevo.archivo}/analista` : "/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al crear portafolio");
      setLoading(false);
    }
  }

  const inputStyle = { background: "#111", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem", padding: "1px 8px" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 20, padding: 28, width: "100%", maxWidth: 420 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h2 style={{ color: "#f5f5f7", fontSize: "1.1rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>
            Nuevo portafolio
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#6e6e73", fontSize: 20, cursor: "pointer" }}>×</button>
        </div>
        <p style={{ color: "#6e6e73", fontSize: "0.8rem", margin: "0 0 20px" }}>
          Ponle un nombre. El perfil, la inversión y los aportes los defines con Atom en el chat.
        </p>

        {error && (
          <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 10, padding: "10px 14px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="flex flex-col gap-2">
            <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Nombre *</Label>
            <Input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej: Agresivo 2026" required autoFocus style={inputStyle} />
          </div>
          <div className="flex flex-col gap-2">
            <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Propietario *</Label>
            <Input value={propietario} onChange={e => setPropietario(e.target.value)} placeholder="Tu nombre" required style={inputStyle} />
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
            <Button type="button" variant="outline" onClick={onClose} style={{ borderColor: "rgba(255,255,255,0.1)", color: "#a1a1a6", padding: "4px 10px", background: "#1a1a1a" }}>
              Cancelar
            </Button>
            <LiquidButton type="submit" disabled={loading || !nombre.trim() || !propietario.trim()} style={{padding: "4px 10px", opacity: loading ? 0.7 : 1 }}>
              {loading ? "Creando..." : "Crear portafolio"}
            </LiquidButton>
          </div>
        </form>
      </div>
    </div>
  );
}