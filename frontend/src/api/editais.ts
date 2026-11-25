import { api } from "./cliente";

export type Categoria = "ESTAGIO" | "MONITORIA" | "BOLSA";
export type StatusEdital =
  | "RASCUNHO"
  | "ABERTO"
  | "INSCRICOES_ENCERRADAS"
  | "EM_AVALIACAO"
  | "RESULTADO_PRELIMINAR"
  | "EM_RECURSO"
  | "EM_HOMOLOGACAO_FINAL"
  | "ENCERRADO"
  | "CANCELADO";

export interface Curso {
  id?: number;
  codigo_curso: string;
  nome_curso: string;
}

export interface Documento {
  id?: number;
  nome: string;
  descricao?: string | null;
  obrigatorio: boolean;
}

export interface EditalResumo {
  id: number;
  titulo: string;
  categoria: Categoria;
  modalidade: string;
  valor_bolsa: string;
  carga_horaria_semanal: number;
  vagas: number;
  cr_minimo: string;
  status: StatusEdital;
  data_inicio_inscricao: string;
  data_fim_inscricao: string;
}

export interface Edital extends EditalResumo {
  descricao: string;
  prazo_recurso_horas: number;
  criterios_pontuacao: Record<string, unknown>;
  criterios_desempate: string[];
  data_inicio_avaliacao: string;
  data_resultado_preliminar: string;
  data_homologacao_final: string;
  data_fim_recurso: string | null;
  justificativa_cancelamento: string | null;
  criado_em: string;
  cursos: Curso[];
  documentos: Documento[];
}

export type EditalEntrada = Omit<
  Edital,
  "id" | "status" | "data_fim_recurso" | "justificativa_cancelamento" | "criado_em"
>;

export interface MembroComissao {
  avaliador_id: number;
  nome: string;
  email: string;
  designado_em: string;
}

export interface UsuarioResumo {
  id: number;
  nome: string;
  email: string;
}

export interface FiltrosEditais {
  status?: StatusEdital[];
  categoria?: Categoria;
  curso?: string;
  busca?: string;
  valor_min?: string;
  valor_max?: string;
}

export function listarEditais(f: FiltrosEditais = {}) {
  const q = new URLSearchParams();
  f.status?.forEach((s) => q.append("status", s));
  for (const k of ["categoria", "curso", "busca", "valor_min", "valor_max"] as const) {
    if (f[k]) q.set(k, f[k]!);
  }
  q.set("limite", "100");
  return api<{ itens: EditalResumo[]; total: number }>(`/editais?${q}`);
}

export const obterEdital = (id: number) => api<Edital>(`/editais/${id}`);
export const criarEdital = (d: EditalEntrada) => api<Edital>("/editais", { method: "POST", body: JSON.stringify(d) });
export const atualizarEdital = (id: number, d: Partial<EditalEntrada>) =>
  api<Edital>(`/editais/${id}`, { method: "PUT", body: JSON.stringify(d) });
export const publicarEdital = (id: number) => api<Edital>(`/editais/${id}/publicar`, { method: "POST" });
export const iniciarAvaliacao = (id: number) => api<Edital>(`/editais/${id}/iniciar-avaliacao`, { method: "POST" });
export const cancelarEdital = (id: number, justificativa: string) =>
  api<Edital>(`/editais/${id}/cancelar`, { method: "POST", body: JSON.stringify({ justificativa }) });

export const listarComissao = (id: number) => api<MembroComissao[]>(`/editais/${id}/comissao`);
export const designarComissao = (id: number, avaliador_ids: number[]) =>
  api<MembroComissao[]>(`/editais/${id}/comissao`, { method: "POST", body: JSON.stringify({ avaliador_ids }) });
export const removerDaComissao = (id: number, avaliadorId: number) =>
  api<void>(`/editais/${id}/comissao/${avaliadorId}`, { method: "DELETE" });
export const listarAvaliadores = () => api<UsuarioResumo[]>("/usuarios/avaliadores");
export const editaisDesignados = () => api<EditalResumo[]>("/editais/designados");

// Relógio de demonstração (somente dev)
export interface Relogio {
  agora: string;
  deslocamento_segundos: number;
}
export const verRelogio = () => api<Relogio>("/dev/relogio");
export const avancarRelogio = (horas: number) =>
  api<Relogio>("/dev/relogio/avancar", { method: "POST", body: JSON.stringify({ horas }) });
export const zerarRelogio = () => api<Relogio>("/dev/relogio/zerar", { method: "POST" });
