export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const data = await res.json();
  if (!res.ok) throw new ApiError(res.status, data.error ?? "Error desconocido");
  return data as T;
}

// ── Auth ────────────────────────────────────────────────────

export const authMe = () =>
  apiFetch<{ authenticated: boolean; username: string; es_admin: boolean }>("/api/auth/me");

export const authLogin = (email: string, password: string) =>
  apiFetch<{ ok: boolean; username: string; es_admin: boolean }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const authRegister = (data: {
  username: string;
  email: string;
  password: string;
  telegram?: string;
}) =>
  apiFetch<{ ok: boolean; username: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const authLogout = () =>
  apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });

export const authResetPassword = (token: string, password: string) =>
  apiFetch<{ ok: boolean }>("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });

  export const authForgotPassword = (email: string) =>
  apiFetch<{ ok: boolean }>("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const authActivate = (token: string) =>
  apiFetch<{ ok: boolean }>("/api/auth/activate", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

  
// ── Portfolios ──────────────────────────────────────────────

export interface PortafolioSummary {
  archivo:          string;
  nombre:           string;
  propietario:      string;
  perfil:           string;
  fecha_inicio:     string;
  monitoreo_activo: boolean;
}

export const getPortafolios = () =>
  apiFetch<{ portafolios: PortafolioSummary[] }>("/api/portafolios");

export const crearPortafolio = (data: {
  nombre:      string;
  propietario: string;
  perfil:      string;
  inversion:   number;
  aporte?:     number;
  frecuencia?: number;
}) =>
  apiFetch<{ ok: boolean; mensaje: string }>("/api/portafolios", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const activarPortafolio = (archivo: string) =>
  apiFetch<{ ok: boolean }>(`/api/portafolios/${archivo}/activar`, { method: "POST" });

export const desactivarPortafolio = (archivo: string) =>
  apiFetch<{ ok: boolean }>(`/api/portafolios/${archivo}/desactivar`, { method: "POST" });

// ── Dashboard ───────────────────────────────────────────────

export interface Posicion {
  activo:        string;
  fracciones:    number;
  precio_hoy:    number;
  valor_hoy:     number;
  invertido:     number;
  ganancia:      number;
  rentabilidad:  number;
}

export interface TiempoReal {
  posiciones:          Posicion[];
  total_invertido:     number;
  total_valor:         number;
  ganancia_total:      number;
  rentabilidad_total:  number;
}

export interface Macro {
  trm:        number;
  trm_cambio: number;
  inf_col:    number;
  inf_usa:    number;
  risk_free:  number;
  banrep:     number;
  tasa_eur:   number;
  cdt:        number;
  spread:     number;
  trm_hist:   { fechas: string[]; valores: number[] };
}

export interface HistoricoEntry {
  fecha:   string;
  macro:   { trm: number };
  resumen: { total_valor: number; total_invertido: number; ganancia_total: number; rentabilidad_total: number };
}

export interface DashboardData {
  portafolio:  { nombre: string; propietario: string; perfil: string; fecha_inicio: string; monitoreo_activo: boolean };
  composicion: Record<string, number>;
  tiempo_real: TiempoReal | null;
  historico:   HistoricoEntry[];
  macro:       Macro | null;
}

export const getDashboard = (archivo: string) =>
  apiFetch<DashboardData>(`/api/dashboard/${archivo}`);

export const getTrmAnalisis = () =>
  apiFetch<{ analisis: string; fecha: string; cacheado?: boolean }>("/api/trm-analisis");

// ── Profile ─────────────────────────────────────────────────

export const getProfile = () =>
  apiFetch<{ username: string; email: string; telegram_chat_id: string; email_notifications: boolean }>("/api/profile");

export const updateProfile = (data: Record<string, unknown>) =>
  apiFetch<{ ok: boolean; mensaje: string }>("/api/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });

// ── Monitor / prices ────────────────────────────────────────

export const getPreciosRT = (archivo: string) =>
  apiFetch<{ ok: boolean; precios: Record<string, unknown>; mercado_abierto: boolean; ultimo_update: string }>(
    `/api/precios-rt/${archivo}`
  );

export const triggerRecolector = () =>
  apiFetch<{ ok: boolean }>("/api/recolector", { method: "POST" });

export const getUltimaActualizacion = () =>
  apiFetch<{ timestamp: string }>("/api/ultima-actualizacion");

// ── Config ──────────────────────────────────────────────

export const getConfig = (archivo: string) =>
  apiFetch<{ nombre: string; activo: boolean; divisa: string; perfil: string; propietario: string; fecha_inicio: string }>(`/api/config/${archivo}`);

export const updateConfig = (archivo: string, data: { divisa?: string; nombre?: string }) =>
  apiFetch<{ ok: boolean; mensaje: string; divisa: string; nombre: string }>(`/api/config/${archivo}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

// ── Seguimiento ─────────────────────────────────────────

export interface Aporte {
  fecha:      string;
  activo:     string;
  monto_usd:  number;
  monto_cop:  number;
  precio_usd: number;
  trm_dia:    number;
  fracciones: number;
  tipo:       string;
}

export interface SeguimientoData {
  nombre:      string;
  composicion: Record<string, number>;
  progreso:    { entrados: number; total: number; pct: number };
  pendientes:  { activo: string; peso: number; precio_usd: number }[];
  entrados:    string[];
  aportes:     Aporte[];
}

export const getSeguimiento = (archivo: string) =>
  apiFetch<SeguimientoData>(`/api/seguimiento/${archivo}`);

export const registrarCompra = (archivo: string, data: {
  activo:     string;
  fecha:      string;
  monto_usd:  number;
  fracciones: number;
}) =>
  apiFetch<SeguimientoData>(`/api/seguimiento/${archivo}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
