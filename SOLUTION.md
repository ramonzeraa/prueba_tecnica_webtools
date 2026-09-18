# SOLUTION.md

> Documento vivo — se completa a medida que se resuelven las tareas del `CANDIDATE_INSTRUCTIONS.md`.

## Decisiones

- **Estructura del repositorio:** el proyecto original no tenía un `.git` propio en la raíz ni en `frontend/`; `backend/` tenía un repositorio separado que versionaba la carpeta `venv/` completa (7297 archivos). Se creó un único repositorio en la raíz con `backend/` y `frontend/` como subcarpetas normales, con un `.gitignore` que excluye `venv/`, `node_modules/`, `__pycache__/` y `db.sqlite3`. Repositorio publicado en https://github.com/ramonzeraa/prueba_tecnica_webtools (rama `main`).

- **Tarea 1 — Aislamiento entre empresas:** `SurveyResultsView.get` buscaba la survey solo por `pk`, sin validar que el usuario autenticado perteneciera a la organización dueña. Se agregó `SurveyQuerySet.for_user(user)` (`backend/surveys/models.py`), que filtra por `organization__memberships__user=user`, y la view ahora resuelve la survey vía `Survey.objects.for_user(request.user)` antes del `get_object_or_404`. Un usuario sin acceso recibe `404` (no `403`), para no revelar si el `survey_id` existe. El test de aislamiento usa únicamente el usuario `ana` (la única credencial documentada en el enunciado) contra una survey de una organización a la que no pertenece — no fue necesario crear un segundo usuario real para demostrar el aislamiento. Verificado también manualmente vía `curl` contra el servidor local.

- **Tarea 2 — Webhook idempotente:** `ResponseWebhookView.post` creaba una `Response` nueva en cada llamada sin verificar duplicados. Se agregó `UniqueConstraint(survey, external_id)` en el modelo `Response` (migración `0002_response_unique_survey_response`) y la vista envuelve la creación en `transaction.atomic()`, capturando `IntegrityError`: si el evento ya existía, devuelve el registro existente con `200` en vez de crear uno nuevo (`201` solo en la primera vez). La constraint a nivel de base de datos es lo que garantiza la idempotencia ante dos requests casi simultáneos — una verificación previa en Python ("existe? entonces no creo") no alcanza, porque dos requests podrían pasar esa verificación antes de que cualquiera de las dos confirme el `INSERT`. Verificado con 2 tests automatizados y manualmente enviando el mismo payload 3 veces por `curl`: siempre devolvió el mismo `id`, y el conteo de respuestas de la survey subió en 1, no en 3.

## Riesgos conocidos

- **Valores de configuración de demo committeados:** `SECRET_KEY` y `WEBHOOK_TOKEN` (`backend/config/settings.py`), y la contraseña `ana123` (`seed_demo.py`, `tests.py`, `frontend/src/api.js`) están hardcodeados. Son exactamente los valores de demo que ya definía el scaffold original de la prueba técnica (documentados en el propio `CANDIDATE_INSTRUCTIONS.md`). No son credenciales reales ni de producción — un escáner de secretos (p. ej. GitGuardian) puede señalarlos como falso positivo por el patrón, pero no hay ningún secreto real expuesto. En un entorno real, `SECRET_KEY` y `WEBHOOK_TOKEN` deberían venir de variables de entorno.

## Mejoras futuras

_(pendiente — se completa al cerrar las 3 tareas)_
