# Análise — Tarefas do CANDIDATE_INSTRUCTIONS.md

Status: `PENDENTE` | `EM ANDAMENTO` | `RESOLVIDO`

---

## 1. Problema de aislamiento

**Status:** RESOLVIDO (`backend/surveys/models.py`, `backend/surveys/views.py`, `backend/surveys/tests.py`)

**Local:** `backend/surveys/views.py` (`SurveyResultsView.get`)

**Problema confirmado:**
```python
survey = get_object_or_404(Survey, pk=survey_id)
responses = Response.objects.filter(survey=survey)
```
Busca a survey só pelo `pk`. Não existe nenhuma checagem de que `request.user` tem `Membership` na `Organization` dona da survey. Qualquer usuário autenticado consegue ler resultados de qualquer organização só incrementando o `survey_id` na URL.

**Impacto:** vazamento de dados entre tenants — o tipo de bug mais grave possível num SaaS multiempresa.

**Alternativas:**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | Filtrar o queryset por organização do usuário (`Survey.objects.filter(organization__memberships__user=request.user)`) e usar 404 genérico se não achar | Simples, direto, não revela se a survey existe (mesmo 404 para "não existe" e "sem acesso") | Lógica fica só nessa view |
| B | `permission_classes` customizada (`has_object_permission`) checando membership | Idiomático DRF, plugável em outras views futuras | Mais uma camada de indireção para um único endpoint |
| C | Manager/queryset helper (`Survey.objects.for_user(user)`) centralizando o scoping | Reutilizável — útil se amanhã surgirem mais endpoints multi-tenant | Requer tocar em `models.py` |

**Recomendação:** A + C combinados. `SurveyQuerySet.for_user(user)` usado pela view via `get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)`. Resolve o bug de forma correta, não vaza existência da survey via status code, e fica pronto para reuso se a API crescer.

**Implementação:**
- `backend/surveys/models.py`: `SurveyQuerySet.for_user(user)` filtrando por `organization__memberships__user=user`; `Survey.objects = SurveyQuerySet.as_manager()`.
- `backend/surveys/views.py`: `get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)`.

**Testes (`backend/surveys/tests.py`):**
- `test_authorized_user_can_list_results` (já existia) — comportamento correto preservado.
- `test_user_cannot_access_survey_from_another_organization` (novo) — cria uma organização/survey à qual `ana` não pertence e confirma `404`. Não depende de um segundo usuário logado: o isolamento é testado com a única credencial oficial do enunciado (`ana`/`ana123`).

3/3 testes passando.

**Verificação manual (servidor local, porta 8080 — a 8000 estava em uso):**

```powershell
curl.exe -u ana:ana123 http://127.0.0.1:8080/api/surveys/1/results/   # survey da própria org (Northwind)
curl.exe -u ana:ana123 http://127.0.0.1:8080/api/surveys/2/results/   # survey de outra org (Contoso, seed_demo cria mas sem membership pra ana)
```

| Requisição | Esperado | Obtido |
|---|---|---|
| `ana` → survey 1 (própria) | 200 | 200, `count: 3` ✅ |
| `ana` → survey 2 (outra org) | 404 | 404 `"No Survey matches the given query."` ✅ |

---

## 2. Evitar respuestas duplicadas

**Status:** RESOLVIDO (`backend/surveys/models.py`, `backend/surveys/views.py`, `backend/surveys/migrations/0002_response_unique_survey_response.py`, `backend/surveys/tests.py`)

**Local:** `backend/surveys/views.py` (`ResponseWebhookView.post`), `backend/surveys/models.py` (`Response`)

**Problema confirmado:**
```python
response = Response.objects.create(
    survey=survey,
    external_id=payload["event_id"],
    ...
)
```
Cria uma `Response` nova a cada chamada, sem checar se já existe uma com o mesmo `external_id`/`survey`. Não há `unique_together`/`UniqueConstraint` no modelo para isso. Reenvios do evento externo (retry do provedor de webhook) duplicam a resposta. Um simples "check then create" no nível de aplicação também não resolve — duas requisições quase simultâneas passam pela checagem antes de qualquer uma commitar (race condition clássica), então a idempotência precisa ser garantida no banco.

**Impacto:** contagens de resposta infladas, dados de survey incorretos.

**Alternativas:**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | `UniqueConstraint(survey, external_id)` + `get_or_create` | Simples | `get_or_create` ainda pode lançar `IntegrityError` em corrida — precisa tratar |
| B | Constraint única + `transaction.atomic()` capturando `IntegrityError` → refaz o fetch e retorna o registro existente | Idempotência garantida mesmo com requests simultâneos, é o padrão para webhooks | Um pouco mais de código |
| C | B + retorno HTTP 200 (não 201) quando já existia, devolvendo o recurso já salvo | API mais correta semanticamente para quem faz retry (idempotent response) | Muda o contrato de resposta (fácil de documentar) |

**Recomendação:** B + C. Constraint no banco é a única forma de garantir idempotência sob concorrência real (dois requests quase simultâneos); capturar `IntegrityError` e devolver o registro existente com 200 evita erro 500/409 desnecessário pro remetente do webhook, que é o comportamento esperado de um endpoint idempotente.

