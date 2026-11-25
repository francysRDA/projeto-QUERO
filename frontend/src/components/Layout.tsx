import { NavLink, Outlet } from "react-router-dom";
import type { Perfil } from "../api/cliente";
import { useAuth } from "../auth/AuthContext";

const NOMES_PERFIL: Record<Perfil, string> = {
  ESTUDANTE: "Estudante",
  AVALIADOR: "Avaliador(a)",
  PRO_REITOR: "Pró-Reitoria",
};

const MENU: Record<Perfil, { para: string; rotulo: string }[]> = {
  ESTUDANTE: [
    { para: "/", rotulo: "Início" },
    { para: "/editais", rotulo: "Editais abertos" },
    { para: "/minhas-inscricoes", rotulo: "Minhas inscrições" },
  ],
  AVALIADOR: [
    { para: "/", rotulo: "Início" },
    { para: "/avaliacoes", rotulo: "Minhas comissões" },
  ],
  PRO_REITOR: [
    { para: "/", rotulo: "Início" },
    { para: "/gestao/editais", rotulo: "Gestão de editais" },
    { para: "/auditoria", rotulo: "Auditoria" },
  ],
};

export function Layout() {
  const { usuario, sair } = useAuth();
  if (!usuario) return null;

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:p-2 focus:bg-white">
        Pular para o conteúdo
      </a>
      <header className="bg-marca-800 text-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-xl font-bold tracking-tight">QUERO</span>
          <nav aria-label="Navegação principal" className="flex flex-wrap gap-1">
            {MENU[usuario.perfil].map((item) => (
              <NavLink
                key={item.para}
                to={item.para}
                end={item.para === "/"}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm ${isActive ? "bg-white/20 font-semibold" : "hover:bg-white/10"}`
                }
              >
                {item.rotulo}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span>
              {usuario.nome} <span className="opacity-75">· {NOMES_PERFIL[usuario.perfil]}</span>
            </span>
            <button
              onClick={() => void sair()}
              className="rounded border border-white/40 px-3 py-1 hover:bg-white/10"
            >
              Sair
            </button>
          </div>
        </div>
      </header>
      <main id="conteudo" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t bg-white py-4 text-center text-xs text-slate-500">
        QUERO — Quadro Universitário de Estágios Remunerados e Oportunidades · protótipo
      </footer>
    </div>
  );
}
