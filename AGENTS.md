# AGENTS.md — Contexto para agentes de IA e novos membros

QUERO = Quadro Universitário de Estágios Remunerados e Oportunidades. Especificação completa:
`QUERO_Documento_de_Projeto_v5.0.pdf`. Plano e decisões de protótipo: `PLANO_PROTOTIPO.md`.

## Stack (obrigatória — RNF-05)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (sync, psycopg 3), Alembic, Pydantic v2.
- Banco: PostgreSQL 16 (único). Arquivos: disco local atrás de `ArmazenamentoArquivos`.
- Frontend: React 18 + Vite + TypeScript + Tailwind, TanStack Query, React Router.
- Worker: processo Python com fila em `tarefas` (`SELECT … FOR UPDATE SKIP LOCKED`). Sem broker.

## Comandos
```bash
docker compose up -d db mailpit           # Postgres em localhost:5433, Mailpit em localhost:8025
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux/macOS: .venv/bin/
.venv/Scripts/alembic upgrade head        # aplica migrations
.venv/Scripts/python -m app.seed          # usuários de demonstração (senha quero123)
.venv/Scripts/uvicorn app.main:app --reload   # API em :8000, docs em /docs
.venv/Scripts/python -m pytest            # testes (cria o banco quero_test sozinho)
.venv/Scripts/alembic revision --autogenerate -m "descricao"   # nova migration (REVISAR à mão)
cd ../frontend && npm install && npm run dev  # SPA em :5173 com proxy /api -> :8000
```

## Estrutura do backend
- `app/core/` config, db, erros→HTTP, segurança (Argon2id/JWT), deps de RBAC, auditoria, relógio.
- `app/domain/` máquinas de estado (`estados.py`) e regras puras (sem banco, sem HTTP).
- `app/models/` SQLAlchemy. `app/schemas/` Pydantic. `app/services/` casos de uso. `app/routers/` HTTP.
- `app/worker/` jobs do worker (`python -m app.worker`): timers do edital, e-mail com retentativa,
  reprocessamento de inscrições pendentes (INT-01) e limpeza de arquivos órfãos.
- `app/integrations/` SMTP e `academico.py`: interface `ServicoAcademico`, adapter simulado por CSV
  (`seed/academico.csv`, separador `;`) e política INT-01 (timeout 5 s × 3 tentativas). Nos testes, a fixture
  `academico` (`AcademicoFalso` no conftest) substitui o serviço: use `academico.cadastrar(matricula, cr=...)`.
- `app/services/homologacao.py` homologação formal: ramo acadêmico em paralelo aos PDFs (gateway AND), dados
  congelados (RN-02), reprocessamento e reanálise (RN-05). Regra pura em `app/domain/elegibilidade.py`.
- `app/services/avaliacoes.py` fila, avaliação (§7.3), impedimento e publicação do preliminar. A ordenação
  (RN-09/RN-12) é a função pura `app/domain/classificacao.classificar` — nunca reimplemente em outro lugar.
- `app/storage/` `ArmazenamentoArquivos` (put/get/delete/listar por chave), `ArmazenamentoDisco` e `validacao.receber_pdf`
  (64 KB por bloco, %PDF-, 10 MB, SHA-256). Nos testes, a fixture `armazenamento` usa um diretório temporário.
- `app/reports/` documentos gerados: comprovante de inscrição e ata de homologação (PDF) + lista final (CSV).
- `app/services/homologacao_final.py` homologação (classificação FINAL, ata e listas gravadas somente leitura) e
  devolução para ajustes. `app/services/auditoria_consulta.py` consulta da trilha (sem escrita).
- Imutabilidade no banco (triggers): `auditoria_logs`, `classificacoes` fase FINAL, `atas_homologacao` e os
  arquivos referenciados pela ata.
- `app/routers/dev.py` ferramentas de demonstração, registradas só com ENV=dev/test: relógio
  (`/api/v1/dev/relogio/*`) e queda simulada do Sistema Acadêmico (`PUT /api/v1/dev/academico`; o estado fica no
  arquivo `data/academico_fora_do_ar`, compartilhado entre API e worker).

## Regras inegociáveis
1. **Regra de negócio no backend**, nunca só no frontend. Guardas de rota no SPA são apenas UX.
2. **Transição de estado** sempre via `MAQUINA_*.proximo(estado, evento)` → `TransicaoInvalida` = HTTP 409.
   Validação de entrada/regra = `RegraViolada` (422). Permissão = `Proibido` (403).
