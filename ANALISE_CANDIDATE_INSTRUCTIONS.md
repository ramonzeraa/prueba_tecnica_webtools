# Análise — Tarefas do CANDIDATE_INSTRUCTIONS.md

Status: `PENDENTE` | `EM ANDAMENTO` | `RESOLVIDO`

---

## Tarefa 1 — Isolamento entre empresas

**Status:** RESOLVIDO (`backend/surveys/models.py`, `backend/surveys/views.py`, `backend/surveys/tests.py`)

**Local:** `backend/surveys/views.py:11-24` (`SurveyResultsView.get`)

**Problema confirmado:**
```python
survey = get_object_or_404(Survey, pk=survey_id)
responses = Response.objects.filter(survey=survey)
```
Busca a survey só pelo `pk`. Não existe nenhuma checagem de que `request.user` tem `Membership` na `Organization` dona da survey. Qualquer usuário autenticado (`ana`, `bob`, etc.) consegue ler resultados de qualquer organização só incrementando o `survey_id` na URL. Confirmado com os dados de seed: `ana` → Northwind, `bob` → Contoso, e ambas surveys existem (ids 1 e 2).

**Impacto:** vazamento de dados entre tenants — o tipo de bug mais grave possível num SaaS multiempresa.

**Alternativas:**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | Filtrar o queryset por organização do usuário (`Survey.objects.filter(organization__memberships__user=request.user)`) e usar 404 genérico se não achar | Simples, direto, não revela se a survey existe (mesmo 404 para "não existe" e "sem acesso") | Lógica fica só nessa view |
| B | `permission_classes` customizada (`has_object_permission`) checando membership | Idiomático DRF, plugável em outras views futuras | Mais uma camada de indireção para um único endpoint |
| C | Manager/queryset helper (`Survey.objects.for_user(user)`) centralizando o scoping | Reutilizável — útil se amanhã surgirem mais endpoints multi-tenant | Requer tocar em `models.py` |

**Recomendação:** A + C combinados. Cria um método simples no manager (`for_user`) usado pela view via `get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)`. Resolve o bug de forma correta, não vaza existência da survey via status code, e fica pronto para reuso se a API crescer — dado que o teste é explicitamente sobre um "SaaS multiempresa".

**Testes a adicionar:**
- usuário de uma org não acessa survey de outra org (404 esperado).
- usuário autorizado continua acessando normalmente (comportamento atual preservado).
- usuário sem nenhuma membership (edge case).

---

## Tarefa 2 — Respostas duplicadas no webhook

**Status:** PENDENTE

**Local:** `backend/surveys/views.py:27-48` (`ResponseWebhookView.post`), `backend/surveys/models.py:37-51` (`Response`)

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

**Testes a adicionar:**
- reenvio do mesmo `event_id` não cria segunda `Response`.
- simular duas escritas "simultâneas" (mesma constraint, `IntegrityError` tratado) sem duplicar.
- eventos com `external_id` diferentes continuam criando respostas normalmente.

---

## Tarefa 3 — Filtro de datas nos resultados

**Status:** PENDENTE

**Local:** `backend/surveys/views.py:11-24` (backend, ausente) e `frontend/src/App.vue` (frontend, ausente)

**Problema confirmado:** não existe nenhum tratamento de query params na view (`request.query_params` nunca é lido) e o `App.vue` não tem nenhum input de data — só carrega `surveyId = 1` fixo, sem filtros.

**Alternativas (backend):**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | Parse manual com `django.utils.dateparse.parse_date`, filtro `submitted_at__date__gte/lte`, 400 em caso de formato inválido | Zero dependências novas | Validação manual, mais verboso |
| B | `django-filter` com `DateFromToRangeFilter` | Idiomático DRF, menos código | Adiciona dependência nova ao `requirements.txt` |
| C | Serializer DRF dedicado para validar `from`/`to` (mesmo padrão já usado em `WebhookSerializer`) | Consistente com o estilo já existente no projeto, erros de validação formatados automaticamente pelo DRF | Mais um serializer pequeno |

**Recomendação:** C — mantém o mesmo padrão do código existente (serializers para validação de entrada), não adiciona dependência, e already segue a convenção do repositório.

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
