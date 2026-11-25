import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { listarNotificacoes, marcarLida, marcarTodasLidas } from "../api/homologacao";
import { fmtDataHora } from "./ui";

/** TRV-01: painel interno de notificações (sino no cabeçalho). Atualiza a cada minuto. */
export function SinoNotificacoes() {
  const qc = useQueryClient();
  const [aberto, setAberto] = useState(false);
  const painel = useRef<HTMLDivElement>(null);
  const consulta = useQuery({ queryKey: ["notificacoes"], queryFn: listarNotificacoes, refetchInterval: 60_000 });
  const atualizar = () => qc.invalidateQueries({ queryKey: ["notificacoes"] });
  const lida = useMutation({ mutationFn: marcarLida, onSuccess: atualizar });
  const todas = useMutation({ mutationFn: marcarTodasLidas, onSuccess: atualizar });

  useEffect(() => {
    if (!aberto) return;
    const fechar = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !painel.current?.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", fechar);
    document.addEventListener("keydown", fechar);
    return () => {
      document.removeEventListener("mousedown", fechar);
      document.removeEventListener("keydown", fechar);
    };
  }, [aberto]);

  const n = consulta.data?.nao_lidas ?? 0;
  return (
    <div className="relative" ref={painel}>
      <button
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        aria-label={`Notificações${n ? ` (${n} não lida${n > 1 ? "s" : ""})` : ""}`}
        className="relative rounded border border-white/40 px-2 py-1 hover:bg-white/10"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {n > 0 && (
          <span className="absolute -right-2 -top-2 rounded-full bg-amber-400 px-1.5 text-xs font-bold text-slate-900">
            {n > 99 ? "99+" : n}
          </span>
        )}
      </button>
      {aberto && (
        <div className="absolute right-0 z-20 mt-2 w-[min(24rem,90vw)] rounded-lg border bg-white text-slate-900 shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="font-semibold">Notificações</span>
            {n > 0 && (
              <button className="text-xs text-marca-700 underline" onClick={() => todas.mutate()}>
                Marcar todas como lidas
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y overflow-y-auto">
            {consulta.data?.itens.length === 0 && <li className="p-3 text-sm text-slate-500">Nenhuma notificação.</li>}
            {consulta.data?.itens.map((x) => (
              <li key={x.id} className={`p-3 text-sm ${x.lida ? "" : "bg-marca-50"}`}>
                <div className="flex items-start justify-between gap-2">
                  <p className={x.lida ? "" : "font-semibold"}>{x.titulo}</p>
                  {!x.lida && (
                    <button className="shrink-0 text-xs text-marca-700 underline" onClick={() => lida.mutate(x.id)}>
                      Lida
                    </button>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-line text-xs text-slate-600">{x.mensagem}</p>
                <p className="mt-1 text-[11px] text-slate-400">{fmtDataHora(x.criado_em)}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
