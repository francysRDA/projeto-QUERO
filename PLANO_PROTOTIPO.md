# QUERO — Análise do Documento de Projeto v5.0 e Plano de Implementação do Protótipo

> Fonte: `QUERO_Documento_de_Projeto_v5.0.pdf` (20/11/2026, 24 páginas). Este plano foi elaborado em 24/11/2026.

---

## Parte 1 — Análise do documento

### 1.1 Resumo

O QUERO é um **monólito modular** para gerir seleções acadêmicas (estágio, monitoria, bolsa) de ponta a ponta:
**edital → inscrição → homologação formal → avaliação de mérito → resultado preliminar → recurso → homologação final (ata)**.

| Aspecto | Definição do documento |
|---|---|
| Stack | React + Vite + TS (Tailwind) · Python 3.12 + FastAPI + SQLAlchemy + Alembic · PostgreSQL 16 |
| Arquivos | Disco local atrás da interface `ArmazenamentoArquivos` (put/get/delete por chave lógica) |
| Assíncrono | Worker Python com fila no próprio Postgres (`SELECT … FOR UPDATE SKIP LOCKED`) |
| Papéis | `ESTUDANTE`, `AVALIADOR`, `PRO_REITOR` (+ externos: Sistema Acadêmico, SSO, SMTP) |
| Domínio | 15 regras de negócio (RN-01…15), 22 requisitos (EDT, INS, AVA, HOM, INT, TRV), 4 máquinas de estado |
| Infra | `docker compose up` local; 1–2 VMs; sem serviços pagos |
| Método | 7 fatias verticais, contrato (schema + OpenAPI) antes das telas, DoD com testes de 409/422/401/403/IDOR |

### 1.2 Pontos fortes

- **Rastreabilidade excelente**: RN → RF → UC → endpoint → teste, com IDs estáveis. Facilita muito o trabalho com agentes de IA.
- **Máquinas de estado explícitas** (§7) com regra uniforme "transição inválida = HTTP 409".
- **Escopo do MVP bem cortado** (§2.1) e premissas temporárias para cada decisão pendente (§15) — nada bloqueia o início.
- **Decisões de infraestrutura frugais e justificadas** (disco local vs. bytea vs. MinIO; ClamAV opcional; worker sem broker).
- **Definição de Pronto** que proíbe "telas de mentira" — alinhada ao objetivo de protótipo *funcional*.

### 1.3 Lacunas e inconsistências encontradas (a resolver no protótipo)

Itens que o documento não cobre ou em que as seções se contradizem. Para cada um, proponho uma **decisão de protótipo** (marcada como premissa, reversível).

