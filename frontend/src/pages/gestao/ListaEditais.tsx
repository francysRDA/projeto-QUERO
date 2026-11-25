import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { listarEditais, type StatusEdital } from "../../api/editais";
import { RelogioDemo } from "../../components/RelogioDemo";
import { ErroApiBox, NOME_CATEGORIA, NOME_STATUS, StatusBadge, fmtDataHora, fmtMoeda } from "../../components/ui";

const TODOS = Object.keys(NOME_STATUS) as StatusEdital[];
const ABAS: { rotulo: string; status: StatusEdital[] }[] = [
  { rotulo: "Todos", status: TODOS },
  { rotulo: "Rascunhos", status: ["RASCUNHO"] },
  { rotulo: "Abertos", status: ["ABERTO"] },
  {
    rotulo: "Em andamento",
    status: ["INSCRICOES_ENCERRADAS", "EM_AVALIACAO", "RESULTADO_PRELIMINAR", "EM_RECURSO", "EM_HOMOLOGACAO_FINAL"],
  },
  { rotulo: "Finalizados", status: ["ENCERRADO", "CANCELADO"] },
];

export function ListaEditais() {
  const [aba, setAba] = useState(0);
  const [busca, setBusca] = useState("");
  const consulta = useQuery({
    queryKey: ["editais", "gestao", aba, busca],
    queryFn: () => listarEditais({ status: ABAS[aba].status, busca: busca || undefined }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Gestão de editais</h1>
        <Link to="/gestao/editais/novo" className="rounded bg-marca-700 px-4 py-2 text-sm font-semibold text-white hover:bg-marca-800">
          Novo edital
        </Link>
      </div>

      <RelogioDemo />

      <div className="flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Filtrar por situação" className="flex flex-wrap gap-1">
          {ABAS.map((a, i) => (
            <button
              key={a.rotulo}
              role="tab"
              aria-selected={aba === i}
              onClick={() => setAba(i)}
              className={`rounded px-3 py-1.5 text-sm ${aba === i ? "bg-marca-700 text-white" : "bg-white border hover:bg-slate-50"}`}
            >
              {a.rotulo}
            </button>
          ))}
        </div>
        <label className="ml-auto text-sm">
          <span className="sr-only">Buscar por título ou descrição</span>
          <input
            type="search"
            placeholder="Buscar…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="rounded border border-slate-300 px-3 py-1.5"
          />
        </label>
      </div>

      <ErroApiBox erro={consulta.error} />

      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2 font-medium">Edital</th>
              <th className="px-4 py-2 font-medium">Categoria</th>
              <th className="px-4 py-2 font-medium">Vagas</th>
              <th className="px-4 py-2 font-medium">Bolsa</th>
              <th className="px-4 py-2 font-medium">Inscrições até</th>
              <th className="px-4 py-2 font-medium">Situação</th>
            </tr>
          </thead>
          <tbody>
            {consulta.isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">Carregando…</td>
              </tr>
            )}
            {consulta.data?.itens.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">Nenhum edital nesta situação.</td>
              </tr>
            )}
            {consulta.data?.itens.map((e) => (
              <tr key={e.id} className="border-t hover:bg-slate-50">
                <td className="px-4 py-2">
                  <Link to={`/gestao/editais/${e.id}`} className="font-medium text-marca-700 underline-offset-2 hover:underline">
                    {e.titulo}
                  </Link>
                  <div className="text-xs text-slate-500">{e.modalidade}</div>
                </td>
                <td className="px-4 py-2">{NOME_CATEGORIA[e.categoria]}</td>
                <td className="px-4 py-2">{e.vagas}</td>
                <td className="px-4 py-2">{fmtMoeda(e.valor_bolsa)}</td>
                <td className="px-4 py-2">{fmtDataHora(e.data_fim_inscricao)}</td>
                <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
