/**
 * Cliente HTTP da API.
 * - Access token fica só em memória (não em localStorage) para reduzir exposição a XSS.
 * - Em 401, tenta uma vez renovar via cookie HttpOnly de refresh e repete a requisição.
 */

export type Perfil = "ESTUDANTE" | "AVALIADOR" | "PRO_REITOR";

export interface Usuario {
  id: number;
  nome: string;
  email: string;
  matricula: string | null;
  perfil: Perfil;
}

export interface ErroApi {
  codigo: string;
  mensagem: string;
  detalhes: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public corpo: ErroApi,
  ) {
    super(corpo.mensagem);
  }
}

let accessToken: string | null = null;
let aoPerderSessao: (() => void) | null = null;

export function definirAoPerderSessao(fn: () => void) {
  aoPerderSessao = fn;
}

let renovando: Promise<boolean> | null = null;

export async function renovarToken(): Promise<boolean> {
  // Evita várias renovações simultâneas quando muitas requisições recebem 401 juntas.
  renovando ??= (async () => {
    try {
      const r = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" });
      if (!r.ok) {
        accessToken = null;
        return false;
      }
      accessToken = (await r.json()).access_token;
      return true;
    } finally {
      setTimeout(() => (renovando = null), 0);
    }
  })();
  return renovando;
}

async function lerErro(r: Response): Promise<ErroApi> {
  try {
    const corpo = await r.json();
    if (corpo?.mensagem) return corpo;
    if (Array.isArray(corpo?.detail)) {
      // Erro de validação do FastAPI/Pydantic.
      return {
        codigo: "VALIDACAO",
        mensagem: "Dados inválidos.",
        detalhes: corpo.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join(".")}: ${d.msg}`),
      };
    }
  } catch {
    /* corpo não é JSON */
  }
  return { codigo: "ERRO", mensagem: `Erro ${r.status}`, detalhes: [] };
}

export async function api<T>(caminho: string, init: RequestInit = {}, tentarRenovar = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const r = await fetch(`/api/v1${caminho}`, { ...init, headers, credentials: "same-origin" });

  if (r.status === 401 && tentarRenovar && !caminho.startsWith("/auth/")) {
    if (await renovarToken()) return api<T>(caminho, init, false);
    aoPerderSessao?.();
  }
  if (!r.ok) throw new ApiError(r.status, await lerErro(r));
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function login(email: string, senha: string): Promise<void> {
  const r = await api<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
  accessToken = r.access_token;
}

export async function logout(): Promise<void> {
  try {
    await api<void>("/auth/logout", { method: "POST" });
  } finally {
    accessToken = null;
  }
}

export const buscarMe = () => api<Usuario>("/auth/me");
