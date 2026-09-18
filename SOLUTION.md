# SOLUTION.md

> Documento vivo — se completa a medida que se resuelven las tareas del `CANDIDATE_INSTRUCTIONS.md`.

## Decisiones

- **Estructura del repositorio:** el proyecto original no tenía un `.git` propio en la raíz ni en `frontend/`; `backend/` tenía un repositorio separado que versionaba la carpeta `venv/` completa (7297 archivos). Se creó un único repositorio en la raíz con `backend/` y `frontend/` como subcarpetas normales, con un `.gitignore` que excluye `venv/`, `node_modules/`, `__pycache__/` y `db.sqlite3`. Repositorio publicado en https://github.com/ramonzeraa/prueba_tecnica_webtools (rama `main`).

- **Tarea 1 — Aislamiento entre empresas:** `SurveyResultsView.get` buscaba la survey solo por `pk`, sin validar que el usuario autenticado perteneciera a la organización dueña. Se agregó `SurveyQuerySet.for_user(user)` (`backend/surveys/models.py`), que filtra por `organization__memberships__user=user`, y la view ahora resuelve la survey vía `Survey.objects.for_user(request.user)` antes del `get_object_or_404`. Un usuario sin acceso recibe `404` (no `403`), para no revelar si el `survey_id` existe. Se agregaron dos tests (`backend/surveys/tests.py`): usuario de otra organización no accede (pero sí accede a su propia survey) y usuario sin ninguna membership recibe 404. Los 4 tests del proyecto pasan.

## Riesgos conocidos

- **Valores de configuración de demo committeados:** `SECRET_KEY` (`backend/config/settings.py`), `WEBHOOK_TOKEN` (`backend/config/settings.py`) y las contraseñas `ana123`/`bob123` (`seed_demo.py`, `tests.py`, `frontend/src/api.js`) están hardcodeados. Son exactamente los valores de demo que ya definía el scaffold original de la prueba técnica (el usuario/contraseña `ana`/`ana123` están documentados en el propio `CANDIDATE_INSTRUCTIONS.md`). No son credenciales reales ni de producción — un escáner de secretos (p. ej. GitGuardian) puede señalarlos como falso positivo por el patrón (`SECRET_KEY = "..."`, password hardcodeada), pero no hay ningún secreto real expuesto en el repositorio. En un entorno real, `SECRET_KEY` y `WEBHOOK_TOKEN` deberían venir de variables de entorno.

## Mejoras futuras

_(pendiente — se completa al cerrar las 3 tareas)_
