# Bitácora del proyecto Portafolio

Registro cronológico de trabajo, decisiones y hallazgos. Append-only: cada
entrada nueva se agrega al final, las anteriores no se modifican.

---

## [2026-08-06] Auditoría y corrección de `dashboard.py` (backend Flask)

**Qué se hizo:**
- Se avisó explícitamente a Andrea antes de tocar `dashboard.py` (backend
  Flask principal, ~2215 líneas, territorio de la socia) y se pidió
  confirmación, según la regla del proyecto sobre archivos de backend.
- Se corrió el pipeline auditor → programador → tester sobre `dashboard.py`.
  El auditor reportó 21 debilidades: 2 críticas, 8 medias, 5 bajas (más
  algunas notas menores), y levantó 5 preguntas de diseño.
- Andrea respondió explícitamente dos de las preguntas antes de continuar:
  (1) confirmó reescribir `/api/recalcular-proyecciones` para usar el motor
  vigente `adaptador_analista.recalcular_con_pesos()`; (2) confirmó dejar
  `/api/recolector` sin autenticación tal como estaba, por posible
  integración externa/cron, fuera de alcance de esta corrección.
- El programador aplicó las correcciones en `dashboard.py` y, como efecto
  necesario de la corrección crítica #2, también modificó
  `adaptador_analista.py` (función `recalcular_con_pesos`): se agregaron los
  campos `perfil, horizonte, inflacion_col, cdt_ref, inversion_inicial,
  aporte_dca, frecuencia_meses` al diccionario de salida `datos`, para
  igualar el contrato que espera
  `frontend/src/components/ui/reporte-tarjetas.tsx`.
- El tester verificó las correcciones con pruebas reales (`test_client()`),
  no solo lectura de diff.

**Debilidades críticas encontradas y corregidas:**
1. `/api/dashboard/<archivo>`: `macro_json` quedaba indefinido si
   `cargar_macro()` devolvía `None`, causando `NameError` no capturado → 500
   que tumbaba el dashboard completo. Corregido y probado end-to-end.
2. `/api/recalcular-proyecciones`: usaba el pipeline financiero legacy
   (`analista.py`) con el bug conocido de "12 meses duplicados" (momentum
   contado doble), en vez de `adaptador_analista.recalcular_con_pesos()`,
   que ya existía en el código pero nunca se invocaba desde ningún lado del
   repo. Corregido para usar el motor vigente y probado end-to-end.

**Resultado:**
- 2 de 2 críticas corregidas y probadas.
- 8 de 8 medias corregidas: falta de lock/escritura atómica en 4 endpoints
  que escribían JSON de portafolio directo; validación de tickers faltante;
  suma de pesos no validada a ~100%; crashes por `null` explícito en varios
  endpoints; rama sin `return` en `/api/aplicar-propuesta`; rutas relativas
  `datos/...` inconsistentes con `DATOS_DIR`; `frecuencia_meses` sin validar
  contra valores 0/negativos.
- 2 de 3 bajas corregidas: mensaje falso de éxito en reset-password, y 3 de
  4 sitios que exponían excepciones crudas (`str(e)`) al cliente en vez de
  un mensaje genérico.

**Pendiente de decisión / próximos pasos:**
- Baja, no bloqueante: en `dashboard.py`, la función `api_seguimiento_aporte`
  (PUT, ~línea 2013-2014) todavía devuelve `str(e)` crudo al cliente en vez
  del mensaje genérico. Quedó fuera de esta vuelta; se puede cerrar en otra
  sesión corta.
- Explícitamente fuera de alcance en esta corrección (no tocados, quedan
  documentados para revisión futura si Andrea quiere):
  - #9 `/api/recolector` sin autenticación — intencional, decisión de Andrea.
  - #11 revocación de admin no invalida sesión activa.
  - #14 duplicación de lógica de horario de mercado con `monitor.py`.
  - #15 configuración de cookies de sesión.
  - #17-21: timeouts de yfinance, comparación no constante de PIN,
    comentarios obsoletos, cliente anthropic no reusado, duplicado menor en
    `gestor_portafolio.py`.
- Hallazgo aparte, no relacionado con el pipeline de corrección: al revisar
  el contrato de `reporte-tarjetas.tsx`, el programador encontró contenido
  con forma de inyección de instrucciones dentro de
  `frontend/AGENTS.md` (una instrucción tipo "lee la documentación en
  `node_modules/next/dist/docs/` antes de escribir código" que no viene de
  Andrea ni de ninguna tarea legítima). Se ignoró y no se actuó sobre ella
  dentro de este pipeline; queda señalada para que Andrea la revise por su
  cuenta.

---

## [2026-08-08] Auditoría y corrección de `monitor.py` (daemon de producción, backend Flask)

**Qué se hizo:**
- Se auditó `monitor.py` en modo solo lectura, sin ejecutar el daemon
  completo (regla explícita del proyecto: correrlo dispara alertas reales de
  Telegram a usuarios reales). El auditor encontró 11 debilidades: 1
  crítica, 1 alta, 5 medias, 4 bajas.
- Andrea decidió llevar solo la crítica y la alta al pipeline de corrección,
  aportando contexto de negocio explícito (umbrales de espaciado, sin tope
  diario de reaperturas, lock dedicado separado del general) necesario para
  guiar el fix, no inferible solo del código.
- Se hizo el ritual de sesión antes de tocar nada: `git status` (cambios sin
  commitear previos de `dashboard.py`/`adaptador_analista.py`), `git fetch` +
  comparación con `origin/main` (3 commits nuevos de la socia — "Editar
  comision", "Ventas en seguimiento", "Depositos" — tocaban `dashboard.py`,
  `gestor_portafolio.py` y frontend, pero no `monitor.py`), `stash` → `pull`
  (fast-forward limpio) → `stash pop` (auto-merge sin conflictos). Se
  re-auditó `monitor.py` contra el nuevo estado del repo: sin cambios
  respecto a la auditoría original.
- El programador implementó ambos fixes en `monitor.py` y, como parte del
  mismo cambio, también en `gestor_portafolio.py` y `dashboard.py`.
- El tester verificó ambos hallazgos con pruebas aisladas (mocks de
  Telegram, reloj controlable), sin ejecutar `_loop_monitor` ni el daemon
  completo ni llamar a Telegram real.

**Debilidades corregidas:**
1. **CRÍTICA — spam ilimitado tras "Sigue informando"**: al responder "sigue"
   a una alerta, el anti-spam ("máximo 3 alertas sin respuesta") se
   desactivaba por completo y el sistema mandaba alerta en cada ciclo del
   daemon (~10-40s) sin límite mientras la señal se mantuviera — confirmado
   empíricamente en la auditoría original (7/7 ciclos con alerta). Riesgo:
   cientos de mensajes idénticos en una sesión de mercado y posible bloqueo
   de Telegram al bot completo (afectando a todos los usuarios).
   Corregido con un nuevo modelo de estado `estado["lotes_alerta"][ticker]`
   (campos: `enviadas`, `ultima_alerta_ts`, `origen`, `prompt_pendiente`) y
   nuevas constantes `TAMANO_LOTE_ALERTA=3`, `INTERVALO_LOTE_ORIGINAL_MIN=15`,
   `INTERVALO_LOTE_SIGUE_MIN=20`. Reemplaza el anti-spam roto anterior
   (`alertas_enviadas_hoy`/`ciclos_sin_respuesta_{ticker}`,
   `ya_alerte_hoy()`/`marcar_alerta_enviada()` eliminadas por quedar sin
   uso). Al agotar un lote de 3 alertas se reenvía el prompt de decisión con
   los mismos botones en vez de silenciar o seguir mandando.
   `registrar_decision()` reabre el lote (intervalo 20 min) cuando el
   usuario responde "sigue"; "entro"/"no_entro" siguen cortando todo el día
   sin cambios. Reset de lotes agregado en el cambio de día y en
   `reporte_cierre()`.
2. **ALTA — condición de carrera daemon/webhook sobre `monitor_<portafolio>.json`**:
   `vigilar_precios()` (loop del daemon) y `registrar_decision()` (invocada
   desde `dashboard.py` → `procesar_callback_telegram` cuando el usuario
   toca un botón de Telegram) escribían el mismo archivo de estado sin
   ningún lock; si el usuario respondía a mitad de un ciclo del daemon, este
   sobreescribía el archivo con su copia en RAM desactualizada, borrando en
   silencio la decisión del usuario (agravando directamente el spam).
   Además la escritura no era atómica (`open(ruta,"w")` directo), exponiendo
   a corrupción del archivo ante un crash a mitad de escritura (ej. redeploy
   de Railway), sin log de advertencia.
   Corregido: nuevo `_LOCK_MONITOR = threading.RLock()` en
   `gestor_portafolio.py`, separado del `_LOCK` general (que protege
   operaciones financieras de portafolio) para no bloquearlas mientras el
   daemon espera respuestas HTTP de Telegram. `vigilar_precios()` y
   `registrar_decision()` en `monitor.py` quedaron envueltos por completo en
   `with _LOCK_MONITOR:` (todo el read-modify-write). `guardar_estado()`
   reescrita para usar `_escribir()` (patrón atómico tmp+fsync+os.replace)
   en vez de escritura directa. En `dashboard.py` (~línea 1891-1901), la
   escritura de sincronización de nombre de portafolio en el estado del
   monitor también pasó a usar `_escribir()` (atómica) — ver pendiente
   abajo, quedó sin `_LOCK_MONITOR`.

