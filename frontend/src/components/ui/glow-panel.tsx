"use client";
import React, { ReactNode, CSSProperties } from "react";

interface GlowPanelProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function GlowPanel({ children, className = "", style }: GlowPanelProps) {
  return (
    <div
      className={className}
      style={{
        position: "relative",
        background: "var(--glass)",
        border: "1px solid var(--glass-border)",
        borderRadius: 18,
        padding: 24,
        marginBottom: 16,
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.10), 0 0 30px rgba(10,132,255,0.08)",
        overflow: "hidden",
        ...style,
      }}
    >
      {/* Reflejo de vidrio en movimiento */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 18,
          pointerEvents: "none",
          backgroundImage: "radial-gradient(60% 50% at 30% 20%, rgba(10,132,255,0.18) 0%, transparent 60%), radial-gradient(50% 40% at 80% 70%, rgba(120,180,255,0.12) 0%, transparent 60%)",
          backgroundSize: "200% 200%",
          animation: "glass-sheen 12s ease-in-out infinite",
        }}
      />
      {/* Contenido por encima del reflejo */}
      <div style={{ position: "relative", zIndex: 1 }}>
        {children}
      </div>
    </div>
  );
}