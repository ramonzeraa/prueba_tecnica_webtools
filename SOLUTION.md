# SOLUTION.md

> Documento vivo — se completa a medida que se resuelven las tareas del `CANDIDATE_INSTRUCTIONS.md`.

## Decisiones

- **Estructura del repositorio:** el proyecto original no tenía un `.git` propio en la raíz ni en `frontend/`; `backend/` tenía un repositorio separado que versionaba la carpeta `venv/` completa (7297 archivos). Se creó un único repositorio en la raíz con `backend/` y `frontend/` como subcarpetas normales, con un `.gitignore` que excluye `venv/`, `node_modules/`, `__pycache__/` y `db.sqlite3`. Repositorio publicado en https://github.com/ramonzeraa/prueba_tecnica_webtools (rama `main`).

- **Tarea 1 — Aislamiento entre empresas:** `SurveyResultsView.get` buscaba la survey solo por `pk`, sin validar que el usuario autenticado perteneciera a la organización dueña. Se agregó `SurveyQuerySet.for_user(user)` (`backend/surveys/models.py`), que filtra por `organization__memberships__user=user`, y la view ahora resuelve la survey vía `Survey.objects.for_user(request.user)` antes del `get_object_or_404`. Un usuario sin acceso recibe `404` (no `403`), para no revelar si el `survey_id` existe. El test de aislamiento usa únicamente el usuario `ana` (la única credencial documentada en el enunciado) contra una survey de una organización a la que no pertenece — no fue necesario crear un segundo usuario real para demostrar el aislamiento. Verificado también manualmente vía `curl` contra el servidor local.

- **Tarea 2 — Webhook idempotente:** `ResponseWebhookView.post` creaba una `Response` nueva en cada llamada sin verificar duplicados. Se agregó `UniqueConstraint(survey, external_id)` en el modelo `Response` (migración `0002_response_unique_survey_response`) y la vista envuelve la creación en `transaction.atomic()`, capturando `IntegrityError`: si el evento ya existía, devuelve el registro existente con `200` en vez de crear uno nuevo (`201` solo en la primera vez). La constraint a nivel de base de datos es lo que garantiza la idempotencia ante dos requests casi simultáneos — una verificación previa en Python ("existe? entonces no creo") no alcanza, porque dos requests podrían pasar esa verificación antes de que cualquiera de las dos confirme el `INSERT`. Verificado con 2 tests automatizados y manualmente enviando el mismo payload 3 veces por `curl`: siempre devolvió el mismo `id`, y el conteo de respuestas de la survey subió en 1, no en 3.

- **Tarea 3 — Filtro de fechas:** se agregó `DateRangeFilterSerializer` (`backend/surveys/serializers.py`) para validar los query params `from`/`to`, siguiendo el mismo patrón que ya usaba `WebhookSerializer`. `SurveyResultsView.get` aplica `submitted_at__date__gte`/`__lte` solo cuando el parámetro correspondiente vino en la petición, para que funcionen juntos o por separado. Fecha con formato inválido o `from` posterior a `to` devuelven `400` con mensaje claro. En el frontend se agregaron 2 inputs `type="date"` (`App.vue`) con la misma validación de `from > to` en el cliente antes de llamar a la API. Verificado con 5 tests automatizados nuevos y manualmente en el navegador.

- **Paginación en `SurveyResultsView`:** se agregó `LimitOffsetPagination` de DRF, activada solo si el cliente manda `?limit=`. Sin ese parámetro el endpoint se comporta exactamente igual que antes (devuelve todo), así que no rompe el frontend actual ni los tests existentes — es una capacidad nueva, no un cambio de contrato. `count` siempre refleja el total de respuestas que matchean los filtros, no el tamaño de la página. Verificado con 2 tests: sin `limit` (todo, sin `next`) y con `limit=1` (1 resultado + `next`).

- **Browsable API de DRF arreglada:** acceder a un endpoint directo desde el navegador devolvía `500 TemplateDoesNotExist` (`TEMPLATES = []` en `settings.py`, pero `BrowsableAPIRenderer` seguía habilitado por defecto). Se agregó `"DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]` en `REST_FRAMEWORK`. Verificado con los 12 tests en verde y navegando directo a la API en el navegador (devuelve JSON limpio, no el error de template).

## Riesgos conocidos

- **Valores de configuración de demo committeados:** `SECRET_KEY` y `WEBHOOK_TOKEN` (`backend/config/settings.py`), y la contraseña `ana123` (`seed_demo.py`, `tests.py`, `frontend/src/api.js`) están hardcodeados. Son los valores de demo que ya definía el scaffold original de la prueba técnica (documentados en el propio `CANDIDATE_INSTRUCTIONS.md`). No son credenciales reales ni de producción. En un entorno real, `SECRET_KEY` y `WEBHOOK_TOKEN` deberían venir de variables de entorno.

- **Test de idempotencia sin concurrencia real:** el test de la Tarea 2 verifica el comportamiento enviando el mismo evento 2 veces de forma secuencial, no con requests simultáneos reales (threads). Ejercita el mismo camino de código (`except IntegrityError`) que una corrida real activaría, pero no es una prueba de concurrencia en sentido estricto — la garantía real viene de la constraint en la base de datos, no del test.

## Mejoras futuras

- Consumir la paginación desde el frontend (botones "siguiente"/"anterior" usando `next`/`previous`) — hoy la API la soporta pero la UI todavía pide todo de una vez.
- Selector de survey en el frontend — hoy `surveyId` está fijo en `1` (`App.vue`), no hay forma de elegir otra survey desde la UI.
- Mover `SECRET_KEY` y `WEBHOOK_TOKEN` a variables de entorno, fuera del código versionado.
- Autenticación del webhook por firma HMAC del payload en vez de un token estático — más robusto ante filtración del token.
- Test de concurrencia real (con threads) para la Tarea 2, complementando el test secuencial actual.
