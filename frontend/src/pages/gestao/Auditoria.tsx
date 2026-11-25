import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listarEditais, type StatusEdital } from "../../api/editais";
import { consultarAuditoria, type RegistroAuditoria } from "../../api/homologacao";
import { Botao, Cartao, ErroApiBox, NOME_STATUS, classeInput, fmtDataHora } from "../../components/ui";

const POR_PAGINA = 50;
const TODOS = Object.keys(NOME_STATUS) as StatusEdital[];

/** TRV-03: consulta da trilha de auditoria. Somente leitura — não há edição nem exclusão (RN-14). */
export function Auditoria() {
  const [params, setParams] = useSearchParams();
  const editalId = params.get("edital") ? Number(params.get("edital")) : undefined;
  const [inscricao, setInscricao] = useState(params.get("inscricao") ?? "");
  const [acao, setAcao] = useState("");
  const [destaques, setDestaques] = useState(false);
  const [pagina, setPagina] = useState(0);

  const editais = useQuery({ queryKey: ["editais", "todos"], queryFn: () => listarEditais({ status: TODOS }) });
  const filtros = {
    edital_id: editalId,
    inscricao_id: inscricao ? Number(inscricao) : undefined,
    acao: acao || undefined,
    somente_destaques: destaques,
    limite: POR_PAGINA,
    deslocamento: pagina * POR_PAGINA,
  };
  const consulta = useQuery({ queryKey: ["auditoria", filtros], queryFn: () => consultarAuditoria(filtros) });
  const total = consulta.data?.total ?? 0;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Trilha de auditoria</h1>
      <p className="text-sm text-slate-600">
        Registros imutáveis de todas as ações críticas (RN-14): autor, data/hora, ação, entidade e valores antes/depois.
      </p>

      <form role="search" onSubmit={(e) => e.preventDefault()} className="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">
          <span className="font-medium">Edital</span>
          <select className={`${classeInput} mt-1`} value={editalId ?? ""}
            onChange={(e) => { setPagina(0); setParams(e.target.value ? { edital: e.target.value } : {}); }}>
            <option value="">Todos</option>
            {editais.data?.itens.map((e) => <option key={e.id} value={e.id}>#{e.id} — {e.titulo}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="font-medium">Inscrição (id)</span>
          <input inputMode="numeric" className={`${classeInput} mt-1`} value={inscricao}
            onChange={(e) => { setPagina(0); setInscricao(e.target.value.replace(/\D/g, "")); }} />
        </label>
        <label className="text-sm">
          <span className="font-medium">Ação contém</span>
          <input className={`${classeInput} mt-1`} placeholder="ex.: RECURSO" value={acao}
            onChange={(e) => { setPagina(0); setAcao(e.target.value); }} />
        </label>
        <label className="flex items-end gap-2 text-sm">
          <input type="checkbox" checked={destaques} onChange={(e) => { setPagina(0); setDestaques(e.target.checked); }} />
          Somente destaques (ex.: comissão única — RN-11)
        </label>
      </form>

      <ErroApiBox erro={consulta.error} />
      <Cartao>
        <p className="mb-2 text-sm text-slate-600" aria-live="polite">{total} registro(s)</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Data/hora</th>
                <th scope="col" className="px-3 py-2 font-medium">Autor</th>
                <th scope="col" className="px-3 py-2 font-medium">Ação</th>
                <th scope="col" className="px-3 py-2 font-medium">Entidade</th>
                <th scope="col" className="px-3 py-2 font-medium">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {consulta.data?.itens.map((r) => <Linha key={r.id} r={r} />)}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Botao variante="secundario" disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>Anterior</Botao>
          <span className="text-xs text-slate-600">Página {pagina + 1} de {Math.max(1, Math.ceil(total / POR_PAGINA))}</span>
          <Botao variante="secundario" disabled={(pagina + 1) * POR_PAGINA >= total} onClick={() => setPagina((p) => p + 1)}>Próxima</Botao>
        </div>
      </Cartao>
    </div>
  );
}

function Linha({ r }: { r: RegistroAuditoria }) {
  return (
    <tr className={`border-t align-top ${r.destaque ? "bg-amber-50" : ""}`}>
      <td className="whitespace-nowrap px-3 py-2 text-xs">{fmtDataHora(r.criado_em)}</td>
      <td className="px-3 py-2">{r.usuario_nome ?? `#${r.usuario_id}`}{r.ip_origem && <span className="block text-xs text-slate-500">{r.ip_origem}</span>}</td>
      <td className="px-3 py-2 font-mono text-xs">{r.acao}{r.destaque && <span className="ml-1 rounded bg-amber-200 px-1">destaque</span>}</td>
      <td className="px-3 py-2 text-xs">{r.entidade} #{r.entidade_id}</td>
      <td className="px-3 py-2">
        {(r.dados_antes || r.dados_depois) && (
          <details>
            <summary className="cursor-pointer text-xs text-marca-700">Antes / depois</summary>
            <div className="mt-1 grid gap-2 lg:grid-cols-2">
              <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-[11px]">{JSON.stringify(r.dados_antes, null, 2)}</pre>
              <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-[11px]">{JSON.stringify(r.dados_depois, null, 2)}</pre>
            </div>
          </details>
        )}
      </td>
    </tr>
  );
}