| # | Problema | Onde | Decisão proposta para o protótipo |
|---|---|---|---|
| L-01 | **Não há tabela de resultado/classificação.** RN-12 (contemplado/suplente) e RN-13 (resultado imutável) exigem persistir posição e situação, mas o §10 não tem onde. | §10, RN-12/13 | Criar `classificacoes` (edital_id, inscricao_id, posicao, nota, situacao `CONTEMPLADO/SUPLENTE/NAO_CLASSIFICADO`, fase `PRELIMINAR/POS_RECURSO/FINAL`). A fase FINAL é o snapshot imutável. |
| L-02 | **Não há distribuição de inscrições entre avaliadores.** `avaliacoes.inscricao_id` é UNIQUE e não existe registro de "quem deve avaliar o quê" nem de impedimento declarado (RN-07, UC-07 E1). | §10, RN-07 | Criar `impedimentos` (inscricao_id, avaliador_id, motivo). Fila do avaliador = homologadas do edital sem avaliação de outro membro e sem impedimento dele. Primeiro a salvar rascunho "assume" a inscrição. |
| L-03 | **Faltam tabelas de infraestrutura**: fila do worker e revogação de refresh token (RNF-06). | §8.2, §10 | Criar `tarefas` (tipo, payload JSONB, executar_em, tentativas, status) e `sessoes` (refresh_token_hash, expira_em, revogada_em). |
| L-04 | **RN-01 × UNIQUE(edital_id, estudante_id)**: "no máximo uma inscrição *ativa*" sugere poder reinscrever após desistência, mas a constraint impede. | RN-01, §10 | Manter UNIQUE: desistência é definitiva. Registrar como pergunta à Pró-Reitoria. |
| L-05 | **Perfil único por usuário** (`usuarios.perfil`) contradiz RN-07/EDT-04, que bloqueiam o mesmo usuário ser avaliador e candidato no mesmo edital (o que só faz sentido se alguém pode ter os dois papéis, ex.: pós-graduando monitor). | §10, RN-07 | Protótipo: manter coluna única, mas implementar a checagem de conflito por edital (barata e já prevê a evolução para tabela `usuario_papeis`). |
| L-06 | **Retificação a partir de `PENDENTE_VALIDACAO_VINCULO`** não está na máquina §7.2. | §7.2, INS-05 | Permitir: substitui arquivos e mantém o status pendente. |
| L-07 | **`criterios_pontuacao` (JSONB) não é usado em nenhuma regra** — a nota de mérito é um número único 0–10. | §10, RN-08 | Protótipo: nota única; o JSON é apenas descritivo (exibido ao avaliador). |
| L-08 | **`data_homologacao_final` e `data_resultado_preliminar`** são obrigatórias mas só parcialmente validadas em EDT-02 e não acionam timer. | EDT-02, §7.5 | Validar ordem completa do cronograma; tratar ambas como datas informativas (sem timer). |
| L-09 | **Imutabilidade da auditoria** depende só da aplicação ("apenas INSERT"). | RNF-10 | Reforçar no banco: trigger que rejeita UPDATE/DELETE em `auditoria_logs` (e em `classificacoes` fase FINAL). |
| L-10 | **Biblioteca de PDF e formato do protocolo** não definidos (comprovante, ata). | INS-04, HOM-02 | ReportLab; protocolo `QUERO-{ano}-{edital_id:04d}-{seq:06d}`. |
| L-11 | `arquivos.tamanho_bytes ≤ 10 MB` também vale para ata/CSV gerados. | §10 | Aceitável; se necessário, aplicar o CHECK só quando `inscricao_id IS NOT NULL`. |
| L-12 | `cpf NOT NULL` pode não vir do SSO e conflita com minimização LGPD. | §10, §13.1 | Tornar `cpf` opcional no protótipo. |
| L-13 | Upload de **1 PDF por documento exigido** está implícito, não explícito; INS-02 menciona multipart, mas a rota é única. | INS-02, §11 | Uma requisição multipart com um arquivo por `documento_exigido_id`. Streaming via chunks de 64 KB (sem `await file.read()`). |
| L-15 | **Limite do Nginx × inscrição com vários PDFs**: `client_max_body_size 15m` (RNF-03) recusaria uma inscrição com 2+ PDFs de 10 MB, pois todos vão numa única requisição multipart. | RNF-03, INS-02 | Em produção, usar ~`45m` no Nginx (ou limite = docs × 10 MB + margem). O backend continua cortando cada arquivo em 10 MB. |
| L-14 | Numeração editorial quebrada (listas começam em 6, 11, 16, 19, 24). | §6.2, §9.2, §14 | Apenas cosmético — corrigir na v5.1. |
| L-16 | **Quem pode recorrer?** RN-10 diz "cada candidato", mas o recurso é contra o resultado de mérito; quem foi indeferido na homologação formal não tem nota a contestar. | RN-05, RN-10 | Só recorre quem tem classificação preliminar (participou do mérito). Indeferimento formal segue pela reanálise do PR (RN-05). Validar com as Pró-Reitorias. |
| L-17 | **"Justificativa reforçada" (RN-11)** não tem critério objetivo. | RN-11 | Mínimo de 100 caracteres + `destaque = true` na auditoria. Ajustável em `schemas/recurso.py`. |
| L-18 | **Reanálise não corrige o CR congelado.** Um candidato homologado por reanálise (ex.: CR revisado pela secretaria) continua com o CR antigo no desempate (RN-09). | RN-02, RN-05, RN-09 | Mantido conforme RN-02. Se a Pró-Reitoria quiser, a reanálise pode passar a aceitar um CR corrigido, com auditoria. |

