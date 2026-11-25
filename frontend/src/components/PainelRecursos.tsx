import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { baixarDocumento } from "../api/inscricoes";
import {
  MIN_JUSTIFICATIVA_REFORCADA,
  NOME_STATUS_RECURSO,
  julgarRecurso,
  painelRecursos,
  type RecursoGestao,
} from "../api/recursos";
import { Botao, Cartao, ErroApiBox, classeInput, fmtDataHora } from "./ui";

/** Recursos do edital (AVA-04). O avaliador julga; a Pró-Reitoria acompanha. */
export function PainelRecursosEdital({ editalId }: { editalId: number }) {
  const painel = useQuery({ queryKey: ["recursos", editalId], queryFn: () => painelRecursos(editalId) });
  if (!painel.data) return <ErroApiBox erro={painel.error} />;
  const p = painel.data;
  const pendentes = p.recursos.filter((r) => r.status === "ABERTO" || r.status === "EM_ANALISE").length;

  return (
    <Cartao titulo={`Recursos (${p.recursos.length})`}>
      <p className="text-sm text-slate-600">
        {p.data_fim_recurso && (
          <>Janela {p.janela_aberta ? "aberta até" : "encerrada em"} <strong>{fmtDataHora(p.data_fim_recurso)}</strong> · </>
        )}
        {pendentes} pendente(s) de julgamento
        {!p.janela_aberta && pendentes > 0 && " — o edital avança para a homologação final quando todos forem julgados."}
      </p>
      {p.recursos.length === 0 && <p className="mt-2 text-sm text-slate-500">Nenhum recurso interposto.</p>}
      <ul className="mt-3 space-y-3">
        {p.recursos.map((r) => <ItemRecurso key={r.id} r={r} />)}
      </ul>
    </Cartao>
  );
}

function ItemRecurso({ r }: { r: RecursoGestao }) {
  const qc = useQueryClient();
  const [abrir, setAbrir] = useState(false);
  const [decisao, setDecisao] = useState<"DEFERIDO" | "INDEFERIDO">("INDEFERIDO");
  const [justificativa, setJustificativa] = useState("");
  const [novaNota, setNovaNota] = useState(r.nota_atual ?? "");
  const [novoParecer, setNovoParecer] = useState<"DEFERIDO" | "INDEFERIDO">("DEFERIDO");
  const minimo = r.comissao_unica ? MIN_JUSTIFICATIVA_REFORCADA : 10;

  const mut = useMutation({
    mutationFn: () =>
      julgarRecurso(r.id, {
        decisao, justificativa,
        nova_nota: decisao === "DEFERIDO" ? Number(novaNota).toFixed(2) : null,
        novo_parecer: decisao === "DEFERIDO" ? novoParecer : null,
      }),
    onSuccess: () => {
      setAbrir(false);
      qc.invalidateQueries();
    },
  });
  const julgado = r.status === "DEFERIDO" || r.status === "INDEFERIDO";

  return (
    <li className="rounded border p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p>
          <strong>{r.estudante_nome}</strong> <span className="text-slate-500">· {r.protocolo} · {fmtDataHora(r.criado_em)}</span>
        </p>
        <span className={`rounded border px-2 py-0.5 text-xs font-medium ${julgado ? (r.status === "DEFERIDO" ? "border-green-300 bg-green-50 text-green-800" : "border-red-300 bg-red-50 text-red-800") : "border-amber-300 bg-amber-50 text-amber-900"}`}>
          {NOME_STATUS_RECURSO[r.status]}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-600">
        Nota atual: {r.nota_atual !== null ? Number(r.nota_atual).toFixed(2) : "—"} ({r.parecer_atual?.toLowerCase() ?? "—"}) ·
        parecer de {r.autor_parecer_nome ?? "—"}
      </p>
      <blockquote className="mt-2 whitespace-pre-line border-l-4 border-slate-300 pl-3 text-slate-800">{r.texto}</blockquote>
      {r.anexo && (
        <button className="mt-1 text-marca-700 underline" onClick={() => void baixarDocumento(r.anexo!)}>
          Anexo: {r.anexo.nome_original}
        </button>
      )}
      {julgado && (
        <p className="mt-2 text-slate-700">
          <strong>Decisão</strong> ({r.julgado_por_nome}, {r.julgado_em && fmtDataHora(r.julgado_em)}): {r.justificativa_decisao}
        </p>
      )}
      {!julgado && r.motivo_bloqueio && <p className="mt-2 text-xs text-amber-900">{r.motivo_bloqueio}</p>}

      {r.pode_julgar && !abrir && <Botao className="mt-2" onClick={() => setAbrir(true)}>Julgar recurso…</Botao>}
      {abrir && (
        <form className="mt-3 space-y-3 rounded bg-slate-50 p-3" onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
          <fieldset>
            <legend className="font-medium">Decisão</legend>
            <div className="mt-1 flex gap-4">
              {(["DEFERIDO", "INDEFERIDO"] as const).map((d) => (
                <label key={d} className="flex items-center gap-1">
                  <input type="radio" name={`decisao-${r.id}`} checked={decisao === d} onChange={() => setDecisao(d)} />
                  {d === "DEFERIDO" ? "Deferir (reavaliar a nota)" : "Indeferir"}
                </label>
              ))}
            </div>
          </fieldset>
          {decisao === "DEFERIDO" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="font-medium">Nova nota de mérito</span>
                <input type="number" min="0" max="10" step="0.01" required className={`${classeInput} mt-1`}
                  value={novaNota} onChange={(e) => setNovaNota(e.target.value)} />
              </label>
              <label className="block">
                <span className="font-medium">Novo parecer</span>
                <select className={`${classeInput} mt-1`} value={novoParecer}
                  onChange={(e) => setNovoParecer(e.target.value as "DEFERIDO" | "INDEFERIDO")}>
                  <option value="DEFERIDO">Deferido</option>
                  <option value="INDEFERIDO">Indeferido</option>
                </select>
              </label>
            </div>
          )}
          <label className="block">
            <span className="font-medium">
              Fundamentação da decisão {r.comissao_unica && <span className="text-amber-900">(justificativa reforçada — comissão de um membro, RN-11)</span>}
            </span>
            <textarea rows={3} className={`${classeInput} mt-1`} value={justificativa} onChange={(e) => setJustificativa(e.target.value)} />
            <span className="text-xs text-slate-500">{justificativa.trim().length}/{minimo} caracteres mínimos</span>
          </label>
          <p className="text-xs text-slate-600">A classificação é recalculada automaticamente após a decisão (AVA-04).</p>
          <ErroApiBox erro={mut.error} />
          <div className="flex gap-2">
            <Botao type="submit" disabled={mut.isPending || justificativa.trim().length < minimo || (decisao === "DEFERIDO" && novaNota === "")}>
              Registrar decisão
            </Botao>
            <Botao type="button" variante="secundario" onClick={() => setAbrir(false)}>Cancelar</Botao>
          </div>
        </form>
      )}
    </li>
  );
}
