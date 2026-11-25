import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { obterEdital } from "../../api/editais";
import { baixarComprovante, inscrever, minhasInscricoes } from "../../api/inscricoes";
import { CamposDocumentos, arquivosValidos } from "../../components/CamposDocumentos";
import { Botao, Cartao, ErroApiBox, NOME_CATEGORIA, StatusBadge, fmtDataHora, fmtMoeda } from "../../components/ui";

/** Detalhe do edital + formulário de inscrição (UC-03). */
export function EditalInscricao() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const edital = useQuery({ queryKey: ["edital", id], queryFn: () => obterEdital(id) });
  const minhas = useQuery({ queryKey: ["inscricoes", "me"], queryFn: minhasInscricoes });
  const [arquivos, setArquivos] = useState<Record<number, File>>({});

  const enviar = useMutation({
    mutationFn: () => inscrever(id, arquivos),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inscricoes"] }),
  });

  if (edital.isLoading) return <p role="status">Carregando…</p>;
  if (!edital.data) return <ErroApiBox erro={edital.error} />;
  const e = edital.data;
  const existente = minhas.data?.find((i) => i.edital.id === id);
  const prazoAberto = e.status === "ABERTO" && new Date(e.data_fim_inscricao) > new Date();

  return (
    <div className="space-y-5">
      <Link to="/editais" className="text-sm text-marca-700 underline">← Editais abertos</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{e.titulo}</h1>
        <StatusBadge status={e.status} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Cartao titulo="Sobre o edital">
            <p className="whitespace-pre-line text-sm text-slate-700">{e.descricao}</p>
          </Cartao>

          {existente ? (
            <Cartao titulo="Sua inscrição">
              <p className="text-sm">
                Protocolo <strong>{existente.protocolo}</strong>, enviada em {fmtDataHora(existente.data_submissao_original)}.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link to="/minhas-inscricoes" className="rounded bg-marca-700 px-3 py-1.5 text-sm font-medium text-white">
                  Acompanhar inscrição
                </Link>
                <Botao variante="secundario" onClick={() => void baixarComprovante(existente)}>Baixar comprovante</Botao>
              </div>
            </Cartao>
          ) : prazoAberto ? (
            <Cartao titulo="Inscrever-se">
              <p className="mb-3 text-sm text-slate-600">
                Anexe os documentos em PDF (até 10 MB cada). Seus dados acadêmicos (vínculo, curso e CR) serão
                consultados e registrados no momento do envio.
              </p>
              <form onSubmit={(ev) => { ev.preventDefault(); enviar.mutate(); }} className="space-y-4">
                <CamposDocumentos documentos={e.documentos} arquivos={arquivos} aoMudar={setArquivos} />
                <ErroApiBox erro={enviar.error} />
                <Botao type="submit" disabled={enviar.isPending || !arquivosValidos(e.documentos, arquivos, true)}>
                  {enviar.isPending ? "Enviando documentos…" : "Enviar inscrição"}
                </Botao>
              </form>
            </Cartao>
          ) : (
            <Cartao><p className="text-sm text-slate-600">As inscrições para este edital não estão abertas.</p></Cartao>
          )}
        </div>

        <Cartao titulo="Resumo">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-slate-500">Categoria</dt><dd>{NOME_CATEGORIA[e.categoria]}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Modalidade</dt><dd>{e.modalidade}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Bolsa</dt><dd>{fmtMoeda(e.valor_bolsa)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Vagas</dt><dd>{e.vagas}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Carga horária</dt><dd>{e.carga_horaria_semanal} h/sem.</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">CR mínimo</dt><dd>{Number(e.cr_minimo).toFixed(2)}</dd></div>
          </dl>
          <h3 className="mt-4 text-sm font-semibold">Cursos autorizados</h3>
          <ul className="list-disc pl-5 text-sm">{e.cursos.map((c) => <li key={c.id}>{c.nome_curso}</li>)}</ul>
          <h3 className="mt-4 text-sm font-semibold">Cronograma</h3>
          <ul className="space-y-1 text-sm">
            <li>Inscrições: {fmtDataHora(e.data_inicio_inscricao)} a {fmtDataHora(e.data_fim_inscricao)}</li>
            <li>Resultado preliminar: {fmtDataHora(e.data_resultado_preliminar)}</li>
            <li>Prazo de recurso: {e.prazo_recurso_horas} h após o preliminar</li>
            <li>Resultado final: {fmtDataHora(e.data_homologacao_final)}</li>
          </ul>
        </Cartao>
      </div>
    </div>
  );
}