### 1.4 Decisões pendentes (§15) que afetam o protótipo

Todas têm premissa adotada; o protótipo segue as premissas e **isola o ponto de troca** em uma interface:

| DP | Premissa no protótipo | Ponto de isolamento |
|---|---|---|
| DP-01 papel operacional | só `PRO_REITOR` | enum `Perfil` + dependência `require_roles()` |
| DP-02 OIDC × SAML | **login local Argon2id + JWT**; OIDC fica como adapter desligado | `core/auth/` com `ProvedorIdentidade` |
| DP-03 API acadêmica | **stub** lendo `seed/academico.csv` + modo "indisponível" configurável | `integrations/academico.py` (`ServicoAcademico`) |
| DP-05/06 | CR congelado + data original; recurso 48 h | parâmetros do edital |
| DP-08 ClamAV | desligado; validação `%PDF-` + SHA-256 | `storage/validacao.py` |

---

## Parte 2 — Plano de implementação do protótipo funcional

### 2.1 Objetivo e definição de "protótipo funcional"

Demonstrar **um edital completo, do rascunho à ata**, com dados reais no PostgreSQL, regras aplicadas no backend e testes automatizados — rodando com `docker compose up`.

**Fora do protótipo** (mantém-se a interface para depois): SSO real, API acadêmica real, ClamAV, Nginx/TLS de produção, backup automatizado, teste de carga de 300 usuários (fica um script Locust básico), conformidade WCAG completa (apenas boas práticas básicas).

**Critério de sucesso**: o roteiro de demonstração da §2.8 roda inteiro pela interface, e `pytest` passa com cobertura das transições inválidas, RBAC e IDOR.

### 2.2 Arquitetura e bibliotecas

```
quero/
├── AGENTS.md                  # contexto p/ agentes (stack, comandos, RNs resumidas)
├── docker-compose.yml         # db (postgres:16), mailpit, backend, worker, frontend
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/        # config (pydantic-settings), db, auth (JWT/Argon2), rbac, auditoria, relógio
│   │   ├── domain/      # máquinas de estado puras + regras (classificação, elegibilidade)
│   │   ├── storage/     # ArmazenamentoArquivos, ArmazenamentoDisco, validação PDF
│   │   ├── integrations/# ServicoAcademico (stub CSV), Email (SMTP)
│   │   ├── models/      # SQLAlchemy 2.0
│   │   ├── schemas/     # Pydantic v2
│   │   ├── services/    # casos de uso (orquestram domain + models + auditoria)
│   │   ├── routers/     # auth, editais, inscricoes, arquivos, avaliacoes, recursos, homologacao, auditoria, notificacoes
│   │   ├── reports/     # comprovante, ata, listas (ReportLab + csv)
│   │   └── worker/      # loop SKIP LOCKED + jobs agendados
│   ├── seed/            # usuários, academico.csv, PDFs de exemplo
│   └── tests/
└── frontend/
    ├── src/{api,pages,components,hooks,auth}
    └── package.json
```

| Camada | Escolha | Motivo |
|---|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 (sync + psycopg 3), Alembic, Pydantic v2 | sync simplifica transações e testes; Uvicorn com workers dá conta do protótipo |
| Auth | `argon2-cffi`, `PyJWT`; access 15 min + refresh em cookie HttpOnly/SameSite=Lax | RNF-06 |
| PDFs | `reportlab` | sem dependência nativa pesada |
| E-mail dev | **Mailpit** (container) | ver e-mails reais em `localhost:8025` |
| Testes | `pytest`, `httpx`/TestClient, Postgres real em container (banco `quero_test`) | DoD exige persistência real |
| Frontend | React 18 + Vite + TS, Tailwind, React Router, TanStack Query, React Hook Form + Zod | padrão, tipado |
| Cliente API | `openapi-typescript` gerado a partir de `/openapi.json` | contrato único (§14 item 24) |
| Relógio | serviço `Relogio` injetável (America/Sao_Paulo) | permite testar prazos e timers sem esperar |

