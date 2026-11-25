import { api, baixarArquivo } from "./cliente";
import type { StatusEdital } from "./editais";

export type StatusInscricao = "PENDENTE_VALIDACAO_VINCULO" | "HOMOLOGADA" | "INDEFERIDA" | "DESISTENTE";

export interface ArquivoInscricao {
  id: number;
  documento_exigido_id: number | null;
  nome_original: string;
  sha256: string;
  tamanho_bytes: number;
  versao: number;
  ativo: boolean;
  enviado_em: string;
}

export interface Inscricao {
  id: number;
  protocolo: string;
  status: StatusInscricao;
  motivos_indeferimento: string[] | null;
  vinculo_ativo_congelado: boolean | null;
  curso_congelado: string | null;
  cr_congelado: string | null;
  data_submissao_original: string;
  data_ultima_retificacao: string | null;
  edital: { id: number; titulo: string; status: StatusEdital; data_fim_inscricao: string };
  arquivos: ArquivoInscricao[];
  pode_retificar: boolean;
  pode_desistir: boolean;
  resultado: ResultadoCandidato | null;
}

export interface ResultadoCandidato {
  fase: "PRELIMINAR" | "POS_RECURSO" | "FINAL";
  nota: string | null;
  parecer: "DEFERIDO" | "INDEFERIDO" | null;
  justificativa: string | null;
  posicao: number | null;
  situacao: "CONTEMPLADO" | "SUPLENTE" | "NAO_CLASSIFICADO";
  total_vagas: number;
}

/** arquivos: documento_exigido_id -> File */
function montarForm(arquivos: Record<number, File>): FormData {
  const form = new FormData();
  for (const [docId, arquivo] of Object.entries(arquivos)) form.append(`doc_${docId}`, arquivo);
  return form;
}

export const inscrever = (editalId: number, arquivos: Record<number, File>) =>
  api<Inscricao>(`/editais/${editalId}/inscricoes`, { method: "POST", body: montarForm(arquivos) });

export const retificar = (inscricaoId: number, arquivos: Record<number, File>) =>
  api<Inscricao>(`/inscricoes/${inscricaoId}/retificar`, { method: "PUT", body: montarForm(arquivos) });

export const desistir = (inscricaoId: number) => api<Inscricao>(`/inscricoes/${inscricaoId}/desistir`, { method: "POST" });

export const minhasInscricoes = () => api<Inscricao[]>("/inscricoes/me");

export const baixarComprovante = (i: Inscricao) =>
  baixarArquivo(`/inscricoes/${i.id}/comprovante`, `comprovante-${i.protocolo}.pdf`);

export const baixarDocumento = (a: ArquivoInscricao) => baixarArquivo(`/arquivos/${a.id}/download`, a.nome_original);

export const LIMITE_BYTES = 10 * 1024 * 1024;

/** Pré-checagem só para UX; a validação que vale é a do backend (RN-04). */
export function problemaNoArquivo(f: File): string | null {
  if (!f.name.toLowerCase().endsWith(".pdf")) return "Envie um arquivo .pdf.";
  if (f.size === 0) return "O arquivo está vazio.";
  if (f.size > LIMITE_BYTES) return "O arquivo excede 10 MB.";
  return null;
}

// --- Fatia 4: Sistema Acadêmico, conferência e reanálise ---------------------------------------
export interface DadosAcademicos {
  matricula: string;
  vinculo_ativo: boolean;
  codigo_curso: string;
  nome_curso: string;
  cr: string;
}

export interface InscricaoGestao {
  id: number;
  protocolo: string;
  status: StatusInscricao;
  estudante_nome: string;
  estudante_matricula: string | null;
  curso_congelado: string | null;
  cr_congelado: string | null;
  vinculo_ativo_congelado: boolean | null;
  motivos_indeferimento: string[] | null;
  data_submissao_original: string;
  reanalisada: boolean;
  justificativa_reanalise: string | null;
  pode_reanalisar: boolean;
}

export const meusDadosAcademicos = () => api<DadosAcademicos>("/academico/me");
export const inscricoesDoEdital = (editalId: number) => api<InscricaoGestao[]>(`/editais/${editalId}/inscricoes`);
export const reanalisar = (inscricaoId: number, justificativa: string) =>
  api<Inscricao>(`/inscricoes/${inscricaoId}/reanalisar`, { method: "POST", body: JSON.stringify({ justificativa }) });

export const verAcademicoDev = () => api<{ fora_do_ar: boolean }>("/dev/academico");
export const definirAcademicoDev = (fora_do_ar: boolean) =>
  api<{ fora_do_ar: boolean }>("/dev/academico", { method: "PUT", body: JSON.stringify({ fora_do_ar }) });
