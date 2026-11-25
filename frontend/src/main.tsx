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
import { EditalInscricao } from "./pages/estudante/EditalInscricao";
import { MinhasInscricoes } from "./pages/estudante/MinhasInscricoes";
import { Vitrine } from "./pages/estudante/Vitrine";
import { FilaAvaliacao } from "./pages/avaliador/FilaAvaliacao";
import { MinhasComissoes } from "./pages/avaliador/MinhasComissoes";
import { DetalheEdital } from "./pages/gestao/DetalheEdital";
import { FormEdital } from "./pages/gestao/FormEdital";
import { ListaEditais } from "./pages/gestao/ListaEditais";

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
                  <Route path="editais" element={<Vitrine />} />
                  <Route path="editais/:id" element={<EditalInscricao />} />
                  <Route path="minhas-inscricoes" element={<MinhasInscricoes />} />
                </Route>
                <Route element={<RotaProtegida perfis={["AVALIADOR"]} />}>
                  <Route path="avaliacoes" element={<MinhasComissoes />} />
                  <Route path="avaliacoes/:editalId" element={<FilaAvaliacao />} />
                </Route>
                <Route element={<RotaProtegida perfis={["PRO_REITOR"]} />}>
                  <Route path="gestao/editais" element={<ListaEditais />} />
                  <Route path="gestao/editais/novo" element={<FormEdital />} />
                  <Route path="gestao/editais/:id" element={<DetalheEdital />} />
                  <Route path="gestao/editais/:id/editar" element={<FormEdital />} />
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
