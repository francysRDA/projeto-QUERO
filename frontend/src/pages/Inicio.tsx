import { useAuth } from "../auth/AuthContext";

const RESUMO = {
  ESTUDANTE: "Consulte os editais abertos, envie sua inscrição e acompanhe cada etapa da seleção.",
  AVALIADOR: "Avalie as inscrições homologadas dos editais em que você integra a comissão.",
  PRO_REITOR: "Cadastre e publique editais, designe comissões e homologue os resultados.",
} as const;

export function Inicio() {
  const { usuario } = useAuth();
  if (!usuario) return null;
  return (
    <section>
      <h1 className="text-2xl font-bold">Olá, {usuario.nome.split(" ")[0]}</h1>
      <p className="mt-2 text-slate-700">{RESUMO[usuario.perfil]}</p>
    </section>
  );
}