**Decisão importante para demo:** o serviço `Relogio` + um endpoint de dev `POST /api/v1/dev/avancar-relogio` (habilitado só com `ENV=dev`) permite atravessar as fases do edital em minutos durante a apresentação.

### 2.3 Fase 0 — Fundação e contrato (antes das fatias)

1. Repositório, `docker-compose.yml`, `AGENTS.md`, lint (ruff, eslint), `Makefile`/scripts (`up`, `migrate`, `seed`, `test`).
2. **Migration inicial** com as 12 tabelas do §10 + ajustes L-01, L-02, L-03, L-09, L-12.
3. **`domain/`**: enums e tabelas de transição das 4 máquinas (§7.1–7.4) como dados (`dict[(estado, evento)] -> estado`), função `transicionar()` que lança `TransicaoInvalida` → handler global devolve 409.
4. Testes parametrizados: **todas** as combinações (estado × evento) fora da tabela retornam erro.
5. Auditoria: `registrar(sessao, usuario, acao, entidade, id, antes, depois, ip)` chamada dentro da mesma transação da ação; trigger anti-UPDATE/DELETE.
6. Esqueleto dos schemas Pydantic de todas as rotas do §11 → gerar OpenAPI → **revisão humana do contrato**.

**Saída:** `docker compose up` sobe tudo, `alembic upgrade head` cria o banco, `pytest` roda os testes de máquinas de estado.

### 2.4 Fatias verticais

Cada fatia entrega **migration (se houver) → service → router → testes → tela**, e só fecha quando cumpre o DoD (§4.7 do documento).

#### Fatia 1 — Autenticação e RBAC · TRV-02, RNF-05, RNF-06
- Backend: `POST /auth/login` (dev, Argon2id), `POST /auth/refresh`, `POST /auth/logout` (revoga em `sessoes`), `GET /auth/me`; dependência `require_roles(...)`; seed com 1 pró-reitor, 3 avaliadores, 6 estudantes.
- Frontend: tela de login, layout por perfil, guarda de rotas, interceptor de refresh.
- Testes: 401 sem token, 403 por papel, refresh revogado após logout, senha nunca em texto puro.

#### Fatia 2 — Editais e comissão · EDT-01…05, RN-07, RN-14
- Backend: CRUD em RASCUNHO; `publicar` com validação de cronograma/cursos/documentos (422); edição restrita após publicação (só descrição, auditada); `cancelar` com justificativa e notificação enfileirada; `comissao` com bloqueio de candidato no mesmo edital.
- Worker: job de timer `ABERTO → INSCRICOES_ENCERRADAS` e `→ EM_AVALIACAO` pelas datas.
- Frontend (Pró-Reitor): lista de editais, formulário em etapas (dados, cursos, documentos, cronograma), ação publicar/cancelar, designação de comissão.
- Testes: 422 de cada regra do cronograma, 409 em transições inválidas, auditoria gerada, avaliador não-designado não vê o edital.

#### Fatia 3 — Vitrine, inscrição e comprovante · INS-01, INS-02, INS-04, INS-05, INS-07, RN-01, RN-03, RN-04
- Storage: `ArmazenamentoDisco` (chunks 64 KB, `%PDF-`, ≤ 10 MB, SHA-256, escrita em arquivo temporário + rename atômico).
- Backend: `GET /editais` com filtros (curso, categoria, modalidade, faixa de valor); `POST /editais/{id}/inscricoes` multipart; `retificar` (nova versão, `ativo=false` na anterior); `desistir`; `GET /inscricoes/me`; `comprovante` em PDF; `GET /arquivos/{id}/download` com checagem titular/comissão/PR.
- Frontend (Estudante): vitrine com filtros, detalhe do edital, formulário de inscrição com um campo por documento exigido, painel "Minhas inscrições", download do comprovante.
- Testes: não-PDF/11 MB rejeitados (422), documento faltando (422), 2ª inscrição (409), fora da janela (409), **IDOR**: estudante B baixando arquivo do estudante A (403/404).

