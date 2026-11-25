import { api } from "./cliente";
import type { Edital, StatusEdital } from "./editais";
import type { ArquivoInscricao } from "./inscricoes";

export type Parecer = "DEFERIDO" | "INDEFERIDO";
export type StatusAvaliacao = "RASCUNHO" | "CONFIRMADA" | "RETIFICADA";
export type Situacao = "CONTEMPLADO" | "SUPLENTE" | "NAO_CLASSIFICADO";

export interface Avaliacao {
  id: number;
  inscricao_id: number;
  avaliador_id: number;
  declaracao_sem_impedimento: boolean;
  nota_merito: string | null;
  parecer: Parecer | null;
  justificativa: string | null;
  status: StatusAvaliacao;
  justificativa_retificacao: string | null;
  atualizado_em: string;
}

export interface ItemFila {
  inscricao_id: number;
  protocolo: string;
  estudante_nome: string;
  curso_congelado: string | null;
  cr_congelado: string | null;
  data_submissao_original: string;
  arquivos: ArquivoInscricao[];
  avaliacao: Avaliacao | null;
}

export interface Progresso {
  homologadas: number;
  confirmadas: number;
  em_rascunho: number;
  nao_iniciadas: number;
  sem_avaliador_disponivel: string[];
  pode_publicar: boolean;
}

export interface Fila {
  edital_id: number;
  edital_titulo: string;
  edital_status: StatusEdital;
  pode_avaliar: boolean;
  itens: ItemFila[];
  progresso: Progresso;
}

export interface AvaliacaoEntrada {
  acao: "RASCUNHO" | "CONFIRMAR" | "RETIFICAR";
  nota_merito: string | null;
  parecer: Parecer | null;
  justificativa: string | null;
  declaracao_sem_impedimento: boolean;
  justificativa_retificacao?: string | null;
}

export interface ItemClassificacao {
  posicao: number | null;
  inscricao_id: number;
  protocolo: string;
  estudante_nome: string;
  nota: string | null;
  parecer: Parecer | null;
  cr_congelado: string | null;
  data_submissao_original: string;
  situacao: Situacao;
}

export interface Classificacao {
  edital_id: number;
  fase: "PREVIA" | "PRELIMINAR" | "POS_RECURSO" | "FINAL";
  publicada: boolean;
  vagas: number;
  itens: ItemClassificacao[];
}

export const filaAvaliacao = (editalId: number) => api<Fila>(`/editais/${editalId}/avaliacoes`);
export const progressoAvaliacao = (editalId: number) => api<Progresso>(`/editais/${editalId}/avaliacoes/progresso`);
export const salvarAvaliacao = (inscricaoId: number, d: AvaliacaoEntrada) =>
  api<Avaliacao>(`/inscricoes/${inscricaoId}/avaliacao`, { method: "PUT", body: JSON.stringify(d) });
export const declararImpedimento = (inscricaoId: number, motivo: string) =>
  api<void>(`/inscricoes/${inscricaoId}/impedimento`, { method: "POST", body: JSON.stringify({ motivo }) });
export const publicarPreliminar = (editalId: number) =>
  api<Edital>(`/editais/${editalId}/resultado-preliminar`, { method: "POST" });
export const obterClassificacao = (editalId: number) => api<Classificacao>(`/editais/${editalId}/classificacao`);
