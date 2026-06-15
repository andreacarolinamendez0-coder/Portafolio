"use client";
import React, { ReactNode } from "react";

export function GlassBackground({ children }: { children: ReactNode }) {
  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "var(--bg)", overflow: "hidden" }}>
      {/* Glow superior izquierdo */}
      <div style={{
        position: "fixed", top: "-10%", left: "-5%", width: "40vw", height: "40vw",
        background: "radial-gradient(circle, rgba(10,132,255,0.10) 0%, transparent 70%)",
        filter: "blur(60px)", pointerEvents: "none", zIndex: 0,
      }} />
      {/* Glow inferior derecho */}
      <div style={{
        position: "fixed", bottom: "-10%", right: "-5%", width: "45vw", height: "45vw",
        background: "radial-gradient(circle, rgba(10,132,255,0.08) 0%, transparent 70%)",
        filter: "blur(70px)", pointerEvents: "none", zIndex: 0,
      }} />
      {/* Contenido por encima de los glows */}
      <div style={{ position: "relative", zIndex: 1 }}>
        {children}
      </div>
    </div>
  );
}