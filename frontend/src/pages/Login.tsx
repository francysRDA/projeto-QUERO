import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/cliente";
import { useAuth } from "../auth/AuthContext";

const CONTAS_DEMO = [
  { email: "prograd@quero.local", rotulo: "Pró-Reitoria" },
  { email: "carlos.avaliador@quero.local", rotulo: "Avaliador" },
  { email: "ana@aluno.quero.local", rotulo: "Estudante" },
];

export function Login() {
  const { usuario, entrar } = useAuth();
  const navegar = useNavigate();
  const local = useLocation();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (usuario) return <Navigate to="/" replace />;

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await entrar(email, senha);
      navegar((local.state as { de?: string } | null)?.de ?? "/", { replace: true });
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Não foi possível conectar ao servidor.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold text-marca-800">QUERO</h1>
        <p className="mb-6 text-sm text-slate-600">Estágios, monitorias e bolsas acadêmicas</p>

        <form onSubmit={enviar} className="space-y-4 rounded-lg border bg-white p-6 shadow-sm" noValidate>
          <div>
            <label htmlFor="email" className="block text-sm font-medium">E-mail institucional</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label htmlFor="senha" className="block text-sm font-medium">Senha</label>
            <input
              id="senha"
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
          </div>
          {erro && (
            <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
              {erro}
            </p>
          )}
          <button
            type="submit"
            disabled={enviando}
            className="w-full rounded bg-marca-700 py-2 font-semibold text-white hover:bg-marca-800 disabled:opacity-60"
          >
            {enviando ? "Entrando…" : "Entrar"}
          </button>
          <p className="text-xs text-slate-500">
            Login local de desenvolvimento. Em produção, o acesso será pelo SSO institucional.
          </p>
        </form>

        <details className="mt-4 text-sm text-slate-600">
          <summary className="cursor-pointer">Contas de demonstração (senha: quero123)</summary>
          <ul className="mt-2 space-y-1">
            {CONTAS_DEMO.map((c) => (
              <li key={c.email}>
                <button
                  type="button"
                  className="text-marca-700 underline"
                  onClick={() => {
                    setEmail(c.email);
                    setSenha("quero123");
                  }}
                >
                  {c.rotulo}: {c.email}
                </button>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </main>
  );
}
