import { api } from "./cliente";
import type { ArquivoInscricao } from "./inscricoes";

export type StatusRecurso = "ABERTO" | "EM_ANALISE" | "DEFERIDO" | "INDEFERIDO";

export interface Recurso {
  id: number;
  inscricao_id: number;
  texto: string;
  anexo: ArquivoInscricao | null;
  status: StatusRecurso;
  justificativa_decisao: string | null;
  criado_em: string;
  julgado_em: string | null;
}

export interface RecursoGestao extends Recurso {
  protocolo: string;
  estudante_nome: string;
  nota_atual: string | null;
  parecer_atual: "DEFERIDO" | "INDEFERIDO" | null;
  autor_parecer_id: number | null;
  autor_parecer_nome: string | null;
  julgado_por_nome: string | null;
  pode_julgar: boolean;
  motivo_bloqueio: string | null;
  comissao_unica: boolean;
}

export interface PainelRecursos {
  edital_id: number;
  data_fim_recurso: string | null;
  janela_aberta: boolean;
  recursos: RecursoGestao[];
}

export interface Julgamento {
  decisao: "DEFERIDO" | "INDEFERIDO";
  justificativa: string;
  nova_nota?: string | null;
  novo_parecer?: "DEFERIDO" | "INDEFERIDO" | null;
}

export const TAMANHO_MAX_RECURSO = 5000;
export const MIN_JUSTIFICATIVA_REFORCADA = 100;

export function interporRecurso(inscricaoId: number, texto: string, anexo: File | null) {
  const form = new FormData();
  form.append("texto", texto);
  if (anexo) form.append("anexo", anexo);
  return api<Recurso>(`/inscricoes/${inscricaoId}/recursos`, { method: "POST", body: form });
}

export const julgarRecurso = (recursoId: number, j: Julgamento) =>
  api<Recurso>(`/recursos/${recursoId}/julgar`, { method: "POST", body: JSON.stringify(j) });

export const painelRecursos = (editalId: number) => api<PainelRecursos>(`/editais/${editalId}/recursos`);

export const NOME_STATUS_RECURSO: Record<StatusRecurso, string> = {
  ABERTO: "Aguardando julgamento",
  EM_ANALISE: "Em análise",
  DEFERIDO: "Deferido",
  INDEFERIDO: "Indeferido",
};
