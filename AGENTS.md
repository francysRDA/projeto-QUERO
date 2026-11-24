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
- `app/storage/`, `app/integrations/`, `app/reports/`, `app/worker/` — a preencher nas próximas fatias.

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
- [ ] Fatia 2 — editais e comissão (EDT-01…05)
- [ ] Fatia 3 — vitrine, inscrição, upload, comprovante (INS-01, 02, 04, 05, 07)
- [ ] Fatia 4 — homologação formal + Sistema Acadêmico stub (INS-03, INT-01)
- [ ] Fatia 5 — avaliação e resultado preliminar (AVA-01, 02)
- [ ] Fatia 6 — recursos (AVA-03, 04)
- [ ] Fatia 7 — homologação final, ata, notificações, auditoria (HOM-01, 02, TRV-01, 03)