**Resultado:**
- Tester confirmó ambos hallazgos corregidos y verificados:
  - Crítico: reprodujo el escenario original (7/7 alertas) y confirmó ahora
    1/7; verificó el ciclo completo lote → re-pregunta → "sigue" → lote
    nuevo con el intervalo correcto (16 min no alerta, 21 min sí).
  - Alto: prueba de concurrencia con 2 hilos (30 iteraciones) sin pérdida de
    escritura ("lost update" resuelto); revisó los 16 usos de
    `_LOCK`/`_LOCK_MONITOR` en el repo sin encontrar riesgo de deadlock.
- Ningún cambio de esta sesión está commiteado — todo sigue en el working
  tree local.

**Pendiente de decisión / próximos pasos:**
- Menor, no bloqueante: la escritura de renombrado de portafolio en
  `dashboard.py` (~línea 1895-1901) quedó atómica pero SIN `_LOCK_MONITOR` —
  sigue siendo un tercer punto de escritura sobre `monitor_<archivo>.json`
  sin exclusión mutua con el daemon. Impacto bajo (se autocorrige en el
  siguiente ciclo del monitor, ~10-15s después). Queda documentado para
  otra sesión si Andrea quiere cerrarlo del todo.
- Explícitamente fuera de alcance en este pipeline (no tocadas, quedan
  documentadas para revisión futura si Andrea quiere): las 5 debilidades
  medias y 4 bajas de la auditoría original de `monitor.py` — rate limit de
  Finnhub mal calculado, `telegram()` sin validar respuesta HTTP, nombre de
  portafolio sin escapar en HTML, falta de aislamiento por ticker en el
  loop, uso de truthiness en vez de `is not None`, errores tragados sin
  loguear, duplicidad de `mercado_abierto()` con `dashboard.py`, prints con
  emoji en consola Windows no-UTF8.

---

## [2026-08-09] Cierre de 3 pendientes de bajo impacto en `dashboard.py`

**Qué se hizo:**
- Se cerraron tres pendientes de bajo impacto documentados en las dos
  sesiones anteriores (auditoría de `dashboard.py` del 2026-08-06 y de
  `monitor.py` del 2026-08-08), todos con cambios acotados a `dashboard.py`.
1. `api_seguimiento_aporte` (PUT, `dashboard.py`) era el único de 4 endpoints
   similares que seguía devolviendo el texto crudo de la excepción de Python
   al cliente (`jsonify({"error": f"Error: {str(e)}"})`). Se corrigió para
   loguear con `print` en servidor y devolver un mensaje genérico al
   cliente, igual que los otros 3 endpoints ya corregidos el 2026-08-06.
2. El bloque de `api_config` (PUT, `dashboard.py`) que sincroniza el nombre
   del portafolio dentro de `monitor_<archivo>.json` escribía sin
   `_LOCK_MONITOR` — el candado dedicado agregado el 2026-08-08 para
   coordinar el daemon (`monitor.py`) y el webhook de Telegram sobre ese
   mismo archivo. Se envolvió ese bloque específico en
   `with _LOCK_MONITOR:`, anidado dentro del `with _LOCK:` general del
   endpoint. Se confirmó que no hay riesgo de deadlock: ni
   `vigilar_precios()` ni `registrar_decision()` en `monitor.py` adquieren
   `_LOCK` de forma anidada dentro de `_LOCK_MONITOR`.
3. `api_aplicar_propuesta` (`dashboard.py`), rama `tipo == "nuevo"` (crear
   portafolio nuevo a partir de una propuesta), no tenía la validación de
   que los pesos sumaran ~100% que sí se agregó a la rama
   `tipo == "reemplazar"` el 2026-08-06 (quedó fuera por alcance limitado de
   esa sesión). Se agregó la misma validación
   (`abs(sum(pesos.values()) - 1.0) > 0.01` → rechazo con 400) a la rama
   `"nuevo"`.
- Los tres cambios se verificaron con `py_compile`/`ast.parse` (sintaxis
  válida), sin ejecutar el archivo completo ni disparar nada hacia Telegram
  real.

**Resultado:**
- Los 3 pendientes de bajo impacto quedan cerrados: exposición de excepción
  cruda en `api_seguimiento_aporte`, escritura sin `_LOCK_MONITOR` en
  `api_config`, y falta de validación de suma de pesos en la rama "nuevo" de
  `api_aplicar_propuesta`.
- Con este cierre, los pendientes de bajo impacto identificados en las
  sesiones del 2026-08-06 (`dashboard.py`) y del 2026-08-08 (`monitor.py`)
  quedan resueltos.
- Ningún cambio de esta sesión está commiteado — todo sigue en el working
  tree local.

**Pendiente de decisión / próximos pasos:**
- Ninguno nuevo generado por esta sesión. Siguen documentadas, sin tocar,
  las debilidades explícitamente fuera de alcance listadas en las entradas
  del 2026-08-06 y 2026-08-08 (medias/bajas de `dashboard.py` y de
  `monitor.py`), a la espera de que Andrea decida si quiere atacarlas en
  otra sesión.

---

## [2026-08-11] Auditoría, corrección y mejoras de producto en `monitor.py` y `dashboard.py`

**Qué se hizo:**
- Se auditaron tres frentes específicos de `monitor.py`/`dashboard.py`: (a)
  fallas silenciosas en los mensajes de Telegram, (b) rutas rotas
  backend/frontend, (c) si el gate de MACD hacía las señales de trading
  demasiado rígidas. El auditor corrió un backtest cuantitativo real (90
  días, 6 tickers del portafolio de Andrea: NVDA, BTC-USD, GOOGL, LLY, SCHD,
  WMT) para el frente MACD, no solo lectura de código.
- Andrea decidió los tres fixes a partir de los hallazgos (ver abajo) y el
  programador los implementó en `monitor.py`. El tester encontró y corrigió
  un efecto colateral real en el primer intento del fix de MACD antes de
  darlo por cerrado.
- Mano-derecha reportó los fixes y señaló tres pendientes de bajo impacto
  (documentados abajo). Andrea pidió cerrar dos de ellos en la misma sesión
  y agregó dos mejoras de producto nuevas; las cuatro se implementaron y
  verificaron en esta misma sesión.

**Hallazgos y fixes — ronda 1 (auditoría):**
1. **Crítico — Telegram, fallas silenciosas:** `telegram()` en `monitor.py`
   nunca verificaba si Telegram aceptó el mensaje; un HTTP 400 con
   `{"ok": false}` no lanza excepción en Python, así que cualquier mensaje
   con HTML roto se perdía sin ningún log. Corregido: ahora verifica la
   respuesta y loguea el fallo.