3. **RBAC + vínculo** em todo endpoint: use `ProReitor`, `Estudante`, `Avaliador` de `app/core/deps.py`
   e verifique posse/designação (anti-IDOR) dentro do service.
4. **Auditoria (RN-14)**: toda ação crítica chama `core.auditoria.registrar(...)` na MESMA transação,
   com `snapshot()` antes/depois. A tabela é imutável (trigger no banco).
5. **Horário oficial**: `core.relogio.agora(db)` (America/Sao_Paulo). Nunca `datetime.now()` em regra de prazo.
6. **Uploads em streaming** (chunks de 64 KB). Proibido `await file.read()` do arquivo inteiro.
7. **Sem links públicos** para PDFs de candidatos (RN-15): download só via endpoint autenticado.
8. Toda mudança de esquema via **migration Alembic revisada**. Nada de dados fictícios fora do seed.
9. Testes nomeados pelo requisito (`test_INS02_...`) e cobrindo: caminho feliz, 422, 409, 401/403, IDOR.
10. Código gerado por IA em RBAC/arquivos, auditoria e classificação exige **revisão humana**.

## Regras de negócio (resumo — detalhes no PDF §3)
RN-01 1 inscrição por estudante/edital · RN-02 vínculo+curso+CR congelados na submissão ·
RN-03 inscrição só com edital ABERTO e na janela · RN-04 PDF válido (%PDF-) ≤10 MB, versões ·
RN-05 homologação automática; reanálise do PR até início da avaliação · RN-06 só HOMOLOGADA é avaliada ·
RN-07 avaliador só vê editais designados; não pode ser candidato no mesmo edital; declara impedimento ·
RN-08 nota 0–10 (2 casas); indeferido exige justificativa · RN-09 ordena por nota; desempate CR, data original ·
RN-10 janela de recurso (48 h padrão), 1 recurso, ≤5.000 caracteres · RN-11 recurso julgado por outro avaliador
se comissão ≥2 · RN-12 N primeiros contemplados, demais suplentes · RN-13 só PR homologa; resultado imutável ·
RN-14 auditoria imutável · RN-15 documentos só para titular, comissão designada e PR.

## Status das fatias (PLANO_PROTOTIPO §2.4)
- [x] Fase 0 — esquema, migrations, máquinas de estado, auditoria imutável
- [x] Fatia 1 — autenticação local, sessões revogáveis, RBAC, layout por perfil
- [x] Fatia 2 — editais e comissão (EDT-01…05), worker (timers + e-mail), relógio de demonstração
- [x] Fatia 3 — vitrine, inscrição com upload streaming, comprovante, retificação, desistência, download protegido
- [x] Fatia 4 — homologação formal completa (documental + acadêmica), Sistema Acadêmico simulado, pendentes
  reprocessadas pelo worker, reanálise pelo PR e conferência das inscrições do edital
- [x] Fatia 5 — fila do avaliador, nota/parecer (rascunho → confirmada → retificada), impedimento com
  redirecionamento, classificação preliminar e abertura automática do recurso.
  ⚠ `app/domain/classificacao.py` + `tests/test_classificacao.py` aguardam a revisão humana do §14 item 28(c).
- [x] Fatia 6 — interposição única na janela (com anexo PDF), julgamento com bloqueio do autor do parecer
  (RN-11) ou justificativa reforçada em comissão única, reavaliação e classificação POS_RECURSO, passagem
  automática para EM_HOMOLOGACAO_FINAL (`services/recursos.py`)
- [x] Fatia 7 — homologação final com ata PDF + CSV imutáveis, devolução para ajustes, notificações no painel
  (sino), consulta de auditoria por edital/inscrição

## Pendências antes do piloto (fora do protótipo)
- Revisão humana obrigatória (§14 item 28): classificação, RBAC/arquivos e auditoria.
- Decisões pendentes do documento (§15, DP-01 a DP-09) e as lacunas L-01 a L-18 do `PLANO_PROTOTIPO.md`.
- SSO real (DP-02), API do Sistema Acadêmico (DP-03), Nginx/TLS (com o limite da L-15), backup (RNF-09),
  teste de carga de 300 usuários (RNF-01/02) e revisão WCAG 2.1 AA (RNF-08).
- Retificação formal do resultado por nova ata vinculada (RN-13) — a tabela já tem `eh_retificacao`.
