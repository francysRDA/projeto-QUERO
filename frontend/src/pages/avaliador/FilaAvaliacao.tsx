import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  declararImpedimento,
  filaAvaliacao,
  obterClassificacao,
  publicarPreliminar,
  salvarAvaliacao,
  type ItemFila,
  type Parecer,
} from "../../api/avaliacoes";
import { baixarDocumento } from "../../api/inscricoes";
import { BarraProgresso, TabelaClassificacao } from "../../components/TabelaClassificacao";
import { Botao, Cartao, ErroApiBox, StatusBadge, classeInput, fmtDataHora } from "../../components/ui";

const ROTULO_STATUS = { RASCUNHO: "Rascunho", CONFIRMADA: "Confirmada", RETIFICADA: "Retificada" } as const;

/** UC-07: fila de avaliação de mérito do avaliador designado (AVA-01, AVA-02). */
export function FilaAvaliacao() {
  const editalId = Number(useParams().editalId);
  const qc = useQueryClient();
  const fila = useQuery({ queryKey: ["fila", editalId], queryFn: () => filaAvaliacao(editalId) });
  const classif = useQuery({ queryKey: ["classificacao", editalId], queryFn: () => obterClassificacao(editalId) });
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const publicar = useMutation({
    mutationFn: () => publicarPreliminar(editalId),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (fila.isLoading) return <p role="status">Carregando…</p>;
  if (!fila.data) return <ErroApiBox erro={fila.error} />;
  const f = fila.data;
  const atual = f.itens.find((i) => i.inscricao_id === selecionada) ?? null;

  return (
    <div className="space-y-5">
      <Link to="/avaliacoes" className="text-sm text-marca-700 underline">← Minhas comissões</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{f.edital_titulo}</h1>
        <StatusBadge status={f.edital_status} />
      </div>

      <Cartao titulo="Progresso da comissão">
        <BarraProgresso feitas={f.progresso.confirmadas} total={f.progresso.homologadas} />
        <p className="mt-2 text-xs text-slate-600">
          {f.progresso.em_rascunho} em rascunho · {f.progresso.nao_iniciadas} não iniciada(s)
        </p>
        {f.progresso.sem_avaliador_disponivel.length > 0 && (
          <p className="mt-2 text-sm text-amber-900">
            Sem avaliador disponível (todos declararam impedimento): {f.progresso.sem_avaliador_disponivel.join(", ")}.
            A Pró-Reitoria foi avisada.
          </p>
        )}
        {f.edital_status === "EM_AVALIACAO" && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Botao disabled={!f.progresso.pode_publicar || publicar.isPending} onClick={() => publicar.mutate()}>
              Publicar resultado preliminar
            </Botao>
            {!f.progresso.pode_publicar && (
              <span className="text-xs text-slate-600">Disponível quando todas as inscrições homologadas tiverem avaliação confirmada.</span>
            )}
          </div>
        )}
        <div className="mt-2"><ErroApiBox erro={publicar.error} /></div>
      </Cartao>

      {!f.pode_avaliar && (
        <p className="rounded border border-slate-300 bg-white p-3 text-sm text-slate-700">
          {f.edital_status === "INSCRICOES_ENCERRADAS" || f.edital_status === "ABERTO"
            ? "A avaliação ainda não começou."
            : "A fase de avaliação deste edital está encerrada."}
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-5">
        <Cartao titulo={`Candidaturas (${f.itens.length})`}>
          <ul className="space-y-1 lg:col-span-2">
            {f.itens.map((i) => (
              <li key={i.inscricao_id}>
                <button
                  onClick={() => setSelecionada(i.inscricao_id)}
                  aria-current={selecionada === i.inscricao_id}
                  className={`w-full rounded border px-3 py-2 text-left text-sm ${selecionada === i.inscricao_id ? "border-marca-700 bg-marca-50" : "hover:bg-slate-50"}`}
                >
                  <span className="font-medium">{i.estudante_nome}</span>
                  <span className="block text-xs text-slate-500">
                    {i.protocolo} · {i.avaliacao ? `${ROTULO_STATUS[i.avaliacao.status]}${i.avaliacao.nota_merito ? ` · nota ${Number(i.avaliacao.nota_merito).toFixed(2)}` : ""}` : "Não iniciada"}
                  </span>
                </button>
              </li>
            ))}
            {f.itens.length === 0 && <li className="text-sm text-slate-500">Nenhuma candidatura na sua fila.</li>}
          </ul>
        </Cartao>
        <div className="lg:col-span-4">
          {atual ? (
            <FormAvaliacao key={atual.inscricao_id} item={atual} podeAvaliar={f.pode_avaliar} aoSalvar={() => {
              qc.invalidateQueries({ queryKey: ["fila", editalId] });
              qc.invalidateQueries({ queryKey: ["classificacao", editalId] });
            }} aoImpedir={() => setSelecionada(null)} />
          ) : (
            <Cartao><p className="text-sm text-slate-500">Selecione uma candidatura para avaliar.</p></Cartao>
          )}
        </div>
      </div>

      {classif.data && (
        <Cartao titulo="Classificação">
          <TabelaClassificacao dados={classif.data} />
        </Cartao>
      )}
    </div>
  );
}

function FormAvaliacao({ item, podeAvaliar, aoSalvar, aoImpedir }: {
  item: ItemFila; podeAvaliar: boolean; aoSalvar: () => void; aoImpedir: () => void;
}) {
  const qc = useQueryClient();
  const av = item.avaliacao;
  const finalizada = av?.status === "CONFIRMADA" || av?.status === "RETIFICADA";
  const [nota, setNota] = useState(av?.nota_merito ?? "");
  const [parecer, setParecer] = useState<Parecer | null>(av?.parecer ?? null);
  const [justificativa, setJustificativa] = useState(av?.justificativa ?? "");
  const [declaracao, setDeclaracao] = useState(av?.declaracao_sem_impedimento ?? false);
  const [retificando, setRetificando] = useState(false);
  const [motivoRetificacao, setMotivoRetificacao] = useState("");
  const [impedindo, setImpedindo] = useState(false);
  const [motivoImpedimento, setMotivoImpedimento] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => setAviso(null), [nota, parecer, justificativa, declaracao]);

  const salvar = useMutation({
    mutationFn: (acao: "RASCUNHO" | "CONFIRMAR" | "RETIFICAR") =>
      salvarAvaliacao(item.inscricao_id, {
        acao, nota_merito: nota === "" ? null : Number(nota).toFixed(2), parecer, justificativa: justificativa || null,
        declaracao_sem_impedimento: declaracao, justificativa_retificacao: acao === "RETIFICAR" ? motivoRetificacao : null,
      }),
    onSuccess: (a) => {
      setRetificando(false);
      setAviso(a.status === "RASCUNHO" ? "Rascunho salvo." : `Avaliação ${a.status === "CONFIRMADA" ? "confirmada" : "retificada"}.`);
      aoSalvar();
    },
  });
  const impedir = useMutation({
    mutationFn: () => declararImpedimento(item.inscricao_id, motivoImpedimento),
    onSuccess: () => {
      qc.invalidateQueries();
      aoImpedir();
    },
  });

  const bloqueado = !podeAvaliar || (finalizada && !retificando);

  return (
    <Cartao titulo={item.estudante_nome}>
      <p className="text-sm text-slate-600">
        {item.protocolo} · enviada em {fmtDataHora(item.data_submissao_original)}
        {item.curso_congelado && <> · {item.curso_congelado} · CR {Number(item.cr_congelado).toFixed(2)}</>}
      </p>

      <h3 className="mt-4 text-sm font-semibold">Documentos (versões vigentes)</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {item.arquivos.map((a) => (
          <li key={a.id}>
            <button className="text-marca-700 underline" onClick={() => void baixarDocumento(a)}>{a.nome_original}</button>
            <span className="text-xs text-slate-500"> · v{a.versao}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-slate-500">Cada download fica registrado na auditoria (LGPD, §13.1).</p>

      <form className="mt-5 space-y-4 border-t pt-4" onSubmit={(e) => e.preventDefault()}>
        {av && <p className="text-xs text-slate-600">Situação: <strong>{ROTULO_STATUS[av.status]}</strong> · atualizada em {fmtDataHora(av.atualizado_em)}</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="nota" className="block text-sm font-medium">Nota de mérito (0,00 a 10,00)</label>
            <input id="nota" type="number" min="0" max="10" step="0.01" disabled={bloqueado} className={`${classeInput} mt-1`}
              value={nota} onChange={(e) => setNota(e.target.value)} />
          </div>
          <fieldset>
            <legend className="text-sm font-medium">Parecer</legend>
            <div className="mt-2 flex gap-4 text-sm">
              {(["DEFERIDO", "INDEFERIDO"] as const).map((p) => (
                <label key={p} className="flex items-center gap-1">
                  <input type="radio" name="parecer" disabled={bloqueado} checked={parecer === p} onChange={() => setParecer(p)} />
                  {p === "DEFERIDO" ? "Deferido" : "Indeferido"}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        <div>
          <label htmlFor="justificativa" className="block text-sm font-medium">
            Justificativa técnica {parecer === "INDEFERIDO" ? <span className="text-red-700">(obrigatória para indeferido — RN-08)</span> : "(opcional)"}
          </label>
          <textarea id="justificativa" rows={3} disabled={bloqueado} className={`${classeInput} mt-1`}
            value={justificativa} onChange={(e) => setJustificativa(e.target.value)} />
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" disabled={bloqueado} checked={declaracao} onChange={(e) => setDeclaracao(e.target.checked)} />
          <span>
            Declaro que <strong>não possuo impedimento ou suspeição</strong> em relação a este(a) candidato(a) (orientação,
            parentesco ou vínculo direto) — RN-07.
          </span>
        </label>

        {retificando && (
          <div>
            <label htmlFor="motivo-ret" className="block text-sm font-medium">Motivo da retificação (obrigatório, fica na auditoria)</label>
            <textarea id="motivo-ret" rows={2} className={`${classeInput} mt-1`} value={motivoRetificacao}
              onChange={(e) => setMotivoRetificacao(e.target.value)} />
          </div>
        )}

        <ErroApiBox erro={salvar.error} />
        {aviso && <p role="status" className="text-sm text-green-800">{aviso}</p>}

        {podeAvaliar && (
          <div className="flex flex-wrap gap-2">
            {!finalizada && (
              <>
                <Botao type="button" variante="secundario" disabled={salvar.isPending} onClick={() => salvar.mutate("RASCUNHO")}>
                  Salvar rascunho
                </Botao>
                <Botao type="button" disabled={salvar.isPending} onClick={() => salvar.mutate("CONFIRMAR")}>Confirmar avaliação</Botao>
              </>
            )}
            {finalizada && !retificando && (
              <Botao type="button" variante="secundario" onClick={() => setRetificando(true)}>Retificar avaliação…</Botao>
            )}
            {retificando && (
              <>
                <Botao type="button" disabled={salvar.isPending || motivoRetificacao.trim().length < 10} onClick={() => salvar.mutate("RETIFICAR")}>
                  Salvar retificação
                </Botao>
                <Botao type="button" variante="secundario" onClick={() => setRetificando(false)}>Cancelar</Botao>
              </>
            )}
          </div>
        )}
      </form>

      {podeAvaliar && !finalizada && (
        <div className="mt-5 border-t pt-4">
          {!impedindo ? (
            <button className="text-sm text-red-800 underline" onClick={() => setImpedindo(true)}>
              Declarar impedimento/suspeição para esta candidatura
            </button>
          ) : (
            <div className="space-y-2 rounded border border-red-200 bg-red-50 p-3">
              <label htmlFor="motivo-imp" className="block text-sm font-medium text-red-900">
                Motivo do impedimento (a candidatura será redirecionada a outro membro da comissão)
              </label>
              <textarea id="motivo-imp" rows={2} className={classeInput} value={motivoImpedimento}
                onChange={(e) => setMotivoImpedimento(e.target.value)} />
              <ErroApiBox erro={impedir.error} />
              <div className="flex gap-2">
                <Botao variante="perigo" disabled={impedir.isPending || motivoImpedimento.trim().length < 10} onClick={() => impedir.mutate()}>
                  Confirmar impedimento
                </Botao>
                <Botao variante="secundario" onClick={() => setImpedindo(false)}>Cancelar</Botao>
              </div>
            </div>
          )}
        </div>
      )}
    </Cartao>
  );
}
