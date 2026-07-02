import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";

export function PageIntro({ archivo, texto }: { archivo: string; texto: string }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14, marginBottom: 24,
      padding: "14px 18px", background: "var(--glass)",
      border: "1px solid var(--glass-border)", borderRadius: 14,
    }}>
      <p style={{ flex: 1, fontSize: 13, lineHeight: 1.55, color: "var(--text-2)", margin: 0 }}>
        {texto}
      </p>
      <Link href={`/portafolio/${archivo}/bot`} title="Pregúntale a Atom sobre esta página" style={{ textDecoration: "none", flexShrink: 0 }}>
        <span className="atom-hint" style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "7px 13px 7px 10px", borderRadius: 980,
          background: "rgba(0,113,227,0.12)", border: "1px solid rgba(0,113,227,0.3)",
          color: "#4da3ff", fontSize: 12, fontWeight: 500, whiteSpace: "nowrap",
          transition: "all 0.18s ease", cursor: "pointer",
        }}>
          <span className="atom-glow" style={{ display: "inline-flex" }}>
            <LogoMark size={20} />
          </span>
          Pregúntale a Atom
        </span>
      </Link>
    </div>
  );
}