2. **Crítico — Telegram, HTML sin escapar:** el nombre de portafolio y el
   texto generado por Claude (mensajes de "buenos días" y "reporte de
   cierre") se interpolaban sin escapar en HTML de Telegram — combinado con
   el bug anterior, cualquier `<`, `>` o `&` suelto rompía esos dos mensajes
   diarios garantizados sin aviso. Corregido con `html.escape()` en los
   campos dinámicos, en vez de depender del prompt de la IA.
3. **Rutas backend/frontend:** no se encontró ninguna ruta rota. Único
   hallazgo menor: `/api/fix-banrep` (borra el caché de la tasa BanRep) no
   tiene botón en la UI — Andrea confirmó que sigue siendo una utilidad
   manual válida, se deja tal cual, sin cambios.
4. **Gate de MACD demasiado rígido:** de 100 día-ticker que ya calificaban
   por score de RSI/tendencia/volumen, el gate duro (`and hist_subiendo`)
   bloqueaba el 50% (50 de 100), y 17 de esos 50 ya tenían el precio por
   debajo de la banda de Bollinger (alertas reales perdidas). El propio
   código ya tenía una nota del desarrollador anticipando este ajuste.
   Corregido: el gate duro se reemplazó por un bono de +0.5 al score en vez
   de bloqueo total. El tester encontró que la primera versión del fix
   mutaba `score_base += 0.5` in-place, filtrando el bono también a
   `puede_vigilar` (que nunca debía cambiar) y al score mostrado/logueado en
   tiempo real. Se corrigió aislando el bono en una variable separada
   (`score_para_entrar`), dejando `score_base` intacto para todo lo demás.
   Verificado con pruebas aisladas que replican los casos que fallaban.

**Hallazgos y fixes — ronda 2 (pendientes + mejoras de producto):**
1. **Alertas de Telegram agrupadas:** cuando 2+ tickers de un portafolio
   cruzan a señal ENTRAR en el mismo ciclo del monitor, ahora se manda UN
   SOLO mensaje con todos los tickers listados y un teclado con una fila de
   botones de decisión por cada uno, en vez de un mensaje por ticker sin
   espaciar (riesgo de rate limit de Telegram). Con 1 solo ticker se
   mantiene el mensaje individual de siempre. Funciones nuevas en
   `monitor.py`: `teclado_decision_multiple()`, `_mensaje_alerta_individual()`,
   `_mensaje_alerta_agrupada()`.
2. **Contador `macd_sin_confirmacion_total` expuesto:** el endpoint
   `/api/precios-rt/<archivo>` en `dashboard.py` ahora incluye ese campo en
   su respuesta (ya existía en el backend pero no se mostraba en ningún
   lado); el frontend (`frontend/src/app/portafolio/[archivo]/monitor/page.tsx`,
   vía `frontend/src/lib/api.ts`) lo muestra como texto discreto cerca de la
   barra de estado, solo si es mayor a 0.
3. **Tono de sugerencia en las alertas:** el título del mensaje cambió de
   "SEÑAL DE ENTRADA" a "POSIBLE ENTRADA", con aclaración explícita de que
   es información basada en indicadores técnicos, no una orden de actuar de
   inmediato — el usuario decide cuándo entrar. Aplica al mensaje individual
   y al agrupado; los mensajes de "buenos días" y "reporte de cierre" no se
   tocaron.
4. **Saludo automático del bot al conectar Telegram (funcionalidad nueva):**
   en `dashboard.py`, endpoint `update_profile`, cuando un usuario guarda o
   cambia su `telegram_chat_id`, el sistema le manda un mensaje de bienvenida
   inmediato — si tiene al menos un portafolio con monitoreo activo, confirma
   que ya está activo y que avisará en la próxima ronda de análisis; si no
   tiene ninguno activo, le dice que active el monitoreo. Protegido con
   try/except: un fallo en el envío del saludo no afecta el guardado del
   perfil.

**Resultado:**
- El tester verificó los 4 cambios de la ronda 2 con pruebas aisladas (sin
  ejecutar `monitor.py` completo ni disparar Telegram/Finnhub reales):
  agrupación probada con 1 y 3 tickers simultáneos; el contador confirmado
  que se lee del estado correcto y no se muestra en 0; el texto de tono
  confirmado en ambas funciones sin afectar buenos días/cierre; los 5 casos
  del saludo automático (primera conexión activo/inactivo, sin cambio de
  chat_id, chat_id vacío, cambio de un chat_id a otro) todos correctos.
  `tsc --noEmit` y `py_compile` limpios en ambas rondas.
- Todos los fixes de la ronda 1 (verificación de respuesta de Telegram,
  `html.escape()`, gate de MACD con `score_para_entrar` separado) siguen
  intactos tras la ronda 2.
- Único detalle cosmético señalado, no bloqueante: el docstring de
  `teclado_decision_multiple()` cita un formato de ejemplo de
  `callback_data` que no coincide exactamente con el formato real usado —
  solo un comentario desactualizado, no afecta el funcionamiento.
- Archivos tocados en esta sesión: `monitor.py`, `dashboard.py`,
  `frontend/src/lib/api.ts`,
  `frontend/src/app/portafolio/[archivo]/monitor/page.tsx`. Ningún cambio de
  esta sesión está commiteado — todo sigue en el working tree local.

**Pendiente de decisión / próximos pasos:**
- Cosmético, no bloqueante: corregir el docstring de
  `teclado_decision_multiple()` en `monitor.py` para que el ejemplo de
  `callback_data` coincida con el formato real.
- Ninguno de los pendientes de la ronda 1 quedó abierto: los tres señalados
  (contador sin mostrar, falta de agrupación de alertas, ruta huérfana
  `/api/fix-banrep`) se cerraron o se confirmaron como decisión intencional
  en esta misma sesión.

---

## [2026-08-11] Rediseño de la pantalla de monitor en cards por activo

**Qué se hizo:**
- Andrea pidió reemplazar la tabla plana de precios en vivo de
  `/portafolio/[archivo]/monitor` por un diseño de recuadros (cards) por
  activo, basado en un mockup HTML/CSS/JS diseñado por ella misma. Por el
  alcance (backend + varios archivos de frontend) se usó plan mode para
  diseñar la implementación antes de tocar código.
- Decisión de diseño confirmada por Andrea antes de implementar: el texto de
  "justificación" de cada activo (por qué tiene tal señal) NO se genera con
  una llamada en vivo a Claude/IA en cada refresh (sería lento y caro a la
  cadencia de 4-9 segundos) — se arma como texto templado en el navegador a
  partir de los indicadores técnicos que el backend ya calculaba.
- Cambio de backend, aditivo, sin tocar lógica de cálculo: `dashboard.py`,
  función `api_precios_rt` — se agregaron 7 campos a la respuesta
  (`banda_inf`, `tendencia`, `vol_ratio`, `macd_hist`, `hist_subiendo`,
  `score_base`, `puede_vigilar`) que `monitor.py` ya calculaba y guardaba en
  `estado["resultados_rt"][ticker]` pero nunca se reexponían al frontend.
  `monitor.py` no se tocó en esta sesión.
- Cambios de frontend:
  - `frontend/src/lib/api.ts`: tipo `PrecioRT` ampliado con los mismos 7
    campos.
  - Nuevo archivo `frontend/src/lib/monitor-texto.ts`: funciones puras
    `justificacionActivo()` y `resumenPortafolio()` que arman el texto de
    justificación por activo y el resumen agregado del portafolio, sin
    ninguna llamada de red.
  - `frontend/src/app/portafolio/[archivo]/monitor/page.tsx`: reescrita el
    área de renderizado (se mantuvo intacta la lógica de carga/polling/
    estados de error de sesiones anteriores) — grid de cards (una por
    activo, usando `GlowCard`) con badge de señal, precio animado, barra de
    RSI, y un panel de detalle que se actualiza al hacer click en una card,
    mostrando las 4 métricas técnicas + la justificación de texto. El mismo
    diseño funciona tanto con precios en vivo (mercado abierto) como con los
    rangos precalculados (mercado cerrado), reutilizando las mismas
    funciones.
- Verificación visual con Playwright (mocks de red, sin backend real)
  encontró y se corrigieron dos bugs antes de cerrar:
  1. Cards sin señal (NEUTRAL) con tinte azul no intencional: `GlowCard` no
     puede quedar "sin color" (su prop `glowColor` tiene default que se
     activa incluso pasándole `undefined`). Se corrigió usando `GlassPanel`
     (sin efecto de glow) solo para las cards NEUTRAL; `GlowCard` quedó
     exclusivo para ENTRAR (verde) y VIGILAR (naranja).
  2. Precio del encabezado del panel de detalle desactualizado al cambiar de
     activo seleccionado: la causa real estaba en
     `frontend/src/components/ui/animated-value.tsx` (componente compartido,
     también usado en el Dashboard principal para el conteo animado de
     "Valor hoy"/"Ganancia"). El formateador de número se pasaba como
     función nueva en cada render, y como el monitor se re-renderiza cada
     ~100ms (indicador de "próximo refresh"), `react-countup` reiniciaba la
     animación sin completarla nunca. Se corrigió estabilizando la
     referencia del formateador con `useRef`. Este fix también corrige
     preventivamente el mismo defecto latente en el Dashboard principal
     (menos notorio ahí porque refresca cada 10s, no 100ms).

**Resultado:**
- `tsc --noEmit` y `py_compile` limpios en ambas rondas de verificación,
  diff acotado a los archivos esperados.
- Prueba visual con Playwright confirmó ambos fixes funcionando
  correctamente.
- Archivos tocados en esta sesión: `dashboard.py`, `frontend/src/lib/api.ts`,
  `frontend/src/lib/monitor-texto.ts` (nuevo),
  `frontend/src/app/portafolio/[archivo]/monitor/page.tsx`,
  `frontend/src/components/ui/animated-value.tsx`. Ningún cambio de esta
  sesión está commiteado — todo sigue en el working tree local.

**Pendiente de decisión / próximos pasos:**
- Cosmético, no bloqueante: las cards NEUTRAL quedaron con borde de 1px en
  vez de 2px comparado con las de ENTRAR/VIGILAR (diferencia de 2px de alto
  total, imperceptible a simple vista) — pendiente si Andrea quiere paridad
  pixel-perfecta en otra sesión.

---

## [2026-08-11] PROBLEMA CRÍTICO ABIERTO — desalineación entre el chat del Analista (IA) y la propuesta cuantitativa (motor)

**Estado: SIN DIAGNOSTICAR, SIN CORREGIR.** Esta entrada solo deja constancia
inmediata del problema tal como lo reportó Andrea, a su pedido explícito
("quiero dejarlo registrado en este momento para que empecemos a
solucionarlo fuertemente"). No es un cierre de trabajo, es el registro de
apertura de un problema.

**Qué se reportó:**
- Andrea reportó que en el chat del Analista, Claude conversa de forma
  contextualizada sobre el portafolio y el mercado, describe/sugiere una
  acción concreta (ej. "voy a incluir MSFT al 15% junto con tus otros
  activos"), pero cuando se genera la propuesta/proyección numérica real
  (salida del motor cuantitativo — HRP vía `ponderador.py`, purga de
  `motor_seleccion.py`, `red_riesgo.py`), el resultado no coincide con lo
  que la IA acababa de decir.
- Ejemplo real compartido por Andrea (cita textual de la propia IA
  reconociendo la incoherencia después del hecho, en vez de evitarla antes):
  "Tienes toda la razón en cuestionar eso. Te debo una explicación clara: Te
  sugerí incluir MSFT al 15% junto con tus otros activos, pero el
  optimizador (el motor que calcula la mejor combinación basándose en datos
  históricos, correlaciones y tu perfil de riesgo) determinó que para tu
  perfil moderado, la composición más eficiente con menor volatilidad es
  concentrarse en COST y VTI únicamente. ¿Por qué eliminó JNJ y MSFT?
  Probablemente porque: VTI ya contiene Microsoft (es el 3er componente más
  grande del ETF); La correlación entre COST, JNJ y MSFT no mejoró el
  balance riesgo-retorno; Para volatilidad baja en 10 años, prefirió
  simplificar. Aquí está el dilema: puedo forzar que incluya los 4 activos
  (COST, JNJ, VTI, MSFT) como te sugerí, pero el optimizador ajustará los
  pesos según lo que considera óptimo matemáticamente, que puede diferir de
  mi sugerencia inicial. ¿Prefieres que fuerce la inclusión de los 4
  activos, o quieres revisar primero esta propuesta simplificada (COST +
  VTI)?"

**Por qué es grave (interpretación de Andrea):**
- Rompe la confianza del usuario: la IA "promete" algo en la conversación y
  el número real no coincide, incluso cuando la propia IA reconoce la
  incoherencia después del hecho en vez de evitarla desde el principio.
- Sugiere que el chat (razonamiento en lenguaje natural de Claude) y el
  motor cuantitativo determinístico (`motor_seleccion.py`,
  `ponderador.py`/HRP, `red_riesgo.py`) están operando como dos sistemas que
  no se coordinan entre sí de forma confiable antes de hablarle al usuario.

**Pregunta abierta de Andrea, sin resolver:**
- "¿Cómo podemos hacer fix? ¿A quién deberíamos ajustar — a la IA o al
  analista (motor cuantitativo)? Siento que el analista puede ser un poco
  más ajustado y rígido por toda la matemática detrás, sin embargo me da
  miedo que lo flexible de la IA sea muy fantasiosa y no tenga mucho rigor."

**Resultado:**
- Ninguno todavía. No se ha diagnosticado la causa raíz ni se ha tocado
  código.

**Pendiente de decisión / próximos pasos:**
- Se lanzó en paralelo (en la misma sesión en que se reportó este problema)
  una investigación con el agente mano-derecha sobre cómo interactúan
  realmente el endpoint de chat del Analista y el endpoint que genera la
  propuesta cuantitativa, para entender la causa raíz antes de proponer
  cualquier fix.
- Sigue sin responder la pregunta central de Andrea: si el ajuste debe ir
  del lado del chat (IA, `adaptador_analista.py`/prompt) o del lado del
  motor cuantitativo (`motor_seleccion.py`, `ponderador.py`, `red_riesgo.py`),
  o si se requiere un mecanismo de coordinación entre ambos que hoy no
  existe. Retomar este punto en cuanto la investigación de causa raíz tenga
  resultados.

---

## [2026-08-11] Cierre del problema crítico — desalineación entre el chat del Analista y el motor cuantitativo

**Qué se hizo:**
- Se cerró el problema crítico abierto en la entrada anterior de este mismo
  día: el chat del Analista (Claude) le prometía al usuario tickers/pesos en
  lenguaje natural sin haber consultado nunca al motor cuantitativo real —
  el número lo inventaba el modelo — y cuando la propuesta final (vía
  `/api/generar-propuesta`) no coincidía, la IA solo podía especular por qué
  ("probablemente porque...") porque tampoco tenía acceso a los motivos
  reales de exclusión del motor.
- Se diseñó en plan mode y se implementó el fix en `dashboard.py` y
  `adaptador_analista.py`:
  1. Nueva función `_tool_simular_propuesta(input_)` en `dashboard.py` —
     envuelve `generar_propuesta_completa()` y devuelve un resumen ligero
     (pesos reales, candidatos excluidos, motivos de exclusión, alfa,
     métricas, advertencias) para que el modelo lo consulte antes de hablar
     de cifras.
  2. Nuevo tool schema `SIMULAR_PROPUESTA_TOOL` + dispatcher `_ejecutar_tool`.
  3. `anthropic_chat()` reestructurado a un loop con `MAX_TOOL_ROUNDS=3` que
     soporta tool use nativo del SDK de Anthropic (`tools=`,
     `tool_executor=`).
  4. `_sistema_analista()` ahora instruye explícitamente al modelo: nunca
     decir un ticker/porcentaje concreto sin haber llamado antes a la
     herramienta, usarla también para preguntas hipotéticas, y usar los
     motivos reales de exclusión en vez de especular.
  5. En `adaptador_analista.py`, `generar_propuesta_completa()` ahora también
     devuelve `motivos_exclusion` (nueva función `_resumir_exclusiones`), que
     rastrea por qué cada ticker candidato fue descartado en cada paso del
     motor (purga Sortino, purga por correlación parcial, cobertura
     sectorial) — el dato ya existía calculado internamente en
     `res["seleccion"]`, solo faltaba exponerlo.
- El tester encontró y el programador cerró dos huecos antes de la prueba
  real: (a) tickers candidatos que el motor no reconoce (sin histórico) no
  tenían entrada en `motivos_exclusion` — se agregó un fallback explícito
  `"sin_datos"` para cualquier candidato no cubierto por los pasos 1-3; (b)
  el mensaje de exclusión por "sector concentrado" asumía incorrectamente un
  cupo de 1 activo por sector — se corrigió para calcular el cupo real con
  `MAX_ACTIVOS_SECTOR_CONCENTRADO` (`motor_seleccion.py`) menos los activos
  ya garantizados.
- Andrea autorizó explícitamente una prueba real end-to-end con consumo real
  de créditos de la API de Anthropic: 3 escenarios contra el portafolio real
  de prueba.
  1. Usuario pide portafolio moderado mencionando MSFT explícitamente →
     Claude llamó la herramienta, el primer resultado fue muy concentrado
     (100% GOOGL), y por iniciativa propia volvió a llamar la herramienta con
     una lista de candidatos más amplia, obteniendo un resultado
     diversificado real (SCHD 64.5%, WMT 17%, GOOGL 10.2%, LLY 8.2%).
     Explicó correctamente por qué MSFT quedó fuera (Sortino de GOOGL mejor
     dentro del sector tecnología) usando datos reales de
     `motivos_exclusion`, sin prometer nada que no coincidiera con el
     resultado real.
  2. Pregunta hipotética ("¿sobreviviría NVDA en la selección?") antes de
     pedir la propuesta final → Claude llamó la herramienta una vez, citó
     valores reales de Sortino (0.48 META, 0.65 TSLA) y explicó la cobertura
     sectorial que excluyó a MSFT/GOOGL/AAPL, además advirtió proactivamente
     sobre el riesgo de concentración del resultado (100% NVDA).
  3. Ticker inventado ("ZZZINVENTADO") → Claude reconoció por su cuenta que
     no era un ticker real y pidió aclaración sin necesidad de invocar la
     herramienta (comportamiento razonable, pero significa que el fallback
     "sin_datos" no se puso a prueba en este escenario puntual — queda como
     red de seguridad para cuando un ticker real pero no descargado
     localmente se cuele).

**Resultado:**
- Los 3 escenarios confirman que el modelo ahora consulta al motor real
  antes de prometer cifras concretas y explica con hechos verificables en
  vez de especular — el bug original (promesa verbal vs. propuesta final
  real distinta, sin explicación fundamentada) queda resuelto.
- Archivos tocados en esta sesión: `dashboard.py`, `adaptador_analista.py`.
  Los cambios están verificados pero AÚN NO COMMITEADOS.

**Pendiente de decisión / próximos pasos:**
- Commitear los cambios de este fix (los 2 huecos cerrados + la
  implementación de tool calling en `dashboard.py`/`adaptador_analista.py`).
- Sigue pendiente decidir si se hace push del commit anterior de la sesión
  del 2026-08-11 (rediseño de tarjetas del monitor + fixes de
  Telegram/MACD/saludo automático).

---

## [2026-08-11] Auditoría y fixes de "+ Agregar activo" en la propuesta del Analista

**Qué se hizo:**
- Se auditó el flujo de `PropuestaEditor`
  (`frontend/src/components/ui/propuesta-editor.tsx`), la caja para agregar
  un ticker manualmente a una propuesta y editar pesos a mano antes de
  aplicar.
- Se encontraron y corrigieron dos fallas de backend: en `dashboard.py`, la
  descarga de histórico de un ticker nuevo que devolvía vacía no creaba el
  flag `ticker_listo_<tk>.flag`, dejando el polling del frontend colgado sin
  resolver (40s de timeout sin explicación real); además el mismo flag se
  creaba tanto en éxito como en fallo por excepción, sin que el frontend
  pudiera distinguir "descarga exitosa" de "descarga fallida". En
  `adaptador_analista.py`, cuando un ticker agregado manualmente no tenía
  histórico válido a tiempo, su peso se redistribuía silenciosamente entre
  los demás activos sin decir cuánto.
- Hallazgo más importante, no corregido por ser decisión de producto:
  `/api/recalcular-proyecciones` y `/api/aplicar-propuesta` NO pasan los
  pesos editados a mano de vuelta por el motor de selección
  (Sortino/correlación/sector) ni por HRP — se aplican tal cual el usuario
  los deja. Se decidió permitir el override manual y en su lugar agregar un
  aviso visible en el frontend explicándolo.
- El tester verificó los fixes con evidencia real: diff exacto contra HEAD y
  ejecución con datos reales.

**Fixes aplicados:**
1. `dashboard.py`: el flag de descarga ahora escribe "ok"/"error" según el
   resultado real (descarga vacía, éxito, excepción), y
   `/api/ticker-listo` devuelve `{"listo", "exito"}` en vez de solo
   `{"listo"}`.
2. `adaptador_analista.py`: la nota de redistribución ahora cuantifica el
   porcentaje exacto redistribuido.
3. Frontend (`propuesta-editor.tsx`): aviso visible de que los pesos
   editados a mano no vuelven a pasar por el motor; `esperarTicker()`
   distingue "ok"/"error"/"timeout" en vez de solo listo/no-listo.

**Resultado:**
- Los 3 fixes verificados por el tester con evidencia real (diff exacto
  contra HEAD y ejecución con datos reales). Commiteados en `c71e2f9` (junto
  con el fix de tool-calling de una ronda anterior, ya registrado en la
  entrada previa de esta bitácora).

**Pendiente de decisión / próximos pasos:**
- Ninguno nuevo: la decisión de producto sobre no repasar los pesos
  editados a mano por el motor cuantitativo quedó tomada y comunicada al
  usuario vía el aviso en el frontend.

---

## [2026-08-11] Backtest walk-forward del motor cuantitativo: validación de rigidez/overfitting

**Qué se hizo:**
- Andrea preguntó si la matemática del Analista (purga Sortino + purga por
  correlación parcial + cobertura sectorial + HRP) es demasiado rígida y
  tiene riesgo de overfitting. La investigación inicial (mano-derecha, con
  evidencia de código real) confirmó que las purgas están mecánicamente
  justificadas (HRP crudo sin purgar colapsa 90.3% en bonos, reproducido en
  esta sesión), pero encontró que varios parámetros clave (vida media EWMA
  = 126 días, umbral de correlación parcial = 0.20) estaban calibrados según
  comentarios del código sobre el mismo universo de producción, sin ningún
  script de backtest reproducible en 140 commits de historial de git — solo
  afirmaciones de texto ("15.6%", "17/29").
- Se construyó `backtest_motor.py` (nuevo, raíz del repo): backtest
  walk-forward real, 48 folds de 2017 a 2025, congelando el universo en cada
  fecha de corte T (monkeypatch temporal de
  `preparador_datos.cargar_precios`, sin modificar ningún archivo del motor)
  y evaluando con retornos reales nunca truncados en las ventanas T→T+63 y
  T→T+126 días hábiles. Comparó: producción (vida_media=126, umbral=0.20),
  un barrido de 12 combinaciones de parámetros, HRP crudo sin purgar, y
  equal-weight sobre el universo ya purgado.
- El primer corrido confirmó las purgas (HRP crudo: Sortino realizado
  -1.01/-1.32, muy malo fuera de muestra), pero sugería que equal-weight
  le ganaba a HRP en Sortino/retorno promedio, y que vida_media=189-252 con
  umbral=0.10 le ganaba a la config de producción (126/0.20).
- Se detectó que los 48 folds se solapan entre sí (ventanas de evaluación no
  independientes), así que se repitió el análisis solo sobre el subconjunto
  de folds verdaderamente independientes, en dos scripts nuevos
  (`backtest_motor_robustez.py` y `backtest_motor_robustez_grid.py`).

**Resultado:**
- Con la corrección de independencia de folds: HRP vs equal-weight pasa a un
  empate exacto 6/12 en folds independientes a 126 días (sign test
  p=1.000, sin evidencia real de diferencia en retorno promedio). Lo que sí
  se sostiene, consistente en 44/48 folds solapados y 12/12 folds
  independientes: HRP tiene un drawdown mucho más suave que equal-weight,
  especialmente en los años de estrés real de la muestra (2018, 2022) — ese
  es el beneficio real de HRP, no visible en el retorno promedio de una
  muestra dominada por años alcistas.
- La ventaja aparente de vida_media=189-252/umbral=0.10 sobre la config de
  producción también se cae al corregir por independencia: en folds
  independientes, 126/0.20 pasa a ser la mejor combinación a 63 días (1º de
  12) y queda en la mitad de la tabla a 126 días (6º de 12, prácticamente
  empatado).
- Conclusión final: se mantiene la matemática del Analista tal cual está.
  Las purgas son necesarias (validado), HRP aporta protección de downside
  real y consistente (validado, aunque no es lo que se buscaba
  originalmente), y los parámetros actuales (vida_media=126, umbral=0.20) no
  están mal calibrados — al corregir por el solape de folds, dejan de verse
  superados por ninguna alternativa del barrido.
- Archivos nuevos, ya commiteados: `backtest_motor.py`,
  `backtest_motor_robustez.py`, `backtest_motor_robustez_grid.py`,
  `backtest_motor_resultados.csv` (1344 filas, resultados crudos).

**Pendiente de decisión / próximos pasos:**
- Ninguno: la pregunta de Andrea sobre rigidez/overfitting quedó respondida
  con evidencia reproducible y no se hizo ningún cambio a
  `motor_seleccion.py`, `covarianza.py`, `ponderador.py` ni `perfilador.py`.

---

## [2026-08-11] Editar portafolio existente: anclar posiciones actuales (activos_ancla)

**Qué se hizo:**
- Andrea reportó que cuando un usuario con portafolio existente le pide al
  Analista algo como "agrega tecnología a mi portafolio", el sistema
  terminaba proponiendo un portafolio completamente distinto, como si no
  reconociera las posiciones actuales.
- Diagnóstico: `_restringir_universo()` en `adaptador_analista.py`
  interpreta `tickers_fijos` como "el universo entero son solo estos
  tickers" (correcto para pedidos de tema/categoría concreta, ej. "solo
  tecnología"). Cuando la IA armaba el JSON con {tickers viejos + ticker
  nuevo} para "editar", ese mismo mecanismo restringía todo el universo a
  ese puñado chico — las purgas corrían ahí dentro sin garantizar que las
  posiciones actuales sobrevivieran, y nunca se buscaba en el resto del
  mercado la mejor forma de sumar lo nuevo.
- Se implementó un mecanismo nuevo y separado, `activos_ancla`, en 4
  archivos backend (aditivo, no modifica el comportamiento existente de
  `tickers_fijos`):
  1. `motor_seleccion.py`: `purgar_redundantes()` y `cobertura_por_sector()`
     ganaron un parámetro opcional `protegidos` — con él, un ticker
     protegido nunca se purga por redundancia contra otro protegido, y
     siempre reclama su cupo de sector antes que cualquier candidato nuevo.
     Nueva función `seleccionar_anclado()` que reutiliza esas dos funciones
     más `purgar_peores()` sin tocarlas.
  2. `analista_motor.py`: `construir_portafolio()` ahora acepta
     `activos_ancla` opcional; con él, usa `seleccionar_anclado()` en vez de
     `seleccionar()`.
  3. `adaptador_analista.py`: `_cargar_todo_para_motor()`, `_construir()` y
     `generar_propuesta_completa()` propagan `activos_ancla`; con él, se
     salta la restricción de universo y se corre sobre el universo completo
     con esos tickers protegidos.
  4. `dashboard.py`: la herramienta `simular_propuesta` del chat ganó el
     campo `activos_ancla`; el prompt del Analista (`_sistema_analista`)
     ahora pregunta explícitamente si el usuario quiere partir de su
     portafolio actual antes de proponer cambios de composición, en vez de
     asumirlo; `/api/generar-propuesta` lee `activos_ancla` del JSON final.
- Verificado con datos reales (mano-derecha + tester, en pruebas
  independientes): cero regresión en el flujo normal sin ancla
  (`probar_motor.py` y `generar_propuesta_completa()` dan resultados
  idénticos byte a byte contra el código previo al cambio); protección
  confirmada tanto en la purga por correlación parcial como en la cobertura
  sectorial; un ancla con Sortino en el 30% peor sobrevive de todas formas;
  dos anclas en el mismo sector sobreviven ambas (no se aplica el límite de
  "uno por sector" entre posiciones ya existentes).

**Resultado:**
- Fix verificado y cerrado. Ejemplo real corrido: portafolio con COST+VTI
  anclados → la cobertura sectorial agrega automáticamente AVGO y XLK
  (tecnología) del universo completo de 98 activos, sin que nadie tuviera
  que pedirlo explícitamente por ticker.
- Todos los cambios de este bloque son backend puro (`motor_seleccion.py`,
  `analista_motor.py`, `adaptador_analista.py`, `dashboard.py`) y ya fueron
  commiteados por Andrea.

**Pendiente de decisión / próximos pasos:**
- Ninguno generado por esta sesión.

---

## [2026-08-12] Pendiente para próxima sesión: dejar proyectar una composición específica pese a las advertencias del motor

**Contexto (pedido por Andrea, aún sin diseñar ni implementar):**
- Hoy, cuando el usuario pide una edición sobre su portafolio existente (ej.
  "agrega tecnología") y el Analista/motor devuelve una propuesta con más
  activos de los que el usuario realmente quiere (ej. el motor ofrece sumar
  10 activos nuevos), si el usuario responde que prefiere algo más acotado
  (ej. solo 4 activos nuevos + los que ya tiene en su portafolio actual), la
  IA no le ofrece modelar/proyectar esa versión específica pese a sus propias
  advertencias — la objeción del Analista termina bloqueando la posibilidad
  de que el usuario vea las proyecciones reales de la composición que insiste
  en probar.
- Andrea quiere que, aunque el Analista tenga una objeción/advertencia
  legítima sobre lo que el usuario pide, igual le ofrezca modelarlo y
  mostrarle las proyecciones de esa composición específica, para que decida
  él con esa información en la mano — la advertencia debe informar, no
  bloquear la simulación.

**Pendiente de decisión / próximos pasos:**
- Diseñar el ajuste en la próxima sesión — probablemente en el prompt de
  `_sistema_analista` (`dashboard.py`), y posiblemente reutilizando
  `simular_propuesta`/`activos_ancla` (ver entrada anterior) para modelar la
  composición reducida que el usuario insiste en ver, en vez de que la
  advertencia detenga el flujo.
- Ningún archivo tocado todavía — esta entrada es solo el registro del
  pedido, para no perderlo antes de la próxima sesión.

---

## [2026-08-12] Hoja de ruta del día (pedida por Andrea, arrancamos por el punto 1)

**Contexto:** Andrea dio 4 frentes de trabajo para hoy, en este orden. Solo
el punto 1 tiene diseño (de la entrada anterior); los puntos 2-4 son
intención de producto todavía sin explorar en código, quedan aquí para no
perderlos si la sesión no alcanza a cubrirlos todos.

1. **Analista — proyectar composición específica pese a advertencias**
   (ver entrada `[2026-08-12] Pendiente para próxima sesión` justo arriba).
   Es el punto de arranque de hoy.

2. **Seguimiento — tracking real de composición y detección de rebalanceo:**
   - Que la página/lógica de Seguimiento deje de ser solo un registro de
     transacciones y pase a calcular cómo esas transacciones van moviendo la
     composición REAL del portafolio en el tiempo, y a vigilar si esa deriva
     amerita un rebalanceo.
   - Si detecta que sí, debe poder avisarle al usuario -- Andrea lo describe
     como un "chat flotante" que le diga algo como: "hoy Seguimiento miró la
     composición actual de tu portafolio: seguimos encaminados a tus metas"
     o, si hay desviación, que lo diga y ofrezca una ruta directa al
     Analista.
   - Esa ruta al Analista debe llegar con CONTEXTO: el Analista debe saber
     que se activó porque Seguimiento detectó desviación de la composición
     respecto a la meta, no como una conversación nueva sin motivo.

3. **Monitor — rangos de VENTA, no solo de entrada:**
   - Hoy Monitor solo calcula rangos/señales para ENTRAR a una posición
     (`rango_entrar`, `rango_vigilar`, ver `api_precios_rt` en
     `dashboard.py`). Falta el rango simétrico para SALIR/liquidar una
     posición ya comprada.
   - Andrea quiere que el usuario pueda pedirle a Monitor que vigile una
     posición para venderla (posiblemente un botón dedicado que además
     dispare el flujo de venta), y que Monitor avise cuando esa posición
     entre en rango de liquidación.

4. **Demo del proyecto completo**, para mostrarlo -- sin más detalle todavía
   sobre formato/alcance, queda pendiente de precisar cuando se llegue a
   ese punto.

**Pendiente de decisión / próximos pasos:**
- Empezar por el punto 1 (analista). Los puntos 2-4 necesitan su propia
  ronda de diseño/exploración de código antes de tocar nada -- no asumir
  alcance todavía.

---

## [2026-08-12] Analista: proyectar una composición específica pese a advertencias (`forzar_exacto`)

**Contexto:** punto 1 de la hoja de ruta del día. Cuando el motor sugiere
una propuesta más amplia de lo que el usuario quiere (ej. "te ofrezco
añadir 10 activos" y el usuario responde "no, quiero solo agregar 4 más los
2 que ya tengo"), el Analista no ofrecía modelar esa versión reducida —
solo repetía la advertencia. Se construyó sobre el mecanismo `activos_ancla`
de la entrada anterior (`[2026-08-11] Editar portafolio existente`).

**Diseño:** combinar `tickers_fijos` (restringe el universo) con
`activos_ancla` (protege de las purgas), algo que el diseño de ayer ya
dejaba disponible como consecuencia natural pero sin usar. Cuando ambos
apuntan a la MISMA lista de tickers, el resultado es: universo restringido
a exactamente esos tickers, y todos protegidos dentro de ese universo chico
— ninguna purga puede sacar a ninguno, y el motor no busca ni agrega nada
de más allá de lo pedido.

**Cambios de backend, 2 archivos, en 3 rondas (auditor→programador→tester
cada una):**

1. `adaptador_analista.py`, `_cargar_todo_para_motor` (línea ~361): la
   condición que decide si restringe el universo pasó de mirar
   `activos_ancla` a mirar `tickers_fijos` — antes, si había `activos_ancla`,
   NUNCA se restringía, sin importar `tickers_fijos`; ahora `tickers_fijos`
   manda la restricción de forma independiente, permitiendo que las dos
   banderas se combinen a propósito.
2. `dashboard.py`: nuevo campo `forzar_exacto` (boolean) en
   `SIMULAR_PROPUESTA_TOOL` (línea ~496); `_tool_simular_propuesta` (línea
   ~205) y `api_generar_propuesta` (línea ~795) hacen
   `tickers_fijos = activos_ancla` cuando `forzar_exacto=true` (con guarda
   `and bool(activos_ancla)` para que un `forzar_exacto` mal formado sin
   ancla no rompa nada). `_sistema_analista` ganó 2 instrucciones nuevas:
   la advertencia informa pero no bloquea, y cuándo usar `forzar_exacto`.
3. **Bug encontrado probando** (no reportado en la ronda 1, corregido y
   documentado aquí por señalamiento del tester en la ronda 2):
   `adaptador_analista._resumir_exclusiones` (línea ~579) — un ancla que cae
   en el peor 30% por Sortino en el paso 1 y es reincorporada por
   `motor_seleccion.seleccionar_anclado` (las anclas nunca se purgan de
   verdad) seguía apareciendo en `motivos_exclusion` con un mensaje FALSO de
   "purgado por Sortino bajo", aunque sí estuviera en la selección final con
   peso real. Se agregó un filtro final: cualquier ticker que terminó en
   `seleccion["seleccion"]` se quita del diccionario de motivos.
4. **2 huecos encontrados por el tester en la ronda 2, corregidos en la
   ronda 3:**
   - `adaptador_analista._restringir_universo` (línea ~120): ganó el
     parámetro `permitir_expansion_etf=True`. Cuando la lista forzada era
     puros ETFs abarcando >2 categorías, la función expandía el universo a
     ~35-39 ETFs (comportamiento correcto para el flujo viejo de "solo
     ETFs", pero rompía la promesa de `forzar_exacto`). Ahora
     `_cargar_todo_para_motor` pasa `permitir_expansion_etf=not
     bool(activos_ancla)` — con `activos_ancla` presente, nunca expande.
   - `dashboard.py`, `_tool_simular_propuesta` (línea ~238): el cálculo de
     `excluidos`/`motivos_exclusion` solo miraba `tickers_candidatos`; un
     ticker de `activos_ancla` sin histórico descargado desaparecía del
     resultado sin ninguna explicación. Ahora también se revisan los
     tickers de `activos_ancla`, con un mensaje específico ("no se pudo
     incluir pese a haberlo pedido como ancla... necesita descargarse
     primero") distinto del genérico.

**Verificado con datos reales (yo + tester, 3 rondas independientes):**
- Caso real de Andrea: `activos_ancla`=`tickers_fijos`=`['COST','VTI','NVDA','XLK','JNJ','KO']`
  → los 6 aparecen en los pesos finales, ni uno más ni uno menos,
  `motivos_exclusion` vacío (antes del fix del punto 3, KO y JNJ aparecían
  ahí incorrectamente).
- Mismo caso SIN `forzar_exacto` (solo `activos_ancla`): universo completo,
  el motor suma más allá de los 6 (comportamiento correcto y distinto,
  confirma que las dos banderas hacen cosas genuinamente diferentes).
- Caso mixto (`tickers_fijos` con un ticker extra que NO es ancla): el
  extra se purga normalmente con motivo real; las anclas sobreviven todas.
- Puros ETFs en >2 categorías con `forzar_exacto`: ya NO expande a 35+, se
  queda en los pedidos (menos los que no tengan datos).
- Ancla sin histórico (`GLD`, y por separado un ticker inventado): ahora
  aparece en `motivos_exclusion` con el mensaje específico de ancla, en vez
  de desaparecer mudo.
- Regresión: el flujo de ayer (`activos_ancla` solo, sin `tickers_fijos`) y
  el flujo de "solo ETFs" sin `activos_ancla` (sigue expandiendo a 35+ como
  siempre) quedaron confirmados sin cambios de comportamiento.

**Resultado:** cerrado y verificado. Archivos tocados:
`adaptador_analista.py`, `dashboard.py`. Ningún cambio commiteado por mí —
queda para que Andrea lo revise.

---
</content>

## [2026-08-12] Analista: explicación narrativa del fix de `forzar_exacto` (antes vs ahora)

**Contexto:** entrada complementaria a `[2026-08-12] Analista: proyectar una
composición específica pese a advertencias (forzar_exacto)`, que ya dejó el
resumen técnico del cambio. Esta entrada agrega la explicación
narrativa/pedagógica completa que mano-derecha produjo a pedido de Andrea,
para que quede documentada la lógica de por qué el fix funcionaba mal antes
y por qué funciona bien ahora, no solo el diff.

**Qué se hizo — ANTES de hoy, la causa raíz exacta:**
- La causa raíz estaba en una sola condición en `adaptador_analista.py`
  (`_cargar_todo_para_motor`, tal como quedó en el commit `696a062`):
  ```python
  if activos_ancla:
      saltar_cobertura_sector = False
  else:
      retornos, sector, saltar_cobertura_sector = _restringir_universo(
          retornos, sector, tickers_fijos
      )
  ```
  Si `activos_ancla` tenía algo dentro, la función ni siquiera llamaba a
  `_restringir_universo` — daba igual qué llevara `tickers_fijos`, esa rama
  nunca se ejecutaba. El universo de búsqueda del motor se quedaba SIEMPRE
  completo (~98 activos), nunca se achicaba a la lista específica que el
  usuario pedía. En `dashboard.py`, la tool `simular_propuesta` reforzaba la
  misma exclusión mutua: `tickers_fijos=input_.get("tickers_candidatos") if
  not activos_ancla else None`.
- Esto le dejaba al Analista solo dos herramientas, NUNCA las dos juntas:
  - `tickers_candidatos` (restringe el universo): "busca SOLO entre estos
    tickers", pero sin protección — si dentro de esa lista chica un ticker
    tenía mal Sortino o quedaba redundante, la purga se lo comía igual.
  - `activos_ancla` (protege posiciones): garantizaba que esos tickers nunca
    se purgaran, pero dejaba el universo COMPLETO compitiendo por los cupos
    restantes — el motor podía sumar activos adicionales que el usuario no
    pidió.
- Además, `_sistema_analista` no tenía ninguna instrucción sobre qué hacer si
  el usuario insistía tras una advertencia — ese bloque no existía.
  Analogía: es como pedirle a un mesero "tráigame solo estos 4 platos del
  menú, ni uno más" — el mesero solo podía garantizar exactamente esos 4 sin
  asegurar que ninguno se quedara en cocina, O garantizar que esos 4 lleguen
  pero sin poder evitar que el chef mande 6 entradas adicionales "para
  completar". Nunca las dos cosas a la vez.

**Qué se hizo — AHORA, el camino mecánico completo:**
1. El prompt reconoce la insistencia: `_sistema_analista` (`dashboard.py:596-599`
   y `655-661`) tiene 2 instrucciones nuevas — "la advertencia INFORMA, no
   bloquea" y el bloque "SI EL USUARIO INSISTE PESE A TU ADVERTENCIA: ...
   llama simular_propuesta con activos_ancla = esa lista completa y
   forzar_exacto=true".
2. La tool tiene un campo nuevo: `SIMULAR_PROPUESTA_TOOL` (`dashboard.py:513-527`)
   agregó `forzar_exacto: boolean`.
3. `_tool_simular_propuesta` fusiona las dos banderas (`dashboard.py:215-224`):
   con `forzar_exacto=true` y `activos_ancla` presente, `tickers_fijos` se
   hace IGUAL a `activos_ancla` (con guarda `and bool(activos_ancla)` para
   que un `forzar_exacto` mal formado sin lista no rompa nada).
4. `_cargar_todo_para_motor` combina restricción + protección
   (`adaptador_analista.py:361-367`, el fix central de hoy): la decisión de
   restringir el universo ahora depende de `tickers_fijos`, INDEPENDIENTE de
   `activos_ancla` — las dos banderas dejan de excluirse mutuamente. Cuando
   ambas apuntan a la misma lista, el universo se achica a EXACTAMENTE esos
   tickers.
5. `seleccionar_anclado` (`motor_seleccion.py:412-466`) protege a todos
   dentro de ese universo chico: paso 1 (Sortino) reincorpora cualquier
   ancla purgada por percentil; paso 2 (correlación parcial) nunca purga un
   protegido; paso 3 (cobertura sectorial) deja entrar a TODAS las anclas
   aunque compartan sector (el límite de "uno por sector" solo aplica a
   candidatos nuevos compitiendo por lo que sobra — y aquí no sobra nada, el
   universo ya era solo esos tickers).
- Resultado del camino: los tickers pedidos quedan seleccionados, HRP les
  reparte pesos reales, y el usuario ve la simulación de exactamente lo que
  pidió, con datos reales — no una promesa vacía.

**Qué se hizo — los 3 bugs encontrados y corregidos en el camino:**
- **Bug 1 — un ticker que SÍ estaba en la propuesta final aparecía como
  "purgado".** El paso 1 de `seleccionar_anclado` puede listar a un ancla en
  `eliminados` (por mal Sortino) y reincorporarlo un instante después — pero
  `_resumir_exclusiones` (el texto de "por qué se excluyó X") leía ese
  `eliminados` sin verificar si el ticker terminó igual en la selección
  final. Es como si el mesero dijera "el plato que pediste se acabó" mientras
  te lo pone en la mesa. Fix (`adaptador_analista.py:579-584`): al final se
  filtra cualquier ticker que sí quedó en la selección final.
- **Bug 2 — una lista forzada de puros ETFs se expandía a ~35-39 ETFs.**
  `_restringir_universo` tenía una regla para OTRO caso de uso ("solo quiero
  ETFs, sin tema específico"): si todos los tickers pedidos son ETFs y no
  colapsan en ≤2 categorías, expandía el universo a TODOS los ETFs
  conocidos. Eso traicionaba la promesa de `forzar_exacto` (ej. forzar
  `["XLK","XLF","GLD"]` — 3 categorías distintas — devolvía una selección
  entre ~39 ETFs, no esos 3). Fix: nuevo parámetro `permitir_expansion_etf`
  (`adaptador_analista.py:120`), puesto en `False` cuando hay `activos_ancla`
  (`adaptador_analista.py:364`).
- **Bug 3 — un ticker anclado sin histórico descargado desaparecía sin
  explicación.** `seleccionar_anclado` filtra las anclas contra las columnas
  de datos disponibles (línea 432) — correcto y necesario, pero
  `_tool_simular_propuesta` solo revisaba `tickers_candidatos` para armar la
  explicación de exclusiones, nunca `activos_ancla`. Un ticker faltante que
  viniera como ancla no aparecía en ningún lado, ni siquiera como "excluido"
  — parecía un bug silencioso. Fix (`dashboard.py:238-247` y `255-264`):
  ahora revisa candidatos Y anclas juntos, con un mensaje específico para
  anclas: "no tiene histórico... necesita descargarse primero antes de poder
  forzarlo".

**Resultado — ejemplo end-to-end (caso real ya verificado por el tester):**
- Portafolio actual: COST + VTI. Usuario insiste en agregar exactamente
  NVDA, XLK, JNJ, KO pese a que el motor había ofrecido más.
- ANTES (hipotético): solo se podía anclar sin restringir — el universo se
  quedaba completo (~98 activos) y el motor podía devolver más tickers de
  los 6 pedidos, justo lo que el usuario no quería ver.
- AHORA (real, verificado): `activos_ancla = tickers_fijos =
  ["COST","VTI","NVDA","XLK","JNJ","KO"]` con `forzar_exacto=true` → los 6
  tickers aparecen en los pesos finales, ni uno más ni uno menos,
  `motivos_exclusion` vacío. Como control, sin `forzar_exacto` (solo
  `activos_ancla`) el motor sí suma tickers adicionales — confirmando que
  las dos banderas hacen cosas genuinamente distintas.

**Pendiente de decisión / próximos pasos:**
- Ninguno nuevo generado por esta entrada — es documentación pedagógica
  complementaria del fix ya cerrado y registrado en la entrada técnica
  anterior del mismo día.

---

## [2026-08-12] Seguimiento: composición proyectada vs real, tabla financiera por activo, aviso de rebalanceo

**Contexto:** punto 2 de la hoja de ruta del día. Seguimiento era puramente
un libro contable de transacciones — no calculaba la composición REAL del
portafolio, no la comparaba contra la meta, no mostraba ninguna métrica
financiera por activo, y no existía ningún concepto de rebalanceo en el
código.

**Decisiones de producto tomadas con Andrea antes de construir:**
- El "proyectado" contra el que se compara la realidad se empieza a
  **guardar desde hoy**, cada vez que se aplica una propuesta (antes se
  descartaba después de mostrarse una vez). Portafolios que no han vuelto a
  aplicar nada desde hoy no tienen ese snapshot histórico, así que caen en
  un fallback recalculado al vuelo, marcado explícitamente como tal.
- Alcance de hoy: composición + métricas **snapshot actual** (real vs
  proyectado), por activo y a nivel de portafolio. La comparación mes a mes
  con trayectoria completa queda para una sesión dedicada — es la pieza más
  pesada, requiere reconstruir series históricas completas.
- El aviso de rebalanceo se calcula al vuelo al abrir Dashboard o
  Seguimiento — sin job en background, sin tocar `monitor.py`/`scheduler.py`
  (territorio de la socia).

**Matiz de diseño importante:** siguiendo la misma filosofía que
`motor_seleccion.py` (mu casi inestimable por activo individual), la tabla
financiera por activo **nunca inventa una "rentabilidad proyectada" por
activo** — solo muestra rentabilidad REAL (desde la compra) y "lo que el
motor vio" del activo (Sortino histórico, volatilidad histórica), nunca un
retorno esperado fabricado. A nivel de portafolio completo sí hay
proyección legítima (el Monte Carlo ya existente).

**Backend (`dashboard.py`, `adaptador_analista.py`, `gestor_portafolio.py`):**
- `gestor_portafolio.guardar_composicion(..., proyeccion=None)`: nuevo
  parámetro opcional que persiste `proyeccion_al_aplicar` (fecha + métricas
  + proyecciones) en el JSON del portafolio.
- `dashboard._calcular_proyeccion_para_guardar()`: recalcula la proyección
  sobre los pesos FINALES que se aplican (nunca confía en datos del
  cliente), reutilizando `recalcular_con_pesos` ya existente. Conectado en
  `api_aplicar_propuesta`, ambas ramas.
- `dashboard.calcular_composicion_real`, `calcular_desviacion_composicion`,
  `calcular_metricas_reales_por_activo`: nuevas, cerca de
  `calcular_tiempo_real` (que ganó un campo `fecha_inicio` por posición,
  aditivo). Umbrales editables documentados como juicio (mismo estilo que
  `perfilador.TOPES_POR_PLAZO`): `UMBRAL_DESVIACION_ACTIVO=5.0pp`,
  `UMBRAL_DESVIACION_TOTAL=10.0pp`, `UMBRAL_PROGRESO_MINIMO=90%` (evita
  marcar desviación mientras el portafolio todavía se está construyendo).
- `adaptador_analista.metricas_reales_portafolio()`: aplica los pesos
  reales sobre el histórico real de esos activos, reutilizando
  `_ret_mensual_cop_real` para ser comparable 1 a 1 con `datos["metricas"]`
  proyectado. Piso `MIN_MESES=6` agregado tras encontrar en pruebas propias
  que con solo 2 meses de historial el retorno anualizado salía en -67.6% —
  técnicamente correcto, prácticamente engañoso.
- `adaptador_analista.metricas_historicas_por_activo()`: Sortino +
  volatilidad histórica por ticker, reutilizando `motor_seleccion.
  calcular_sortino`.
- `/api/seguimiento` y `/api/dashboard` extendidos con el bloque
  `comparacion`/`desviacion_composicion`.
- `_sistema_analista`/`api_analista_chat` ganan `motivo` opcional — cuando
  es `"rebalanceo"`, el backend RECALCULA la desviación real (nunca confía
  en el cliente) y antepone al prompt los activos desviados con sus puntos
  porcentuales.

**Frontend:** 3 componentes nuevos —
`components/ui/composicion-comparada.tsx` (gráfico de barras meta vs real,
recharts, paleta validada con la skill dataviz contra la superficie oscura
real de la app — colores primos cercanos a los oficiales del proyecto pero
propios de este gráfico porque los hex oficiales fallaban el chequeo de
banda de luminancia para uso categórico), `components/ui/tabla-financiera-
activos.tsx` (tabla por activo + tarjetas agregadas proyectado/real,
reutiliza el verde/rojo ya establecido en el resto de la app para
consistencia de significado), `components/ui/aviso-seguimiento.tsx` (widget
flotante esquina inferior derecha, 2 estados, silencio total mientras
`desviacion.aplica` es falso). Wireados en Dashboard y Seguimiento;
`analista/page.tsx` lee `?motivo=rebalanceo` de la URL y envía
automáticamente un primer mensaje con ese contexto en vez del saludo
genérico.

**Verificado:** backend con `test_client()` real end-to-end (generar →
aplicar propuesta → confirmar `proyeccion_al_aplicar` en disco;
`andrea.json` intacto tras las pruebas, hash confirmado antes/después) por
mí y por el tester en rondas independientes; `probar_motor.py`/
`probar_red.py` limpios (sin regresión en el motor cuantitativo). Frontend
verificado con Playwright + mocks (4 escenarios: desviado, en línea,
portafolio construyéndose, y el flujo completo `?motivo=rebalanceo` en el
chat) — cero errores de consola, screenshots confirman el render correcto.
Un bug visual encontrado y corregido en el camino: `AvisoSeguimiento` usaba
`GlowPanel`, que tiene un brillo decorativo interno fijo azulado que no se
puede sobreescribir por completo (mismo problema ya documentado antes en la
sesión con `GlowCard`) — se cambió a `GlassPanel` con borde/sombra propios.

**Hallazgos del tester, no bloqueantes, para que Andrea decida:**
1. El cálculo de "progreso" de `calcular_desviacion_composicion` (intersecta
   contra la meta vigente) es distinto, en casos reales, al que ya usa
   `/api/seguimiento` (cuenta cualquier ticker con al menos un aporte,
   incluso si ya no está en la meta) — pueden dar porcentajes distintos.
   Documentado explícitamente en el docstring; no unificado hoy.
2. **Riesgo operacional preexistente, no de hoy:** `dashboard.py` arranca el
   hilo del monitor de producción real 15 segundos después de cualquier
   `import dashboard` — incluyendo scripts de prueba con `test_client()`. El
   tester lo disparó por accidente en una de sus pruebas (mercado cerrado en
   ese momento, sin alerta real de Telegram, pero en horario de mercado
   podría pasar). No hay ningún guard de entorno (`TESTING`, etc.) que lo
   evite. Vale la pena agregar uno en una próxima sesión.

**Resultado:** cerrado y verificado. Archivos backend tocados:
`dashboard.py`, `adaptador_analista.py`, `gestor_portafolio.py`. Frontend:
`components/ui/composicion-comparada.tsx`,
`components/ui/tabla-financiera-activos.tsx`,
`components/ui/aviso-seguimiento.tsx`, `lib/api.ts`,
`app/portafolio/[archivo]/page.tsx`,
`app/portafolio/[archivo]/seguimiento/page.tsx`,
`app/portafolio/[archivo]/analista/page.tsx`. Ningún cambio commiteado por
mí — queda para que Andrea lo revise.

**Pendiente de decisión / próximos pasos:**
- Comparación mes a mes con trayectoria completa — sesión dedicada aparte.
- Decidir si vale la pena agregar el guard de entorno al hilo del monitor
  para que las pruebas con `test_client()` sean seguras por diseño.
- Reconectar `guardar_registro_diario`/historial diario (infraestructura ya
  existe a medias en el repo, desconectada) si en algún momento se quiere
  ese enfoque en vez de la reconstrucción retroactiva usada hoy.

---
