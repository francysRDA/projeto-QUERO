import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Edital } from "../../api/editais";
import { atasDoEdital, baixarAtaPdf, baixarListaCsv, devolverAjustes, homologarFinal } from "../../api/homologacao";
import { Botao, Cartao, ErroApiBox, classeInput, fmtDataHora } from "../../components/ui";

/** UC-09: homologar o resultado final ou devolver para ajustes (HOM-01, HOM-02, RN-13). */
export function HomologacaoFinal({ edital }: { edital: Edital }) {
  const qc = useQueryClient();
  const [confirmo, setConfirmo] = useState(false);
  const [devolvendo, setDevolvendo] = useState(false);
  const [justificativa, setJustificativa] = useState("");
  const atas = useQuery({ queryKey: ["atas", edital.id], queryFn: () => atasDoEdital(edital.id), enabled: edital.status === "ENCERRADO" });
  const homologar = useMutation({ mutationFn: () => homologarFinal(edital.id), onSuccess: () => qc.invalidateQueries() });
  const devolver = useMutation({ mutationFn: () => devolverAjustes(edital.id, justificativa), onSuccess: () => qc.invalidateQueries() });
  const baixar = useMutation({ mutationFn: (f: () => Promise<void>) => f() });

  if (edital.status === "ENCERRADO") {
    return (
      <Cartao titulo="Resultado final homologado">
        {atas.data?.map((a) => (
          <div key={a.id} className="space-y-2 text-sm">
            <p>
              Homologado por <strong>{a.homologado_por}</strong> em {fmtDataHora(a.homologado_em)}. O resultado é imutável (RN-13).
            </p>
            <div className="flex flex-wrap gap-2">
              <Botao onClick={() => baixar.mutate(() => baixarAtaPdf(a))}>Baixar ata (PDF)</Botao>
              <Botao variante="secundario" onClick={() => baixar.mutate(() => baixarListaCsv(a))}>Baixar lista (CSV)</Botao>
            </div>
            <p className="break-all text-xs text-slate-500">SHA-256 da ata: {a.pdf_sha256}</p>
          </div>
        ))}
        <ErroApiBox erro={baixar.error ?? atas.error} />
      </Cartao>
    );
  }
  if (edital.status !== "EM_HOMOLOGACAO_FINAL") return null;

  return (
    <Cartao titulo="Homologação final (HOM-01)">
      <p className="text-sm text-slate-700">
        Revise a classificação pós-recurso, os recursos e as inscrições abaixo. Ao homologar, o sistema gera a ata em PDF e a
        lista em CSV, notifica todos os candidatos e torna o resultado <strong>imutável</strong>.
      </p>
      <p className="mt-1 text-xs text-slate-500">
        <Link to={`/auditoria?edital=${edital.id}`} className="underline">Consultar a trilha de auditoria do edital</Link>
      </p>

      {!devolvendo && (
        <div className="mt-4 space-y-3">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={confirmo} onChange={(e) => setConfirmo(e.target.checked)} />
            Revisei a instrução do processo e confirmo a lista de contemplados e suplentes.
          </label>
          <div className="flex flex-wrap gap-2">
            <Botao disabled={!confirmo || homologar.isPending} onClick={() => homologar.mutate()}>
              {homologar.isPending ? "Gerando ata…" : "Homologar resultado final"}
            </Botao>
            <Botao variante="secundario" onClick={() => setDevolvendo(true)}>Devolver para ajustes…</Botao>
          </div>
          <ErroApiBox erro={homologar.error} />
        </div>
      )}

      {devolvendo && (
        <div className="mt-4 space-y-2 rounded border border-amber-300 bg-amber-50 p-3">
          <label htmlFor="just-devolucao" className="block text-sm font-medium text-amber-900">
            Justificativa da devolução (obrigatória). O edital volta para avaliação e a comissão é notificada.
          </label>
          <textarea id="just-devolucao" rows={3} className={classeInput} value={justificativa}
            onChange={(e) => setJustificativa(e.target.value)} />
          <ErroApiBox erro={devolver.error} />
          <div className="flex gap-2">
            <Botao variante="perigo" disabled={devolver.isPending || justificativa.trim().length < 10} onClick={() => devolver.mutate()}>
              Devolver para a avaliação
            </Botao>
            <Botao variante="secundario" onClick={() => setDevolvendo(false)}>Cancelar</Botao>
          </div>
        </div>
      )}
    </Cartao>
  );
}
