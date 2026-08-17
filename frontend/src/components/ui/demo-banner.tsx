"use client";
import { useIsDemo } from "@/lib/useIsDemo";

// Paso 5 del tratamiento de la cuenta demo: aviso sutil y permanente (no se
// puede cerrar) de que los datos no son reales -- la sesión demo es efímera
// por visitante, así que no tiene sentido "recordar" que ya se descartó.
export function DemoBanner() {
  const isDemo = useIsDemo();
  if (!isDemo) return null;

  return (
    <div
      style={{
        position: "sticky", top: 0, zIndex: 40,
        background: "var(--glass)", border: "1px solid var(--glass-border)", borderBottom: "1px solid rgba(0,113,227,0.25)",
        backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        padding: "8px 24px", textAlign: "center",
      }}
    >
      <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>
        <span style={{ marginRight: 6 }}>🔎</span>
        Estás viendo una demo — los datos no son reales y los cambios no se guardan.
      </span>
    </div>
  );
}