**Implementação:**
- `backend/surveys/models.py`: `UniqueConstraint(fields=["survey", "external_id"], name="unique_survey_response")` no `Meta` de `Response`.
- `backend/surveys/views.py`: `ResponseWebhookView.post` envolve o `Response.objects.create(...)` em `transaction.atomic()`; se estourar `IntegrityError` (constraint violada), busca o registro já existente e devolve `200` em vez de `201`.
- `backend/surveys/migrations/0002_response_unique_survey_response.py`: aplica a constraint no banco.

**Testes (`backend/surveys/tests.py`):**
- `test_webhook_is_idempotent_on_duplicate_event` (novo) — mesmo `event_id` enviado 2x: 1ª chamada `201`, 2ª `200` com o mesmo `id`, só 1 `Response` no banco.
- `test_webhook_creates_separate_response_for_different_event_id` (novo) — `event_id`s diferentes continuam criando normalmente.

5/5 testes passando.

**Verificação manual (servidor local, porta 8080):** mesmo payload (`event_id: manual-001`) enviado via `curl` **3 vezes seguidas** — sempre devolveu o mesmo `id: 4`. Conferido via `GET /api/surveys/1/results/`: `count` subiu de 3 pra 4 (não pra 6), confirmando que as 3 chamadas não duplicaram.

---

## 3. Añadir filtro de fechas

**Status:** PENDENTE

**Local:** `backend/surveys/views.py` (backend, ausente) e `frontend/src/App.vue` (frontend, ausente)

**Problema confirmado:** não existe nenhum tratamento de query params na view (`request.query_params` nunca é lido) e o `App.vue` não tem nenhum input de data — só carrega `surveyId = 1` fixo, sem filtros.

**Alternativas (backend):**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | Parse manual com `django.utils.dateparse.parse_date`, filtro `submitted_at__date__gte/lte`, 400 em caso de formato inválido | Zero dependências novas | Validação manual, mais verboso |
| B | `django-filter` com `DateFromToRangeFilter` | Idiomático DRF, menos código | Adiciona dependência nova ao `requirements.txt` |
| C | Serializer DRF dedicado para validar `from`/`to` (mesmo padrão já usado em `WebhookSerializer`) | Consistente com o estilo já existente no projeto, erros de validação formatados automaticamente pelo DRF | Mais um serializer pequeno |

**Recomendação:** C — mantém o mesmo padrão do código existente (serializers para validação de entrada), não adiciona dependência, e segue a convenção do repositório.

**Alternativas (frontend):** dois `<input type="date">` com `v-model`, disparando `loadResults()` ao mudar (ou botão "Aplicar"). Validação client-side de `from > to` antes de chamar a API, complementando o 400 que o backend deve retornar nesse caso.

**Comportamento para datas inválidas (a definir e documentar):**
- formato inválido → `400` com mensagem clara.
- `from > to` → `400` (intervalo inválido).
- só `from` ou só `to` → filtro funciona isoladamente (requisito explícito do enunciado).

**Testes a adicionar:**
- filtro só com `from`, só com `to`, com ambos.
- data inválida retorna 400.
- `from > to` retorna 400 (ou comportamento definido).
- filtro combinado com o isolamento por organização da Tarefa 1.

---

## Extra — achados fora das 3 obrigações imediatas

> Não fazem parte do escopo das 3 tarefas acima. Registrados aqui, resolvidos por último (se sobrar tempo), depois que as 3 obrigações imediatas estiverem prontas.

### E1. `TemplateDoesNotExist` na Browsable API do DRF

**Status:** PENDENTE (fica pra depois das 3 tarefas)

Acessar qualquer endpoint da API direto pelo navegador (`Accept: text/html`) quebra com `500 TemplateDoesNotExist`, porque `TEMPLATES = []` em `backend/config/settings.py`, mas o DRF usa `BrowsableAPIRenderer` por padrão (não há `DEFAULT_RENDERER_CLASSES` configurado restringindo pra só JSON). Achado ao testar visualmente a Tarefa 1 no browser. Não afeta o front (que já manda `Accept: application/json` implícito via `fetch`) nem os testes automatizados/curl — só quebra quando alguém abre a URL da API direto no navegador.

**Correção (quando formos nessa, sem alternativas — é um ajuste direto):** em `REST_FRAMEWORK` no `settings.py`, adicionar `"DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]`, removendo o `BrowsableAPIRenderer` da lista padrão. Não precisa mexer em `TEMPLATES`.

### E2. Estrutura de git (histórico do repositório)

**Status:** RESOLVIDO — repo único criado na raiz, publicado em https://github.com/ramonzeraa/prueba_tecnica_webtools (branch `main`, história consolidada em 1 commit por decisão do usuário).

### E3. `AI_NOTES.md`

**Status:** PENDENTE — entregável obrigatório do enunciado (não é um "problema", é um documento que falta escrever no fechamento).

### E4. Itens de baixa prioridade, sem ação planejada

- `frontend/src/App.vue`: `surveyId` fixo em `1`, sem seletor/rota.
- `SurveyResultsView`: sem paginação.
- `WEBHOOK_TOKEN`: comparação de string não é constant-time (timing attack teórico).
- `SECRET_KEY`/`WEBHOOK_TOKEN`/senha `ana123` hardcoded: são os valores de demo do próprio scaffold, documentado como risco conhecido (não real) em `SOLUTION.md`.
