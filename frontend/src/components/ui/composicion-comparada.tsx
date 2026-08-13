"use client";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { GlassPanel } from "@/components/ui/glass-panel";

interface Props {
  composicionMeta: Record<string, number>;
  composicionReal: Record<string, number>;
}

// Colores validados (dataviz skill) para este par categorico especifico
// (meta vs real) contra la superficie oscura de la app -- no son los
// hex "oficiales" del resto del proyecto (#0071e3/#ff9f0a) porque esos
// fallan el chequeo de banda de luminancia para uso categorico en un
// grafico de barras; son primos cercanos en la misma familia de matiz.
const COLOR_META = "#3987e5";
const COLOR_REAL = "#d95926";

export function ComposicionComparada({ composicionMeta, composicionReal }: Props) {
  const tickers = Array.from(new Set([...Object.keys(composicionMeta), ...Object.keys(composicionReal)]))
    .sort((a, b) => (composicionMeta[b] ?? 0) - (composicionMeta[a] ?? 0));

  const data = tickers.map(t => ({
    ticker: t,
    meta: Math.round((composicionMeta[t] ?? 0) * 1000) / 10,
    real: Math.round((composicionReal[t] ?? 0) * 1000) / 10,
  }));

  if (!data.length) return null;

  return (
    <GlassPanel>
      <p style={{ color: "var(--text)", fontSize: 14, fontWeight: 600, margin: "0 0 4px" }}>
        Composición: meta vs real
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 12, margin: "0 0 12px" }}>
        Qué te propusiste vs qué tienes hoy realmente, por activo.
      </p>

      <div style={{ width: "100%", height: Math.max(220, data.length * 44) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 4 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, "dataMax"]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 11, fill: "var(--text-3)" }}
              stroke="rgba(255,255,255,0.1)"
            />
            <YAxis
              type="category"
              dataKey="ticker"
              tick={{ fontSize: 12, fill: "var(--text)" }}
              stroke="rgba(255,255,255,0.1)"
              width={64}
            />
            <Tooltip
              contentStyle={{ background: "rgba(12,12,12,0.97)", border: "1px solid var(--glass-border)", borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: "var(--text)", marginBottom: 4, fontWeight: 600 }}
              formatter={(value, name) => [`${value}%`, name === "meta" ? "Meta" : "Real"]}
            />
            <Legend
              formatter={(value) => (
                <span style={{ color: "var(--text-2)", fontSize: 12 }}>{value === "meta" ? "Meta" : "Real"}</span>
              )}
              wrapperStyle={{ fontSize: 12 }}
            />
            <Bar dataKey="meta" name="meta" fill={COLOR_META} radius={[0, 4, 4, 0]} barSize={14} />
            <Bar dataKey="real" name="real" fill={COLOR_REAL} radius={[0, 4, 4, 0]} barSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}
