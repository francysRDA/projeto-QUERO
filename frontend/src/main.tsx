import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RotaProtegida } from "./auth/RotaProtegida";
import { Layout } from "./components/Layout";
import "./index.css";
import { EmConstrucao, Inicio } from "./pages/Inicio";
import { Login } from "./pages/Login";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<RotaProtegida />}>
              <Route element={<Layout />}>
                <Route index element={<Inicio />} />
                <Route element={<RotaProtegida perfis={["ESTUDANTE"]} />}>
                  <Route path="editais" element={<EmConstrucao titulo="Editais abertos" fatia={3} />} />
                  <Route path="minhas-inscricoes" element={<EmConstrucao titulo="Minhas inscrições" fatia={3} />} />
                </Route>
                <Route element={<RotaProtegida perfis={["AVALIADOR"]} />}>
                  <Route path="avaliacoes" element={<EmConstrucao titulo="Minhas comissões" fatia={5} />} />
                </Route>
                <Route element={<RotaProtegida perfis={["PRO_REITOR"]} />}>
                  <Route path="gestao/editais" element={<EmConstrucao titulo="Gestão de editais" fatia={2} />} />
                  <Route path="auditoria" element={<EmConstrucao titulo="Auditoria" fatia={7} />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
