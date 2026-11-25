import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { avancarRelogio, verRelogio, zerarRelogio } from "../api/editais";
import { definirAcademicoDev, verAcademicoDev } from "../api/inscricoes";
import { Botao, ErroApiBox, fmtDataHora } from "./ui";

/**
 * Painel de demonstração (só existe com ENV=dev):
 * - avança o relógio oficial e dispara as transições temporais (§7.5);
 * - liga/desliga o Sistema Acadêmico simulado (INT-01).
 */
export function RelogioDemo() {
  const qc = useQueryClient();
  const relogio = useQuery({ queryKey: ["relogio"], queryFn: verRelogio, retry: false });
  const academico = useQuery({ queryKey: ["academico-dev"], queryFn: verAcademicoDev, retry: false });
  const aoMudar = () => qc.invalidateQueries();
  const avancar = useMutation({ mutationFn: avancarRelogio, onSuccess: aoMudar });
  const zerar = useMutation({ mutationFn: zerarRelogio, onSuccess: aoMudar });
  const alternar = useMutation({ mutationFn: definirAcademicoDev, onSuccess: aoMudar });

  if (relogio.isError) return null; // ambiente sem rotas de dev

  const dias = (relogio.data?.deslocamento_segundos ?? 0) / 86400;
  const foraDoAr = academico.data?.fora_do_ar ?? false;
  return (
    <aside aria-label="Ferramentas de demonstração" className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
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
      {academico.data && (
        <div className="flex flex-wrap items-center gap-2 border-t border-amber-200 pt-2">
          <span className="font-semibold text-amber-900">Sistema Acadêmico (simulado):</span>
          <span className={foraDoAr ? "font-medium text-red-800" : "text-green-800"} role="status">
            {foraDoAr ? "fora do ar — novas inscrições ficam pendentes" : "no ar"}
          </span>
          <Botao className="ml-auto" variante="secundario" disabled={alternar.isPending} onClick={() => alternar.mutate(!foraDoAr)}>
            {foraDoAr ? "Religar e reprocessar pendentes" : "Simular queda"}
          </Botao>
        </div>
      )}
      <ErroApiBox erro={avancar.error ?? zerar.error ?? alternar.error} />
    </aside>
  );
}
