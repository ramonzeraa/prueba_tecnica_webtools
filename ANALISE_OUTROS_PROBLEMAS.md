# Análise — Problemas fora do escopo direto do CANDIDATE_INSTRUCTIONS.md

Status: `PENDENTE` | `EM ANDAMENTO` | `RESOLVIDO`

---

## 1. [CRÍTICO] Estrutura de git quebrada — bloqueia o push para o GitHub

**Status:** PENDENTE — precisa ser resolvido antes de qualquer `git add`/`commit`/`push`.

**Problema confirmado:**
- `C:\Users\Ramon\Desktop\prueba_tecnica_webtools` (raiz do projeto) **não tem `.git` próprio**.
- `frontend/` também não tem `.git` próprio. Como o git sobe diretórios até achar um repositório, qualquer comando `git` rodado dentro de `frontend/` (ou na raiz do projeto) está na verdade operando o repositório de `C:\Users\Ramon\.git` — o **repositório pessoal do usuário**, com remote `https://github.com/ramonzeraa/plataforma_financas.git`, que já rastreia arquivos do perfil do Windows inteiro (Documents, Downloads, AppData, NTUSER.DAT, node_modules soltos, etc.). Um `git add .` nesse contexto arriscaria commitar/enviar arquivos pessoais para um repositório errado.
- `backend/` tem seu próprio `.git`, com remote correto: `https://github.com/ramonzeraa/prueba_tecnica_webtools_backend.git`.

**Por que isso importa agora:** o pedido "subir back e front pro GitHub" não pode ser executado com segurança até decidir a estrutura correta.

**Alternativas:**

| # | Abordagem | Prós | Contras |
|---|---|---|---|
| A | Um único repositório novo na raiz (`prueba_tecnica_webtools`) contendo `backend/` e `frontend/` como subpastas normais | Bate com o enunciado ("entrega el repositorio completo"), 1 PR/commit history só, mais simples de revisar para o entrevistador | Precisa migrar o histórico do `backend/.git` atual (ou recomeçar) |
| B | Manter 2 repositórios separados (`prueba_tecnica_webtools_backend` já existe; criar `prueba_tecnica_webtools_frontend`) | Aproveita o remote já configurado do backend | Enunciado pede "el repositorio" (singular); entrevistador teria que abrir 2 links |
| C | Monorepo com `backend/` e `frontend/` como git submodules apontando pros repos separados | Mantém os 2 remotes existentes | Complexidade desnecessária para o escopo do teste |

**Recomendação:** A. Vou perguntar sua preferência antes de mexer em git (ação com efeito em repositório remoto/compartilhado).

**Ação necessária de qualquer forma, independente da opção escolhida:** nunca rodar `git add`/`commit` na raiz ou em `frontend/` até existir um `.git` dedicado ao projeto ali — hoje isso cairia no repositório pessoal.

---

## 2. [ALTO] `backend/.git` está rastreando a venv inteira

**Problema confirmado:** `git -C backend ls-files` retorna **7332 arquivos**, dos quais **7297 são de `venv/site-packages`** (Django, asgiref, etc.). Também rastreia `db.sqlite3` e vários `__pycache__/*.pyc`. Não existe `.gitignore` dentro de `backend/`.

**Impacto:** repositório pesado, diffs de dependências binárias, risco de subir bytecode desatualizado, banco local no histórico.

**Correção (direta, sem alternativas — é um erro de setup, não uma decisão de design):**
- criar `backend/.gitignore` com `venv/`, `.venv/`, `__pycache__/`, `*.pyc`, `db.sqlite3`.
- `git rm -r --cached venv db.sqlite3 **/__pycache__` no repo do backend.

---

## 3. [MÉDIO] `.gitignore` da raiz está desalinhado com a pasta real

**Problema confirmado:** raiz ignora `backend/.venv/`, mas a pasta criada de fato é `backend/venv/` (sem o ponto). Além do problema #1 (esse `.gitignore` nem está sendo aplicado a um repo do projeto hoje), o padrão em si já nasce errado.

**Correção:** ajustar para `backend/venv/` (ou `backend/**/venv/` para cobrir os dois nomes possíveis, já que o `CANDIDATE_INSTRUCTIONS.md` instrui `python -m venv .venv`).

---

## 4. [MÉDIO] `AI_NOTES.md` e `SOLUTION.md` ainda não existem

Ambos são entregáveis obrigatórios pelo enunciado (seção "Uso de inteligencia artificial" e "Entrega"). Vou preencher ao longo do trabalho, conforme formos decidindo/aplicando cada mudança, para não reconstruir de memória no final.

---

## 5. [BAIXO] Frontend com `surveyId` fixo em 1

**Local:** `frontend/src/App.vue:5`. Não há seletor de survey nem rota. Fora do escopo das 3 tarefas (não pedido), mas relevante para o filtro de data da Tarefa 3 ser testado manualmente contra a survey certa (Northwind, id 1, é a única com responses no seed). Não vou mexer nisso a menos que decidam que faz parte do fluxo de teste manual.

---

## 6. [BAIXO] Sem paginação em `SurveyResultsView`

`Response.objects.filter(survey=survey)` retorna tudo de uma vez. Não é exigido pelo enunciado; vale citar em "mejoras futuras" no `SOLUTION.md`.

---

## 7. [BAIXO] Comparação do `WEBHOOK_TOKEN` não é constant-time

`request.headers.get(...) != settings.WEBHOOK_TOKEN` é uma comparação de string normal (vulnerável a timing attack, risco teórico/baixo). Fora do escopo das tarefas; citar como observação em `SOLUTION.md`, não vou corrigir sem pedido explícito.

---

## 8. [INFORMATIVO] Configuração de dev (SECRET_KEY, DEBUG=True)

Esperado para um teste técnico local (`config/settings.py`). Não é um problema a corrigir — só não deve ser tratado como referência de produção no `SOLUTION.md`.
