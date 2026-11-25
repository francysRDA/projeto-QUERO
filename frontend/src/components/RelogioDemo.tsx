import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { avancarRelogio, verRelogio, zerarRelogio } from "../api/editais";
import { Botao, ErroApiBox, fmtDataHora } from "./ui";

/** Painel para demonstrações: avança o relógio oficial e dispara as transições temporais (§7.5). */
export function RelogioDemo() {
  const qc = useQueryClient();
  const relogio = useQuery({ queryKey: ["relogio"], queryFn: verRelogio, retry: false });
  const aoMudar = () => qc.invalidateQueries();
  const avancar = useMutation({ mutationFn: avancarRelogio, onSuccess: aoMudar });
  const zerar = useMutation({ mutationFn: zerarRelogio, onSuccess: aoMudar });

  if (relogio.isError) return null; // ambiente sem rotas de dev

  const dias = (relogio.data?.deslocamento_segundos ?? 0) / 86400;
  return (
    <aside aria-label="Relógio de demonstração" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-amber-900">Relógio de demonstração:</span>
        <span>{relogio.data ? fmtDataHora(relogio.data.agora) : "…"}</span>
        {dias > 0 && <span className="text-amber-800">(+{dias.toFixed(1)} dias)</span>}
        <span className="ml-auto flex flex-wrap gap-1">
          {[
            ["+1 hora", 1],
            ["+1 dia", 24],
            ["+7 dias", 24 * 7],
          ].map(([rotulo, horas]) => (
            <Botao key={rotulo} variante="secundario" disabled={avancar.isPending} onClick={() => avancar.mutate(horas as number)}>
              {rotulo}
            </Botao>
          ))}
          <Botao variante="secundario" disabled={zerar.isPending || dias === 0} onClick={() => zerar.mutate()}>
            Voltar ao tempo real
          </Botao>
        </span>
      </div>
      <ErroApiBox erro={avancar.error ?? zerar.error} />
    </aside>
  );
}
