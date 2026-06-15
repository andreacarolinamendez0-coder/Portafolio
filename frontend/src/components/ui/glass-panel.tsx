"use client";
import React, { ReactNode, CSSProperties } from "react";

interface GlassPanelProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function GlassPanel({ children, className = "", style }: GlassPanelProps) {
  return (
    <div
      className={className}
      style={{
        background: "var(--glass)",
        border: "1px solid var(--glass-border)",
        borderRadius: 18,
        padding: 24,
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        marginBottom: 16,
        ...style,
      }}
    >
      {children}
    </div>
  );
}