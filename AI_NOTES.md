# AI_NOTES.md

## Herramientas utilizadas

- **Claude Code** (Anthropic, modelo Sonnet 5), en sesión interactiva dentro del entorno de desarrollo, con acceso a shell, edición de archivos y un navegador embebido para verificación visual.

## Para qué se utilizó

Se usó para: analizar el código existente y detectar los problemas de las 3 tareas del enunciado, proponer alternativas de solución con pros/contras para cada una, implementar código, generar y ejecutar los tests automatizados, y generar/ejecutar comandos de verificación manual (`curl`, fetch en el navegador). El nivel de participación en la escritura del código varió por tarea — se detalla abajo, tarea por tarea, sin generalizar.

## Resumen de autoría por tarea

- **Tarea 1 (aislamiento):** el código (`models.py`, `views.py`, `tests.py`) fue escrito por Claude, a partir de un análisis de alternativas que propuso y que se discutió con el usuario antes de aplicar. Claude generó los comandos `curl` para la verificación manual, que el usuario ejecutó.
- **Tarea 2 (webhook idempotente):** el código central (la `UniqueConstraint` en `models.py` y el bloque `try/transaction.atomic/except IntegrityError` en `views.py`) lo escribió el usuario. Claude había propuesto ese mismo enfoque antes (constraint en base de datos + captura de `IntegrityError`), y al revisar la implementación ya escrita encontró y corrigió un import muerto (`from urllib import response`, sin uso). Claude generó la migración (`makemigrations`), escribió los tests automatizados, y para la verificación manual creó un archivo `webhook_payload.json` (evitando problemas de escape de comillas de PowerShell al pasar JSON inline) y los comandos `curl` correspondientes — el usuario los ejecutó 3 veces y confirmó que no hubo duplicados.
- **Tarea 3 (filtro de fechas):** el código (`serializers.py`, `views.py`, `api.js`, `App.vue`, `tests.py`), tanto backend como frontend, fue escrito por Claude, siguiendo un plan que presentó línea por línea antes de aplicar. El usuario revisó ese plan, preguntó puntualmente si era necesario tocar tantos archivos (se le explicó el porqué de cada uno, ver `REPORTE_TAREAS.md`) y validó el resultado en el navegador.


## Cómo se comprobó que el resultado era correcto

- **Tests automatizados:** `python manage.py test` ejecutado después de cada tarea (3 → 5 → 10 tests, todos en verde al final).
- **Verificación manual con `curl`** contra el servidor local, para cada tarea (aislamiento, idempotencia del webhook, filtro de fechas).
- **Verificación visual en el navegador** (Tareas 1 y 3): captura de pantalla del frontend real, y en la Tarea 1 además una llamada `fetch` directa a la API con las credenciales de `ana` para confirmar el `404` en survey ajena.
- Ningún cambio se dio por válido solo por "no dar error" — cada tarea se cerró con al menos un test automatizado más una verificación manual que reproduce el escenario descrito en el enunciado.

---

## Detalle línea por línea de los cambios

### Tarea 1 — Aislamiento entre organizaciones

**`backend/surveys/models.py`** — se agregó una queryset personalizada y se la conectó como manager de `Survey`:

```python
class SurveyQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(organization__memberships__user=user)


class Survey(models.Model):
    ...
    objects = SurveyQuerySet.as_manager()   # línea nueva
```

`organization__memberships__user=user` es una consulta que atraviesa las relaciones: de `Survey` a `Organization`, de `Organization` a sus `Membership`, y filtra por el usuario de esa membership. En criollo: "dame solo las surveys de organizaciones donde este usuario es miembro". Se puso en el manager (no directo en la vista) para que cualquier otra vista que necesite el mismo filtro lo pueda reutilizar.

**`backend/surveys/views.py`** — el cambio real que cierra el bug:

```python
# antes
survey = get_object_or_404(Survey, pk=survey_id)
# después
survey = get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)
```

Antes se buscaba la survey solo por `id`, sin mirar quién la pide. Ahora el queryset ya viene filtrado por usuario antes de buscar el `id` — si la survey existe pero es de otra organización, `get_object_or_404` no la encuentra ahí adentro y devuelve `404` (no `403`, para no confirmarle a un atacante que ese `id` existe).

**`backend/surveys/tests.py`** — test nuevo, usando solo `ana`:

```python
def test_user_cannot_access_survey_from_another_organization(self):
    other_org = Organization.objects.create(name="Contoso")
    other_survey = Survey.objects.create(
        organization=other_org, title="Employee NPS", external_key="contoso-enps",
    )
    response = self.client.get(f"/api/surveys/{other_survey.id}/results/")
    self.assertEqual(response.status_code, 404)
```

Crea una organización y survey a la que `ana` no pertenece, y confirma que la API la bloquea — sin necesitar un segundo usuario real logueado.

---

### Tarea 2 — Webhook idempotente

**`backend/surveys/models.py`** — constraint única en `Response`:

