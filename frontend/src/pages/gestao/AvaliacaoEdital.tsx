import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { obterClassificacao, progressoAvaliacao, publicarPreliminar } from "../../api/avaliacoes";
import type { Edital } from "../../api/editais";
import { PainelRecursosEdital } from "../../components/PainelRecursos";
import { BarraProgresso, TabelaClassificacao } from "../../components/TabelaClassificacao";
import { Botao, Cartao, ErroApiBox, fmtDataHora } from "../../components/ui";

const FASES_COM_AVALIACAO = ["EM_AVALIACAO", "RESULTADO_PRELIMINAR", "EM_RECURSO", "EM_HOMOLOGACAO_FINAL", "ENCERRADO"];

/** Acompanhamento da avaliação de mérito e da classificação pela Pró-Reitoria (AVA-02). */
export function AvaliacaoEdital({ edital }: { edital: Edital }) {
  const qc = useQueryClient();
  const ativo = FASES_COM_AVALIACAO.includes(edital.status);
  const prog = useQuery({ queryKey: ["progresso", edital.id], queryFn: () => progressoAvaliacao(edital.id), enabled: ativo });
  const classif = useQuery({ queryKey: ["classificacao", edital.id], queryFn: () => obterClassificacao(edital.id), enabled: ativo });
  const publicar = useMutation({ mutationFn: () => publicarPreliminar(edital.id), onSuccess: () => qc.invalidateQueries() });

  if (!ativo) return null;
  const p = prog.data;
  return (
    <Cartao titulo="Avaliação de mérito e classificação">
      {p && <BarraProgresso feitas={p.confirmadas} total={p.homologadas} />}
      {p && p.sem_avaliador_disponivel.length > 0 && (
        <p role="alert" className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">
          Inscrições sem avaliador disponível (todos os membros declararam impedimento): {p.sem_avaliador_disponivel.join(", ")}.
          Designe outro avaliador na comissão abaixo.
        </p>
      )}
      {edital.status === "EM_AVALIACAO" && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Botao disabled={!p?.pode_publicar || publicar.isPending} onClick={() => publicar.mutate()}>
            Publicar resultado preliminar
          </Botao>
          <span className="text-xs text-slate-600">
            A publicação abre automaticamente a janela de recurso de {edital.prazo_recurso_horas} h (RN-10).
          </span>
        </div>
      )}
      {edital.data_fim_recurso && edital.status === "EM_RECURSO" && (
        <p className="mt-3 text-sm">Janela de recurso aberta até <strong>{fmtDataHora(edital.data_fim_recurso)}</strong>.</p>
      )}
      <div className="mt-2"><ErroApiBox erro={publicar.error ?? prog.error} /></div>
      {classif.data && <div className="mt-4"><TabelaClassificacao dados={classif.data} /></div>}
      {["EM_RECURSO", "EM_HOMOLOGACAO_FINAL", "ENCERRADO"].includes(edital.status) && (
        <div className="mt-4"><PainelRecursosEdital editalId={edital.id} /></div>
      )}
    </Cartao>
  );
}
