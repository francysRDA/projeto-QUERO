# QUERO — Quadro Universitário de Estágios Remunerados e Oportunidades

Sistema unificado de seleção e gestão de estágios, monitorias e bolsas acadêmicas (protótipo).

- Especificação: [`QUERO_Documento_de_Projeto_v5.0.pdf`](QUERO_Documento_de_Projeto_v5.0.pdf)
- Análise e plano: [`PLANO_PROTOTIPO.md`](PLANO_PROTOTIPO.md)
- Guia para desenvolvedores e agentes de IA: [`AGENTS.md`](AGENTS.md)

## Rodar tudo com Docker

```bash
docker compose up --build
```

| Serviço | Endereço |
|---|---|
| Aplicação (SPA) | http://localhost:5173 |
| API + documentação OpenAPI | http://localhost:8000/docs |
| Caixa de e-mails (Mailpit) | http://localhost:8025 |
| PostgreSQL | localhost:5433 (usuário/senha/banco: `quero`) |

Contas de demonstração (senha `quero123`): `prograd@quero.local` (Pró-Reitoria),
`carlos.avaliador@quero.local` (Avaliador), `ana@aluno.quero.local` (Estudante).

Para desenvolvimento sem Docker no backend/frontend, veja os comandos no `AGENTS.md`.

## Roteiro de demonstração (≈ 20 min)

Percorre um edital inteiro, do rascunho à ata, pela interface (PLANO_PROTOTIPO §2.8). Senha de todas as contas:
`quero123`. Use uma janela anônima por perfil, ou saia e entre novamente.

**Preparação**
- Comece de um banco limpo: `docker compose down -v && docker compose up --build`.
- Deixe o Mailpit aberto em http://localhost:8025 para mostrar os e-mails ao longo da demonstração.
- Tenha dois PDFs quaisquer à mão e um arquivo `.exe` (ou qualquer outro binário) renomeado para `falso.pdf`.
- O painel amarelo **Relógio de demonstração** (no detalhe do edital) avança o tempo oficial e simula a queda do
  Sistema Acadêmico. Depois de avançar o relógio, aguarde alguns segundos: o worker é quem dispara as transições.

**Contas**

| Perfil | E-mail | Papel no roteiro |
|---|---|---|
| Pró-Reitoria | `prograd@quero.local` | cria, publica e homologa |
| Avaliador | `carlos.avaliador@quero.local` | avalia Ana e Bruno |
| Avaliador | `beatriz.avaliadora@quero.local` | avalia Elisa, declara impedimento, julga o recurso |
| Estudantes | `ana@`, `bruno@`, `camila@`, `diego@`, `elisa@`, `felipe@aluno.quero.local` | candidatos |

Dados do Sistema Acadêmico simulado (`backend/seed/academico.csv`):

| Estudante | Curso | CR | Resultado esperado na homologação |
|---|---|---|---|
| Ana | Matemática | 8,70 | homologada |
| Bruno | Matemática | 7,40 | homologada |
| Elisa | Física | 8,00 | pendente com o sistema fora do ar → homologada pelo worker |
| Camila | Eng. Civil | 9,10 | indeferida: curso não autorizado |
| Diego | Matemática | 6,50 | indeferida: CR abaixo do mínimo |
| Felipe | Matemática | 7,90 | indeferida: vínculo inativo |

**1. Criar e publicar o edital** — Pró-Reitoria
1. *Gestão de editais → Novo edital*: categoria Monitoria, **2 vagas**, **CR mínimo 7,00**, cursos **MAT** e
   **FIS** (códigos iguais aos do CSV), dois documentos obrigatórios (ex.: Histórico e Carta de motivação).
   Cronograma: inscrições começando agora e terminando em menos de 1 dia; avaliação, resultado preliminar e
   homologação final nos dias seguintes, em ordem; prazo de recurso de 48 h.
2. No detalhe do edital, designe **Carlos** e **Beatriz** na comissão e clique em **Publicar edital**.
3. Mostre no Mailpit os e-mails de designação da comissão.

