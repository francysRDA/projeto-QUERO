import type { Classificacao, Situacao } from "../api/avaliacoes";
import { fmtDataHora } from "./ui";

export const NOME_SITUACAO: Record<Situacao, string> = {
  CONTEMPLADO: "Contemplado(a)",
  SUPLENTE: "Suplente",
  NAO_CLASSIFICADO: "Não classificado(a)",
};
export const COR_SITUACAO: Record<Situacao, string> = {
  CONTEMPLADO: "bg-green-50 text-green-800 border-green-300",
  SUPLENTE: "bg-blue-50 text-blue-800 border-blue-300",
  NAO_CLASSIFICADO: "bg-slate-100 text-slate-700 border-slate-300",
};
const NOME_FASE = { PREVIA: "Prévia (não publicada)", PRELIMINAR: "Resultado preliminar", POS_RECURSO: "Pós-recurso", FINAL: "Resultado final" };

/** Lista de classificação (RN-09, RN-12). `destacar`: inscrição do próprio estudante. */
export function TabelaClassificacao({ dados, destacar }: { dados: Classificacao; destacar?: number }) {
  return (
    <div>
      <p className="mb-2 text-sm text-slate-600">
        <strong>{NOME_FASE[dados.fase]}</strong> · {dados.vagas} vaga(s) · desempate: maior CR, depois envio mais antigo
      </p>
      {dados.itens.length === 0 ? (
        <p className="text-sm text-slate-500">Nenhuma avaliação confirmada ainda.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Classificação do edital</caption>
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Posição</th>
                <th scope="col" className="px-3 py-2 font-medium">Candidato(a)</th>
                <th scope="col" className="px-3 py-2 font-medium">Nota</th>
                <th scope="col" className="px-3 py-2 font-medium">CR</th>
                <th scope="col" className="px-3 py-2 font-medium">Envio original</th>
                <th scope="col" className="px-3 py-2 font-medium">Situação</th>
              </tr>
            </thead>
            <tbody>
              {dados.itens.map((i) => (
                <tr key={i.inscricao_id} className={`border-t ${i.inscricao_id === destacar ? "bg-amber-50 font-medium" : ""}`}>
                  <td className="px-3 py-2">{i.posicao ? `${i.posicao}º` : "—"}</td>
                  <td className="px-3 py-2">
                    {i.estudante_nome} <span className="text-xs text-slate-500">{i.protocolo}</span>
                  </td>
                  <td className="px-3 py-2">{i.nota !== null ? Number(i.nota).toFixed(2) : "—"}</td>
                  <td className="px-3 py-2">{i.cr_congelado !== null ? Number(i.cr_congelado).toFixed(2) : "—"}</td>
                  <td className="px-3 py-2 text-xs">{fmtDataHora(i.data_submissao_original)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded border px-2 py-0.5 text-xs ${COR_SITUACAO[i.situacao]}`}>{NOME_SITUACAO[i.situacao]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function BarraProgresso({ feitas, total }: { feitas: number; total: number }) {
  const pct = total === 0 ? 100 : Math.round((feitas / total) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-600">
        <span>{feitas} de {total} avaliação(ões) confirmada(s)</span>
        <span>{pct}%</span>
      </div>
      <div className="mt-1 h-2 rounded bg-slate-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
        aria-label="Progresso da avaliação">
        <div className="h-2 rounded bg-marca-700" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
