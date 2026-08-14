export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: Record<string, unknown>) {
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
  if (!res.ok) throw new ApiError(res.status, (data.error as string) ?? "Error desconocido", data);
  return data as T;
}

// ── Auth ────────────────────────────────────────────────────
export const authVerifyPin = (email: string, pin: string) =>
  apiFetch<{ ok: boolean; username: string }>("/api/auth/verify-pin", {
    method: "POST", body: JSON.stringify({ email, pin }),
  });

export const authResendPin = (email: string) =>
  apiFetch<{ ok: boolean }>("/api/auth/resend-pin", {
    method: "POST", body: JSON.stringify({ email }),
  });

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
  fecha_inicio:  string;
  precio_hoy:    number;
  valor_hoy:     number;
  invertido:     number;
  ganancia:      number;
  rentabilidad:  number;
  fx_cop:        number | null;
  inflacion_cop: number | null;
}

export interface TiempoReal {
  posiciones:          Posicion[];
  total_invertido:     number;
  total_valor:         number;
  ganancia_total:      number;
  rentabilidad_total:  number;
  fx_cop_total:        number | null;
  inflacion_cop_total: number | null;
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

export interface DesviacionComposicion {
  aplica:              boolean;
  progreso_pct:        number;
  necesita_rebalanceo?: boolean;
  desviacion_total_pp?: number;
  activos_desviados?:  Record<string, number>;
}

export interface DashboardData {
  portafolio:  { nombre: string; propietario: string; perfil: string; fecha_inicio: string; monitoreo_activo: boolean };
  composicion: Record<string, number>;
  tiempo_real: TiempoReal | null;
  saldo_usd:   number;
  historico:   HistoricoEntry[];
  macro:       Macro | null;
  desviacion_composicion: DesviacionComposicion | null;
}

export const getDashboard = (archivo: string) =>
  apiFetch<DashboardData>(`/api/dashboard/${archivo}`);

export const getTrmAnalisis = () =>
  apiFetch<{ analisis: string; fecha: string; cacheado?: boolean }>("/api/trm-analisis");

export const getHistoricoAnalisis = (archivo: string) =>
  apiFetch<{ analisis: string; fecha: string; cacheado?: boolean }>(`/api/historico-analisis/${archivo}`);

// ── Profile ─────────────────────────────────────────────────

export const getProfile = () =>
  apiFetch<{ username: string; email: string; telegram_chat_id: string; email_notifications: boolean }>("/api/profile");

export const updateProfile = (data: Record<string, unknown>) =>
  apiFetch<{ ok: boolean; mensaje: string }>("/api/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });

// ── Monitor / prices ────────────────────────────────────────

export interface PrecioRT {
  precio:         number;
  cambio_dia:     number;
  senal:          string;
  score:          number;
  rsi:            number;
  ma20:           number;
  ma50:           number;
  rango_entrar?:  number | null;
  rango_vigilar?: number | null;
  puede_entrar:   boolean;
  banda_inf:      number;
  tendencia:      number;
  vol_ratio:      number;
  macd_hist:      number;
  hist_subiendo:  boolean;
  score_base:     number;
  puede_vigilar:  boolean;
  mercado_rt:     boolean;
  timestamp:      string;
  // ── Venta (nuevo) ──
  banda_sup?:        number | null;
  rango_vender?:      number | null;
  puede_vender?:      boolean;
  costo_promedio?:    number | null;
  ganancia_pct?:      number | null;
  senal_venta?:       string;
  monitorea_compra?:  boolean;
  monitorea_venta?:   boolean;
}

// Rango de entrada/vigilancia precalculado para el día — lo que el backend
// expone cuando no hay precios en vivo (mercado cerrado). Ver dashboard.py
// /api/precios-rt/<archivo> y monitor.py (rangos_hoy).
export interface RangoTicker {
  ma20:           number;
  ma50:           number;
  banda_inf:      number;
  rsi:            number;
  tendencia:      number;
  vol_ratio:      number;
  macd_hist:      number;
  hist_subiendo:  boolean;
  score_base:     number;
  rango_entrar:   number | null;
  rango_vigilar:  number | null;
  puede_entrar:   boolean;
  puede_vigilar:  boolean;
  // ── Venta (nuevo) ──
  banda_sup?:         number | null;
  score_venta_base?:  number;
  rango_vender?:      number | null;
  puede_vender?:      boolean;
  costo_promedio?:    number | null;
}

// Activación granular de monitoreo por activo -- compra y venta son
// independientes, un activo puede tener ambas en true a la vez.
export interface MonitoreoActivo {
  compra: boolean;
  venta:  boolean;
}
export type MonitoreoMap = Record<string, MonitoreoActivo>;

// Ticker que salió de la composición vigente pero el usuario aceptó seguir
// sosteniendo (ver api_aplicar_propuesta) -- puede seguir togglando compra/venta.
export interface ActivoFueraMeta {
  fecha_salida:  string;
  peso_anterior: number;
}
export type ActivosFueraMetaMap = Record<string, ActivoFueraMeta>;

export const getPreciosRT = (archivo: string) =>
  apiFetch<{
    ok:              boolean;
    precios:         Record<string, PrecioRT>;
    mercado_abierto: boolean;
    ultimo_update:   string;
    rangos:          Record<string, RangoTicker>;
    rangos_fecha:    string;
    // Cuántas veces hoy una entrada se disparó sin confirmación de momentum
    // MACD (score suficiente, pero histograma MACD sin girar al alza). Ver
    // monitor.py, vigilar_precios() y dashboard.py /api/precios-rt.
    macd_sin_confirmacion_total?: number;
    error?:          string;
    composicion?:          Record<string, number>;
    tickers_con_posicion?: string[];
    monitoreo?:            MonitoreoMap;
    activos_fuera_meta?:   ActivosFueraMetaMap;
  }>(`/api/precios-rt/${archivo}`);

// ambito="activo" requiere `activo`; ambito="portafolio" aplica a toda la
// composición (compra) o solo a los tickers con posición viva (venta).
export const toggleMonitoreo = (
  archivo: string,
  body: { ambito: "portafolio" | "activo"; activo?: string; tipo: "compra" | "venta"; valor: boolean }
) =>
  apiFetch<{ ok?: boolean; monitoreo?: MonitoreoMap; error?: string }>(`/api/monitor/${archivo}/toggle`, {
    method: "POST",
    body: JSON.stringify(body),
  });

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
export interface Deposito {
  id:        string;
  fecha:     string;
  monto_cop: number;
  trm_real:  number;
  monto_usd: number;
  tipo:      string;   // "deposito" | "apertura"
}

export interface Venta {
  id:                     string;
  fecha:                  string;
  activo:                 string;
  fracciones:             number;
  precio_venta_usd:       number;
  comision:               number;
  proceeds_usd:           number;
  trm_dia:                number;
  costo_base_cop:         number;
  ganancia_realizada_cop: number;
  tipo:                   string;
}

export interface Aporte {
  id:         string;
  fecha:      string;
  activo:     string;
  monto_usd:  number;
  monto_cop:  number;
  precio_usd: number;
  trm_dia:    number;
  trm_real?:  number;   // TRM real de compra — solo referencia, no entra al cálculo
  fracciones: number;
  tipo:       string;
  comision?:  number;   // USD; sale del saldo, no entra al costo/valor
}

// "congelada": snapshot fijo del momento en que se aplicó la composición
// vigente -- nunca se recalcula, sirve para auditar qué tan bien predijo el
// modelo. "viva": mismo motor, recalculada bajo demanda cada vez que se abre
// Seguimiento (ver plan Seguimiento 2026-08-14).
export interface MetricaPortafolio {
  retorno_anual: number;
  volatilidad:   number;
  max_drawdown:  number;
  sharpe?:       number;
  fecha?:        string;   // solo en congelada: cuándo se congeló
  meses_considerados?: number;
  desde?:        string;
}

export type EstadoActivo = "en_meta" | "fuera_meta_con_posicion";

export interface MetricaActivo {
  activo:                       string;
  estado:                       EstadoActivo;
  peso_meta:                    number | null;
  peso_real:                    number | null;
  rentabilidad_real:            number | null;
  volatilidad_real:             number | null;
  drawdown_real:                number | null;
  sortino_historico_motor:      number | null;
  volatilidad_historica_motor:  number | null;
}

// Un panel de comparación proyectado-vs-real, para un universo de activos
// dado (objetivo = solo meta vigente; actual = todo lo que se sostiene hoy).
export interface PanelComparacion {
  proyeccion_congelada?: MetricaPortafolio | null;  // solo en "objetivo"
  proyeccion_viva:       MetricaPortafolio | null;
  real:                  MetricaPortafolio | null;
}

export interface ComparacionSeguimiento {
  composicion_meta: Record<string, number>;
  composicion_real: Record<string, number>;
  por_activo:        MetricaActivo[];
  desviacion_composicion: DesviacionComposicion | null;
  objetivo: PanelComparacion;  // panel "Portafolio objetivo" -- solo en meta
  actual:   PanelComparacion;  // panel "Portafolio real" -- todo lo sostenido
}

export interface SeguimientoData {
  nombre:      string;
  composicion: Record<string, number>;
  progreso:    { entrados: number; total: number; pct: number };
  pendientes:  { activo: string; peso: number; precio_usd: number }[];
  entrados:    string[];
  aportes:     Aporte[];
  depositos:   Deposito[];
  saldo_usd:   number;
  ventas:      Venta[];
  realizado:   { por_ticker: Record<string, number>; total: number };
  comparacion: ComparacionSeguimiento;
}

export const getSeguimiento = (archivo: string) =>
  apiFetch<SeguimientoData>(`/api/seguimiento/${archivo}`);

export const registrarCompra = (archivo: string, data: {
  activo:     string;
  fecha:      string;
  monto_usd:  number;
  fracciones: number;
  trm_real?:  number;
  comision?:  number;
}) =>
  apiFetch<SeguimientoData>(`/api/seguimiento/${archivo}`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const editarAporte = (archivo: string, id: string, data: {
  activo:     string;
  fecha:      string;
  monto_usd:  number;
  fracciones: number;
  trm_real?:  number;
  comision?:  number;
}) =>
  apiFetch<{ ok: boolean }>(`/api/seguimiento/${archivo}/aporte/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const eliminarAporte = (archivo: string, id: string) =>
  apiFetch<{ ok: boolean }>(`/api/seguimiento/${archivo}/aporte/${id}`, {
    method: "DELETE",
  });

export const crearDeposito = (archivo: string, data: {
  fecha:     string;
  monto_cop: number;
  trm_real:  number;
}) =>
  apiFetch<{ ok: boolean }>(`/api/depositos/${archivo}`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const editarDeposito = (archivo: string, id: string, data: {
  fecha:     string;
  monto_cop: number;
  trm_real:  number;
}) =>
  apiFetch<{ ok: boolean }>(`/api/depositos/${archivo}/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const eliminarDeposito = (archivo: string, id: string) =>
  apiFetch<{ ok: boolean }>(`/api/depositos/${archivo}/${id}`, {
    method: "DELETE",
  });

export const crearVenta = (archivo: string, data: {
  activo:           string;
  fecha:            string;
  fracciones:       number;
  monto_usd:        number;
  comision?:        number;
}) =>
  apiFetch<{ ok: boolean }>(`/api/ventas/${archivo}`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const editarVenta = (archivo: string, id: string, data: {
  activo:           string;
  fecha:            string;
  fracciones:       number;
  monto_usd:        number;
  comision?:        number;
}) =>
  apiFetch<{ ok: boolean }>(`/api/ventas/${archivo}/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const eliminarVenta = (archivo: string, id: string) =>
  apiFetch<{ ok: boolean }>(`/api/ventas/${archivo}/${id}`, {
    method: "DELETE",
  });

export interface AdminUsuario {
  username:            string;
  email:               string;
  es_admin:            boolean;
  fecha_registro:      string;
  ultimo_login:        string;
  intentos_fallidos:   number;
  bloqueado:           boolean;
  email_notifications: boolean;
  n_portafolios:       number;
}
 
export interface ActividadEntry {
  tipo:        string;
  username:    string;
  email:       string;
  detalle:     string;
  ip:          string;
  dispositivo: string;
  fecha:       string;
}
 
// ── Lecturas ──
 
export const adminListarUsuarios = () =>
  apiFetch<{ ok: boolean; usuarios: AdminUsuario[]; total: number }>(
    "/api/admin/usuarios"
  );
 
export const adminActividad = (limite = 50, tipo?: string) => {
  const params = new URLSearchParams({ limite: String(limite) });
  if (tipo) params.set("tipo", tipo);
  return apiFetch<{
    ok: boolean;
    actividad: ActividadEntry[];
    total: number;
    resumen_tipos: Record<string, number>;
  }>(`/api/admin/actividad?${params.toString()}`);
};
 
// ── Acciones (rutas que ya existian en el backend) ──
 
export const adminEliminarUsuario = (username: string) =>
  apiFetch<{ ok: boolean; error?: string }>("/api/admin/eliminar-usuario", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
 
// El backend genera una clave temporal fija (cambiar123) y la devuelve en 'mensaje'.
// No se le manda contraseña nueva.
export const adminResetPassword = (username: string) =>
  apiFetch<{ ok: boolean; mensaje?: string; error?: string }>(
    "/api/admin/reset-password",
    { method: "POST", body: JSON.stringify({ username }) }
  );
 
export const adminDesbloquear = (username: string) =>
  apiFetch<{ ok: boolean; error?: string }>("/api/admin/desbloquear", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
 
export const adminToggleAdmin = (username: string, es_admin: boolean) =>
  apiFetch<{ ok: boolean; error?: string }>("/api/admin/toggle-admin", {
    method: "POST",
    body: JSON.stringify({ username, es_admin }),
  });

  export const eliminarPortafolio = (archivo: string) =>
  apiFetch<{ ok: boolean; error?: string }>(`/api/eliminar-portafolio/${archivo}`, {
    method: "POST",
  });

  export const eliminarCuenta = () =>
  apiFetch<{ ok: boolean; error?: string }>("/api/eliminar-cuenta", { method: "POST" });
 