**2. Inscrições** — Estudantes
1. Ana e Bruno: *Editais abertos* → edital → anexe os PDFs → **Enviar inscrição** → **Baixar comprovante**.
2. Upload inválido: na inscrição da Camila, anexe `falso.pdf` → o arquivo é **recusado** (não começa com `%PDF-`).
   Depois envie com PDFs válidos: a inscrição é indeferida (curso não autorizado). Faça o mesmo com Diego (CR) e
   Felipe (vínculo), mostrando o motivo em *Minhas inscrições*.
3. Pró-Reitoria: no painel amarelo, **Simular queda** do Sistema Acadêmico. Elisa se inscreve e fica
   **Aguardando validação do vínculo**. Clique em **Religar e reprocessar pendentes**: em alguns segundos a
   inscrição da Elisa passa a **Homologada** e ela recebe o e-mail.
4. Ana: *Minhas inscrições* → **Substituir documentos** (retificação, enquanto o edital está aberto).
5. Pró-Reitoria: na seção de inscrições do edital, mostre os motivos de indeferimento e o botão
   **Reanalisar indeferimento…** (reanálise permitida até o início da avaliação — RN-05).

**3. Encerrar inscrições e iniciar a avaliação** — Pró-Reitoria
1. Relógio **+1 dia**: o edital vai para *Inscrições encerradas*.
2. **Iniciar avaliação agora** (ou avance mais 1 dia e deixe o worker iniciar).

**4. Avaliação de mérito** — Avaliadores
1. Beatriz: *Minhas comissões* → edital → na candidatura do Bruno, **Declarar impedimento/suspeição** com motivo.
   Ela deixa de ver o Bruno; a candidatura fica para o Carlos.
2. Beatriz: Elisa → nota **9,00** e parecer → **Confirmar avaliação**.
3. Carlos: Ana → **8,50** e Bruno → **8,50** (empate proposital) → **Confirmar avaliação** em cada uma.
   Mostre **Salvar rascunho** e **Retificar avaliação…** se quiser.
4. **Publicar resultado preliminar**: 1º Elisa, 2º Ana (empate decidido pelo CR 8,70 × 7,40), Bruno 3º suplente.
   A janela de recurso de 48 h abre automaticamente e os candidatos são notificados (sino e e-mail).

**5. Recurso** — Bruno e avaliadores
1. Bruno: *Minhas inscrições* → **Interpor recurso** com texto (e anexo PDF opcional) → **Enviar recurso**.
   Um segundo recurso é recusado (RN-10).
2. Carlos (autor do parecer): abre o recurso → o julgamento é **bloqueado** (RN-11).
3. Beatriz: **Julgar recurso…** → deferir com nova nota **9,50**. A classificação muda para 1º Bruno, 2º Elisa e
   3º Ana (suplente).
4. Pró-Reitoria: relógio **+7 dias**. A janela fecha e o edital vai para *Em homologação final*.

**6. Homologação final e ata** — Pró-Reitoria
1. Só a Pró-Reitoria homologa (RN-13): o avaliador não tem essa tela, e a chamada direta à API
   (`POST /api/v1/editais/{id}/homologar-final`, testável em http://localhost:8000/docs) responde 403.
2. Pró-Reitoria: marque a confirmação → **Homologar resultado final**. O edital fica *Encerrado*.
3. **Baixar ata (PDF)** e **Baixar lista (CSV)**; mostre o SHA-256 exibido na tela. Qualquer usuário autenticado
   (ex.: Ana, em *Minhas inscrições*) também baixa a ata.
4. Tente editar o edital encerrado → recusado: o resultado é imutável. Mostre no Mailpit os e-mails do resultado.
5. Alternativa: em vez de homologar, **Devolver para ajustes…** com justificativa — o edital volta à avaliação e a
   comissão é notificada.

**7. Auditoria** — Pró-Reitoria
1. *Auditoria do edital* (link no topo do detalhe): todas as ações acima, com autor, data/hora e valores antes/depois.
   As ações automáticas do worker aparecem como "Sistema".
2. Filtre por ação (ex.: `RECURSO`), por inscrição e por **Somente destaques**.
3. Como estudante, tente abrir `/auditoria` → acesso negado.

Ao terminar, use **Voltar ao tempo real** no relógio de demonstração. Para repetir do zero: `docker compose down -v`.
