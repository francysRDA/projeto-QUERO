import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { inscricoesDoEdital, reanalisar, type InscricaoGestao, type StatusInscricao } from "../../api/inscricoes";
import { Botao, Cartao, ErroApiBox, classeInput, fmtDataHora } from "../../components/ui";

const ROTULO: Record<StatusInscricao, string> = {
  HOMOLOGADA: "Homologada",
  INDEFERIDA: "Indeferida",
  PENDENTE_VALIDACAO_VINCULO: "Pendente (vínculo)",
  DESISTENTE: "Desistente",
};
const COR: Record<StatusInscricao, string> = {
  HOMOLOGADA: "text-green-800",
  INDEFERIDA: "text-red-800",
  PENDENTE_VALIDACAO_VINCULO: "text-amber-800",
  DESISTENTE: "text-slate-500",
};

/** UC-04: conferência da homologação formal e reanálise de indeferimentos (RN-05). */
export function InscricoesEdital({ editalId }: { editalId: number }) {
  const consulta = useQuery({ queryKey: ["inscricoes", "edital", editalId], queryFn: () => inscricoesDoEdital(editalId) });
  const lista = consulta.data ?? [];
  const contagem = (s: StatusInscricao) => lista.filter((i) => i.status === s).length;

  return (
    <Cartao titulo={`Inscrições (${lista.length})`}>
      {lista.length > 0 && (
        <p className="mb-3 text-sm text-slate-600">
          {contagem("HOMOLOGADA")} homologada(s) · {contagem("INDEFERIDA")} indeferida(s) ·{" "}
          {contagem("PENDENTE_VALIDACAO_VINCULO")} pendente(s) · {contagem("DESISTENTE")} desistente(s)
        </p>
      )}
      <ErroApiBox erro={consulta.error} />
      {consulta.data?.length === 0 && <p className="text-sm text-slate-500">Nenhuma inscrição recebida.</p>}
      <ul className="divide-y">
        {lista.map((i) => <Linha key={i.id} inscricao={i} editalId={editalId} />)}
      </ul>
    </Cartao>
  );
}

function Linha({ inscricao: i, editalId }: { inscricao: InscricaoGestao; editalId: number }) {
  const qc = useQueryClient();
  const [aberto, setAberto] = useState(false);
  const [justificativa, setJustificativa] = useState("");
  const mut = useMutation({
    mutationFn: () => reanalisar(i.id, justificativa),
    onSuccess: () => {
      setAberto(false);
      qc.invalidateQueries({ queryKey: ["inscricoes", "edital", editalId] });
    },
  });

  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">{i.estudante_nome} <span className="font-normal text-slate-500">· matrícula {i.estudante_matricula ?? "—"}</span></p>
          <p className="text-xs text-slate-500">
            {i.protocolo} · {fmtDataHora(i.data_submissao_original)}
            {i.curso_congelado && <> · {i.curso_congelado} · CR {Number(i.cr_congelado).toFixed(2)}</>}
            {i.vinculo_ativo_congelado === false && <> · vínculo inativo</>}
          </p>
        </div>
        <span className={`font-semibold ${COR[i.status]}`}>
          {ROTULO[i.status]}{i.reanalisada && " (após reanálise)"}
        </span>
      </div>
      {i.motivos_indeferimento && (
        <ul className="mt-1 list-disc pl-5 text-xs text-red-800">{i.motivos_indeferimento.map((m) => <li key={m}>{m}</li>)}</ul>
      )}
      {i.justificativa_reanalise && <p className="mt-1 text-xs text-slate-600">Reanálise: {i.justificativa_reanalise}</p>}

      {i.pode_reanalisar && !aberto && (
        <Botao className="mt-2" variante="secundario" onClick={() => setAberto(true)}>Reanalisar indeferimento…</Botao>
      )}
      {aberto && (
        <div className="mt-2 space-y-2 rounded border bg-slate-50 p-3">
          <label htmlFor={`just-${i.id}`} className="block text-xs font-medium">
            Justificativa da reanálise (obrigatória, mínimo 10 caracteres — fica registrada na auditoria)
          </label>
          <textarea id={`just-${i.id}`} rows={2} className={classeInput} value={justificativa}
            onChange={(e) => setJustificativa(e.target.value)} />
          <ErroApiBox erro={mut.error} />
          <div className="flex gap-2">
            <Botao disabled={mut.isPending || justificativa.trim().length < 10} onClick={() => mut.mutate()}>
              Deferir e homologar
            </Botao>
            <Botao variante="secundario" onClick={() => setAberto(false)}>Cancelar</Botao>
          </div>
        </div>
      )}
    </li>
  );
}
