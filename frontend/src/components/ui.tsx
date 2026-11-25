import type { ReactNode } from "react";
import { ApiError } from "../api/cliente";
import type { Categoria, StatusEdital } from "../api/editais";

const FUSO = "America/Sao_Paulo";

export const fmtDataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { timeZone: FUSO, dateStyle: "short", timeStyle: "short" });

export const fmtMoeda = (v: string | number) =>
  Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const NOME_CATEGORIA: Record<Categoria, string> = {
  ESTAGIO: "Estágio",
  MONITORIA: "Monitoria",
  BOLSA: "Bolsa",
};

export const NOME_STATUS: Record<StatusEdital, string> = {
  RASCUNHO: "Rascunho",
  ABERTO: "Inscrições abertas",
  INSCRICOES_ENCERRADAS: "Inscrições encerradas",
  EM_AVALIACAO: "Em avaliação",
  RESULTADO_PRELIMINAR: "Resultado preliminar",
  EM_RECURSO: "Em recurso",
  EM_HOMOLOGACAO_FINAL: "Em homologação final",
  ENCERRADO: "Encerrado",
  CANCELADO: "Cancelado",
};

const COR_STATUS: Record<StatusEdital, string> = {
  RASCUNHO: "bg-slate-100 text-slate-800 border-slate-300",
  ABERTO: "bg-green-50 text-green-800 border-green-300",
  INSCRICOES_ENCERRADAS: "bg-amber-50 text-amber-900 border-amber-300",
  EM_AVALIACAO: "bg-blue-50 text-blue-800 border-blue-300",
  RESULTADO_PRELIMINAR: "bg-indigo-50 text-indigo-800 border-indigo-300",
  EM_RECURSO: "bg-purple-50 text-purple-800 border-purple-300",
  EM_HOMOLOGACAO_FINAL: "bg-cyan-50 text-cyan-900 border-cyan-300",
  ENCERRADO: "bg-slate-700 text-white border-slate-700",
  CANCELADO: "bg-red-50 text-red-800 border-red-300",
};

export function StatusBadge({ status }: { status: StatusEdital }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded border px-2 py-0.5 text-xs font-medium ${COR_STATUS[status]}`}>
      {NOME_STATUS[status]}
    </span>
  );
}

export function ErroApiBox({ erro }: { erro: unknown }) {
  if (!erro) return null;
  const msg = erro instanceof ApiError ? erro.message : "Erro inesperado. Tente novamente.";
  const detalhes = erro instanceof ApiError ? erro.corpo.detalhes : [];
  return (
    <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
      <p className="font-semibold">{msg}</p>
      {detalhes.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {detalhes.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Botao({
  variante = "primario",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario" | "perigo" }) {
  const estilos = {
    primario: "bg-marca-700 text-white hover:bg-marca-800",
    secundario: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
    perigo: "bg-red-700 text-white hover:bg-red-800",
  };
  return (
    <button
      {...props}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${estilos[variante]} ${className}`}
    />
  );
}

export function Campo({ rotulo, id, children, ajuda }: { rotulo: string; id: string; children: ReactNode; ajuda?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {rotulo}
      </label>
      <div className="mt-1">{children}</div>
      {ajuda && <p className="mt-1 text-xs text-slate-500">{ajuda}</p>}
    </div>
  );
}

export const classeInput = "w-full rounded border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100";

export function Cartao({ titulo, children, acoes }: { titulo?: string; children: ReactNode; acoes?: ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-5 shadow-sm">
      {(titulo || acoes) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {titulo && <h2 className="text-lg font-semibold">{titulo}</h2>}
          {acoes}
        </div>
      )}
      {children}
    </section>
  );
}
