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
