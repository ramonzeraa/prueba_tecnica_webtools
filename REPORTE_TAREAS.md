# Reporte de tareas — Prueba técnica Webtools

Resumen de las 3 tareas del `CANDIDATE_INSTRUCTIONS.md`: qué problema había, qué se hizo y por qué cada cambio fue necesario. Detalle línea por línea en `AI_NOTES.md`; alternativas evaluadas para cada tarea en `ANALISE_CANDIDATE_INSTRUCTIONS.md`.

---

## Tarea 1 — Problema de aislamiento entre empresas

**Problema:** `SurveyResultsView.get` (`backend/surveys/views.py`) buscaba la survey solo por su `id`, sin verificar que el usuario autenticado perteneciera a la organización dueña. Cualquier usuario logueado podía leer los resultados de cualquier organización con solo cambiar el número en la URL.

**Qué se hizo:**

| Archivo | Por qué era necesario |
|---|---|
| `backend/surveys/models.py` | Es donde vive la regla de negocio "a qué surveys puede acceder un usuario". Se agregó `SurveyQuerySet.for_user(user)`, reutilizable por cualquier vista futura que necesite el mismo filtro. |
| `backend/surveys/views.py` | Es el endpoint vulnerable — sin tocarlo, el bug sigue ahí. Ahora resuelve la survey a través de `Survey.objects.for_user(request.user)` en vez de `Survey.objects` a secas. |
| `backend/surveys/tests.py` | El enunciado pide explícitamente pruebas que demuestren el aislamiento. |

**Resultado:** un usuario sin acceso recibe `404` (no `403`), para no revelar si el `survey_id` existe. El comportamiento de un usuario autorizado no cambió.

**Verificación:** 3 tests automatizados + verificación manual vía `curl` y en el navegador (usuario `ana` bloqueado al pedir la survey de otra organización).

---

## Tarea 2 — Evitar respuestas duplicadas

**Problema:** `ResponseWebhookView.post` creaba una `Response` nueva en cada llamada, sin verificar si el mismo evento (`external_id`) ya había sido procesado. Un reintento del proveedor del webhook duplicaba la respuesta.

**Qué se hizo:**

| Archivo | Por qué era necesario |
|---|---|
| `backend/surveys/models.py` | Se agregó `UniqueConstraint(survey, external_id)`. Es la única forma de garantizar idempotencia real cuando dos requests llegan casi al mismo tiempo — una validación previa en Python no alcanza, porque ambas peticiones podrían pasarla antes de que cualquiera termine de guardar. |
| `backend/surveys/migrations/0002_response_unique_survey_response.py` | Sin migración, la constraint existe solo en el código Python, no en la base de datos real. |
| `backend/surveys/views.py` | La creación de la `Response` se envuelve en `transaction.atomic()`; si la constraint se viola, se captura `IntegrityError` y se devuelve el registro ya existente con `200` (no `201`), en vez de un error. |
| `backend/surveys/tests.py` | Pruebas de reenvío del mismo evento (no duplica) y de eventos distintos (sí crean normalmente). |

**Resultado:** reenviar el mismo evento no crea una segunda `Response`; el remitente del webhook recibe una respuesta `200` normal, no un error.

**Verificación:** 2 tests automatizados + verificación manual enviando el mismo payload 3 veces por `curl` — siempre devolvió el mismo `id`, y el conteo de respuestas subió en 1, no en 3.

---

## Tarea 3 — Añadir filtro de fechas

**Problema:** no existía ningún filtro por fecha de envío, ni en el backend (los query params `from`/`to` nunca se leían) ni en el frontend (no había ningún control de fecha).

**Qué se hizo:**

| Archivo | Por qué era necesario |
|---|---|
| `backend/surveys/serializers.py` | Nuevo `DateRangeFilterSerializer`, que valida el formato de `from`/`to` y que `from` no sea posterior a `to`. Sigue el mismo patrón que ya usaba `WebhookSerializer` en este proyecto. |
| `backend/surveys/views.py` | Es el endpoint en sí — sin este cambio los filtros no existen. Aplica `submitted_at__date__gte`/`__lte` solo si el parámetro correspondiente vino en la petición, para que `from` y `to` funcionen juntos o por separado. |
| `frontend/src/api.js` | Necesita armar la query string (`?from=...&to=...`) y mandarla en el `fetch`. |
| `frontend/src/App.vue` | Es el control pedido explícitamente en el enunciado ("Añade los controles correspondientes en Vue"): 2 inputs de fecha + botón, con validación de `from > to` en el cliente antes de llamar a la API. |
| `backend/surveys/tests.py` | Pruebas: solo `from`, solo `to`, ambos juntos, fecha inválida (`400`), `from > to` (`400`). |

**Comportamiento definido para fechas inválidas:** formato incorrecto → `400` con mensaje claro (validación automática de `DateField`); `from` posterior a `to` → `400` con mensaje explícito. Mismo criterio aplicado en el frontend (para no hacer una llamada a la API que sabemos que va a fallar) y en el backend (que es la validación que realmente importa).

**Resultado:** filtro funcional, combinable, con mensajes de error claros en ambos lados.

**Verificación:** 5 tests automatizados nuevos (10/10 en total el suite completo) + verificación manual en el navegador: aplicar "Desde" redujo la lista correctamente, y `from > to` mostró el mensaje de validación sin llegar a golpear la API.

