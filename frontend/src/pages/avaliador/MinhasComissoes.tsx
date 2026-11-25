import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { editaisDesignados } from "../../api/editais";
import { Cartao, ErroApiBox, NOME_CATEGORIA, StatusBadge, fmtDataHora } from "../../components/ui";

export function MinhasComissoes() {
  const consulta = useQuery({ queryKey: ["editais", "designados"], queryFn: editaisDesignados });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Minhas comissões</h1>
      <p className="text-sm text-slate-600">
        Você só tem acesso aos editais para os quais foi formalmente designado(a) (RN-07). A fila de avaliação
        ficará disponível quando o edital entrar em avaliação.
      </p>
      <ErroApiBox erro={consulta.error} />
      {consulta.data?.length === 0 && (
        <Cartao><p className="text-sm text-slate-500">Você ainda não foi designado(a) para nenhuma comissão.</p></Cartao>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {consulta.data?.map((e) => (
          <Cartao key={e.id}>
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-semibold">{e.titulo}</h2>
              <StatusBadge status={e.status} />
            </div>
            <p className="mt-1 text-sm text-slate-600">
              {NOME_CATEGORIA[e.categoria]} · {e.vagas} vaga(s) · inscrições até {fmtDataHora(e.data_fim_inscricao)}
            </p>
            {e.status !== "ABERTO" && e.status !== "CANCELADO" && (
              <Link to={`/avaliacoes/${e.id}`} className="mt-3 inline-block rounded bg-marca-700 px-3 py-1.5 text-sm font-medium text-white">
                {e.status === "EM_AVALIACAO" ? "Avaliar candidaturas" : "Ver avaliação e classificação"}
              </Link>
            )}
          </Cartao>
        ))}
      </div>
    </div>
  );
}