```python
class Meta:
    ordering = ["-submitted_at"]
    constraints = [
        models.UniqueConstraint(
            fields=["survey", "external_id"], name="unique_survey_response"
        )
    ]
```

Esto le dice a la base de datos: "nunca permitas 2 filas con la misma combinación de `survey` + `external_id`". Es el "guardia de seguridad" que garantiza que, aunque lleguen 2 peticiones casi al mismo tiempo, la segunda inserción sea rechazada por la base — algo que una simple validación en Python ("¿ya existe? entonces no creo") no puede garantizar bajo concurrencia real.

**`backend/surveys/migrations/0002_response_unique_survey_response.py`** — generada con `makemigrations`, aplica esa constraint en la base de datos real (sin esto, la regla existiría solo en el código Python, no en el SQLite).

**`backend/surveys/views.py`** — manejo de la violación de la constraint:

```python
try:
    with transaction.atomic():
        response = Response.objects.create(
            survey=survey,
            external_id=payload["event_id"],
            status=payload["status"],
            answers=payload["answers"],
            submitted_at=payload["submitted_at"],
        )
    response_status = status.HTTP_201_CREATED
except IntegrityError:
    response = Response.objects.get(survey=survey, external_id=payload["event_id"])
    response_status = status.HTTP_200_OK
return ApiResponse(ResponseSerializer(response).data, status=response_status)
```

Si el evento es nuevo, se crea y se devuelve `201`. Si ya existía, la base rechaza el `INSERT` (viola la constraint), Python captura ese `IntegrityError`, busca el registro que ya estaba guardado y lo devuelve con `200` — el remitente del webhook recibe una respuesta normal, no un error, aunque haya reenviado el mismo evento.

**`backend/surveys/tests.py`** — 2 tests nuevos: el mismo `event_id` enviado 2 veces (1ª `201`, 2ª `200`, mismo `id`, solo 1 fila en la base); `event_id`s distintos siguen creando normalmente.

---

### Tarea 3 — Filtro de fechas

**`backend/surveys/serializers.py`** — nuevo serializer de validación:

```python
class DateRangeFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"detail": "'from' no puede ser posterior a 'to'."}
            )
        return attrs
```

Los campos se llaman `date_from`/`date_to` (no `from`/`to`) porque `from` es palabra reservada en Python y no se puede usar como nombre de atributo de clase. La vista mapea `from`/`to` de la URL a estos nombres internos — la API pública sigue usando `from`/`to`, tal como pide el enunciado. `DateField` valida el formato automáticamente (fecha inválida → error); el método `validate` agrega la regla extra de que `from` no puede ser posterior a `to`.

**`backend/surveys/views.py`** — uso del filtro en el endpoint:

```python
filters = DateRangeFilterSerializer(
    data={
        "date_from": request.query_params.get("from"),
        "date_to": request.query_params.get("to"),
    }
)
filters.is_valid(raise_exception=True)
date_from = filters.validated_data.get("date_from")
date_to = filters.validated_data.get("date_to")

responses = Response.objects.filter(survey=survey)
if date_from:
    responses = responses.filter(submitted_at__date__gte=date_from)
if date_to:
    responses = responses.filter(submitted_at__date__lte=date_to)
```

`raise_exception=True` hace que, si la validación falla (fecha inválida o `from > to`), DRF devuelva automáticamente un `400` con el mensaje de error. Los `if` separados para `date_from` y `date_to` son la clave de que los filtros funcionen juntos o por separado: si uno de los dos no vino en la petición, simplemente no se aplica ese `filter()` adicional.

**`frontend/src/api.js`** — construcción de la query string:

```javascript
export async function getSurveyResults(surveyId, { from, to } = {}) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const query = params.toString() ? `?${params.toString()}` : "";

  const response = await fetch(`/api/surveys/${surveyId}/results/${query}`, {
```

`{ from, to } = {}` es un segundo parámetro opcional (si no se pasa nada, no rompe). `URLSearchParams` arma la query string solo con los valores que efectivamente vinieron, evitando mandar `?from=&to=` vacíos cuando el usuario no filtró nada.

**`frontend/src/App.vue`** — 2 inputs de fecha y validación antes de llamar a la API:

```html
<input type="date" v-model="fromDate" />
<input type="date" v-model="toDate" />
<button @click="loadResults" :disabled="loading">Aplicar filtro</button>
```
```javascript
if (fromDate.value && toDate.value && fromDate.value > toDate.value) {
  error.value = "La fecha 'desde' no puede ser posterior a 'hasta'.";
  return;
}
```

La comparación `fromDate.value > toDate.value` funciona como comparación de strings porque el input `type="date"` siempre entrega el valor en formato `YYYY-MM-DD` — ese formato específico sí se puede comparar como texto y da el mismo resultado que comparar fechas. Esta validación evita una llamada a la API que ya sabemos que va a fallar; el backend igual la vuelve a validar (es la fuente de verdad real).

**`backend/surveys/tests.py`** — 5 tests nuevos: filtro solo con `from`, solo con `to`, ambos juntos, fecha con formato inválido (`400`), y `from` posterior a `to` (`400`).