#### Fatia 4 — Homologação formal e integração acadêmica · INS-03, INT-01, RN-02, RN-05
- Integração: `ServicoAcademico` stub (CSV) com timeout 5 s × 3 tentativas e modo falha simulada.
- Backend: na submissão, checagem acadêmica e documental em paralelo (`asyncio.gather`/thread pool) → HOMOLOGADA / INDEFERIDA (todos os motivos) / PENDENTE; congela vínculo, curso, CR; worker reprocessa pendentes; `reanalisar` pelo PR até `data_inicio_avaliacao`.
- Frontend: motivos de indeferimento ao estudante; tela de reanálise para o PR.
- Testes: cada motivo de indeferimento, pendente → homologada pelo worker, pendente expirado → indeferida, reanálise após prazo (409), justificativa obrigatória (422).

> Nota: as Fatias 3 e 4 dependem uma da outra na submissão; implemente a 3 já chamando um `homologar()` simples e complete-o na 4.

#### Fatia 5 — Avaliação de mérito e resultado preliminar · AVA-01, AVA-02, RN-06…09, RN-12
- Backend: fila do avaliador (L-02); `PUT /inscricoes/{id}/avaliacao` (rascunho/confirmar/retificar com motivo); declaração de impedimento obrigatória para confirmar; registro de impedimento; `resultado-preliminar` só com todas confirmadas → grava `classificacoes` PRELIMINAR e abre janela de recurso (`EM_RECURSO`, timer de `prazo_recurso_horas`).
- `domain/classificacao.py`: função pura `classificar(candidatos, vagas, criterios_desempate)` — **revisão humana obrigatória** (§14 item 28).
- Frontend (Avaliador): fila, visualizador de PDF via stream autenticado, formulário de nota/parecer, botão publicar preliminar.
- Testes: nota fora de 0–10, indeferido sem justificativa, desempate por CR e depois por data original (retificação não penaliza), contemplados × suplentes, nota invisível ao estudante antes da publicação.

#### Fatia 6 — Recursos · AVA-03, AVA-04, RN-10, RN-11
- Backend: `POST /inscricoes/{id}/recursos` (1 por candidato, ≤ 5.000 caracteres, PDF opcional, só na janela); `julgar` (assumir → EM_ANALISE → DEFERIDO/INDEFERIDO); autor do parecer original bloqueado (403) se comissão ≥ 2; comissão de 1 exige justificativa reforçada + flag na auditoria; deferimento retifica a avaliação e recalcula `classificacoes` POS_RECURSO; worker move edital para EM_HOMOLOGACAO_FINAL quando janela fechou e não há recursos abertos.
- Frontend: botão de recurso só dentro da janela; tela de julgamento.
- Testes: 2º recurso (409), fora da janela (409), autor original (403), recálculo correto da classificação.

#### Fatia 7 — Homologação final, ata, notificações e auditoria · HOM-01, HOM-02, TRV-01, TRV-03, RN-13, RN-14
- Backend: `homologar-final` (bloqueia com recurso pendente) → classificação FINAL imutável, ata PDF + listas PDF/CSV gravadas como arquivos, edital ENCERRADO, notificações para todos; `devolver-ajustes` → EM_AVALIACAO com justificativa; `GET /auditoria` filtrável; `GET /notificacoes` + marcar lida; worker envia e-mails com retentativa.
- Frontend (PR): painel de homologação (contemplados, suplentes, indeferidos, recursos), downloads da ata/CSV, tela de auditoria; sino de notificações para todos os perfis.
- Testes: homologar com recurso aberto (409), não-PR (403), tentativa de alterar resultado após homologação (409), auditoria sem rota de edição/exclusão, e-mail com falha reenviado.

### 2.5 Worker (transversal, cresce a cada fatia)

Um processo `python -m app.worker` com loop de ~5 s:

