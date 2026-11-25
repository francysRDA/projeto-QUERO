import { api, baixarArquivo } from "./cliente";
import type { Edital } from "./editais";

export interface Ata {
  id: number;
  edital_id: number;
  homologado_por: string;
  homologado_em: string;
  eh_retificacao: boolean;
  arquivo_pdf_id: number;
  arquivo_csv_id: number;
  pdf_sha256: string;
  csv_sha256: string;
}

export const homologarFinal = (editalId: number) => api<Ata>(`/editais/${editalId}/homologar-final`, { method: "POST" });
export const devolverAjustes = (editalId: number, justificativa: string) =>
  api<Edital>(`/editais/${editalId}/devolver-ajustes`, { method: "POST", body: JSON.stringify({ justificativa }) });
export const atasDoEdital = (editalId: number) => api<Ata[]>(`/editais/${editalId}/atas`);
export const baixarAtaPdf = (a: Ata) => baixarArquivo(`/arquivos/${a.arquivo_pdf_id}/download`, `ata-edital-${a.edital_id}.pdf`);
export const baixarListaCsv = (a: Ata) =>
  baixarArquivo(`/arquivos/${a.arquivo_csv_id}/download`, `resultado-final-edital-${a.edital_id}.csv`);

// --- TRV-01: notificações -------------------------------------------------------------------------
export interface Notificacao {
  id: number;
  tipo: string;
  titulo: string;
  mensagem: string;
  lida: boolean;
  email_status: string;
  criado_em: string;
}

export const listarNotificacoes = () => api<{ itens: Notificacao[]; nao_lidas: number }>("/notificacoes?limite=30");
export const marcarLida = (id: number) => api<void>(`/notificacoes/${id}/lida`, { method: "POST" });
export const marcarTodasLidas = () => api<void>("/notificacoes/lidas", { method: "POST" });

// --- TRV-03: auditoria ------------------------------------------------------------------------------
export interface RegistroAuditoria {
  id: number;
  usuario_id: number | null;
  usuario_nome: string | null;
  acao: string;
  entidade: string;
  entidade_id: number;
  dados_antes: Record<string, unknown> | null;
  dados_depois: Record<string, unknown> | null;
  ip_origem: string | null;
  destaque: boolean;
  criado_em: string;
}

export interface FiltrosAuditoria {
  edital_id?: number;
  inscricao_id?: number;
  acao?: string;
  somente_destaques?: boolean;
  limite?: number;
  deslocamento?: number;
}

export function consultarAuditoria(f: FiltrosAuditoria) {
  const q = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (v !== undefined && v !== "" && v !== false) q.set(k, String(v));
  });
  return api<{ itens: RegistroAuditoria[]; total: number }>(`/auditoria?${q}`);
}
