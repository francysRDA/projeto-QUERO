import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { Perfil } from "../api/cliente";
import { useAuth } from "./AuthContext";

/**
 * Guarda de rota apenas para UX. A autorização real é SEMPRE feita no backend (DoD §4.7 item 2).
 */
export function RotaProtegida({ perfis }: { perfis?: Perfil[] }) {
  const { usuario, carregando } = useAuth();
  const local = useLocation();

  if (carregando) return <p className="p-8 text-slate-600" role="status">Carregando…</p>;
  if (!usuario) return <Navigate to="/login" replace state={{ de: local.pathname }} />;
  if (perfis && !perfis.includes(usuario.perfil)) return <Navigate to="/" replace />;
  return <Outlet />;
}
