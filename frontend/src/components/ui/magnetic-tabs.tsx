"use client";

import * as React from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

export interface MagneticTabItem {
  value: string;
  label: string;
}

interface MagneticTabsProps {
  items: MagneticTabItem[];
  value: string;
  onChange: (value: string) => void;
}

export function MagneticTabs({ items, value, onChange }: MagneticTabsProps) {
  const [hovered, setHovered] = React.useState<string | null>(null);

  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const tabRefs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const x = useMotionValue(0);
  const w = useMotionValue(0);
  const spring = { stiffness: 300, damping: 25 };
  const springX = useSpring(x, spring);
  const springW = useSpring(w, spring);

  const moveTo = React.useCallback((val: string) => {
    const idx = items.findIndex(i => i.value === val);
    const btn = tabRefs.current[idx];
    const container = containerRef.current;
    if (btn && container) {
      const c = container.getBoundingClientRect();
      const t = btn.getBoundingClientRect();
      x.set(t.left - c.left);
      w.set(t.width);
    }
  }, [items, x, w]);

  React.useEffect(() => {
    moveTo(hovered ?? value);
  }, [hovered, value, moveTo]);

  React.useEffect(() => {
    const onResize = () => moveTo(value);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [value, moveTo]);

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        display: "inline-flex",
        gap: 2,
        padding: 4,
        background: "var(--glass)",
        border: "1px solid var(--glass-border)",
        borderRadius: 12,
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      {/* Indicador deslizante de vidrio */}
      <motion.div
        style={{
          position: "absolute",
          left: springX,
          width: springW,
          top: 4,
          bottom: 4,
          background: "rgba(255,255,255,0.10)",
          border: "1px solid var(--glass-border)",
          borderRadius: 8,
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
          pointerEvents: "none",
        }}
      />
      {items.map((item, i) => (
        <button
          key={item.value}
          ref={el => { tabRefs.current[i] = el; }}
          onClick={() => onChange(item.value)}
          onMouseEnter={() => setHovered(item.value)}
          onMouseLeave={() => setHovered(null)}
          style={{
            position: "relative",
            zIndex: 1,
            padding: "8px 22px",
            borderRadius: 8,
            cursor: "pointer",
            fontSize: "0.875rem",
            fontWeight: value === item.value ? 500 : 400,
            color: value === item.value ? "var(--text)" : "var(--text-3)",
            background: "transparent",
            border: "none",
            fontFamily: "inherit",
            transition: "color 0.2s",
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}