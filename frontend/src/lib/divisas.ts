export type Divisa = "USD" | "EUR" | "COP";

const SIMBOLOS: Record<Divisa, string> = {
  USD: "US$",
  EUR: "€",
  COP: "$",
};

interface Tasas {
  trm: number;       // COP por 1 USD
  tasa_eur: number;  // EUR por 1 USD
}

/**
 * Convierte un monto en COP a la divisa elegida y lo formatea.
 * COP → USD: dividir por TRM. COP → EUR: dividir por TRM, multiplicar por tasa_eur.
 */
export function mostrarMonto(montoCOP: number, divisa: Divisa, tasas: Tasas): string {
  const simbolo = SIMBOLOS[divisa];
  let valor = montoCOP;

  if (divisa === "USD") {
    valor = tasas.trm ? montoCOP / tasas.trm : 0;
  } else if (divisa === "EUR") {
    valor = tasas.trm ? (montoCOP / tasas.trm) * tasas.tasa_eur : 0;
  }
  // COP se queda igual

  // USD/EUR con 2 decimales, COP sin decimales
  const decimales = divisa === "COP" ? 0 : 2;
  const formateado = valor.toLocaleString("es-CO", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });

  return `${simbolo}${formateado}`;
}