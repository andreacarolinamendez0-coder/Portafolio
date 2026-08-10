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
