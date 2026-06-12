"use client";

interface LogoProps {
  size?: number;
  color?: string;
}

export function Logo({ size = 18, color = "currentColor" }: LogoProps) {
  const s = (size / 30) * 30;
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" fill="none">
      <ellipse cx="15" cy="15" rx="10" ry="4" stroke={color} strokeWidth="1.3" fill="none" />
      <ellipse cx="15" cy="15" rx="10" ry="4" stroke={color} strokeWidth="1.3" fill="none" transform="rotate(60 15 15)" />
      <ellipse cx="15" cy="15" rx="10" ry="4" stroke={color} strokeWidth="1.3" fill="none" transform="rotate(120 15 15)" />
      <circle cx="15" cy="15" r="2.2" fill={color} />
    </svg>
  );
}

export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        background: "#0a0a0a",
        borderRadius: size * 0.28,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        border: "1px solid rgba(255,255,255,0.1)",
        flexShrink: 0,
        color: "white",
      }}
    >
      <Logo size={size * 0.55} color="white" />
    </div>
  );
}