| Job | Fatia | Gatilho |
|---|---|---|
| Fechar inscrições / iniciar avaliação | 2 | datas do edital |
| Enviar e-mail (retentativa exponencial, máx. 5) | 3 | tarefa `EMAIL` |
| Reprocessar `PENDENTE_VALIDACAO_VINCULO` | 4 | a cada 5 min; expira em `data_inicio_avaliacao` |
| Encerrar janela de recurso | 6 | `prazo_recurso_horas` |
| Limpar arquivos órfãos > 24 h | 3 | diário |

Todos usam `SELECT … FOR UPDATE SKIP LOCKED` e são idempotentes (podem rodar 2 workers sem duplicar).

### 2.6 Estratégia de testes

- **Unitários** (`domain/`): máquinas de estado (todas as transições inválidas), classificação/desempate, validação de PDF.
- **Integração** (API + Postgres real): critérios de aceite de cada requisito, nomeados pelo ID (`test_INS02_rejeita_nao_pdf`).
- **Segurança**: matriz parametrizada rota × papel (401/403) e testes de IDOR para arquivos, inscrições e avaliações.
- **E2E de fumaça** (opcional, Playwright): o roteiro da §2.8.
- **Carga** (fora do DoD do protótipo): `locustfile.py` com o mix 70/20/10 do §12.3, para rodar quando houver VM.

### 2.7 Cronograma sugerido

Considerando equipe de 3–4 pessoas com apoio de agentes de IA, sprints de 1 semana:

| Semana | Entrega |
|---|---|
| 1 | Fase 0 + Fatia 1 |
| 2 | Fatia 2 |
| 3 | Fatias 3 e 4 (inscrição + homologação formal) |
| 4 | Fatia 5 |
| 5 | Fatia 6 |
| 6 | Fatia 7 + roteiro de demo + correções |

Ponto de controle ao fim da semana 3: um estudante consegue se inscrever e ver o status homologado/indeferido — é o momento ideal para validar com os patrocinadores.

### 2.8 Roteiro de demonstração (aceite do protótipo)

1. Pró-Reitor cria edital de monitoria (2 vagas, CR ≥ 7,0, 2 documentos), designa 2 avaliadores e publica.
2. Cinco estudantes se inscrevem: 3 elegíveis, 1 com CR 6,5 (indeferido com motivo), 1 com o Sistema Acadêmico "fora do ar" (pendente → homologado pelo worker). Um deles retifica um PDF.
3. Tentativa de upload de um `.exe` renomeado para `.pdf` → recusado.
4. Avança o relógio: inscrições encerram e a avaliação começa.
5. Avaliadores confirmam notas, incluindo um empate de nota resolvido pelo CR; um avaliador declara impedimento em um candidato.
6. Publica o resultado preliminar: 2 contemplados e os suplentes.
7. O 3º colocado interpõe recurso; o avaliador autor tenta julgar (bloqueado); o outro avaliador defere, e a classificação muda.
8. Avança o relógio: a janela fecha e o edital vai para homologação final.
9. Pró-Reitor homologa; ata PDF e CSV são gerados; e-mails aparecem no Mailpit.
10. Pró-Reitor consulta a auditoria do edital: todas as ações acima estão registradas.

### 2.9 Riscos específicos do protótipo

| Risco | Mitigação |
|---|---|
| Agente de IA gera telas antes das regras | Ordem rígida: migration → domain → service → testes → tela; prompts citam IDs (RN/INS/AVA…) |
| Erros na classificação/desempate | Função pura + testes de tabela + revisão humana obrigatória |
| Testes lentos com Postgres real | Banco de teste único, transação com rollback por teste |
| Prazos difíceis de demonstrar | Serviço `Relogio` + endpoint de dev para avançar o tempo |
| Ambiguidades do §1.3 virarem retrabalho | Levar a tabela L-01…L-14 à próxima reunião com as Pró-Reitorias |

### 2.10 Próximos passos imediatos

1. Validar com o grupo as decisões L-01…L-14 (principalmente L-01, L-02 e L-04).
2. Criar o repositório com a estrutura da §2.2 e o `AGENTS.md`.
3. Escrever a migration inicial e os testes das máquinas de estado (Fase 0).
