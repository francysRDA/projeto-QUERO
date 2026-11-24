import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as cliente from "../api/cliente";
import type { Usuario } from "../api/cliente";

interface AuthValor {
  usuario: Usuario | null;
  carregando: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => Promise<void>;
}

const AuthCtx = createContext<AuthValor | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);

  // Ao abrir/recarregar a página, tenta restaurar a sessão pelo cookie de refresh.
  useEffect(() => {
    cliente.definirAoPerderSessao(() => setUsuario(null));
    (async () => {
      try {
        if (await cliente.renovarToken()) setUsuario(await cliente.buscarMe());
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

  const entrar = useCallback(async (email: string, senha: string) => {
    await cliente.login(email, senha);
    setUsuario(await cliente.buscarMe());
  }, []);

  const sair = useCallback(async () => {
    await cliente.logout();
    setUsuario(null);
  }, []);

  const valor = useMemo(() => ({ usuario, carregando, entrar, sair }), [usuario, carregando, entrar, sair]);
  return <AuthCtx.Provider value={valor}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthValor {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
