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
