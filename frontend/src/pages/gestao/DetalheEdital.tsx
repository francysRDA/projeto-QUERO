import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  cancelarEdital,
  designarComissao,
  iniciarAvaliacao,
  listarAvaliadores,
  listarComissao,
  obterEdital,
  publicarEdital,
  removerDaComissao,
  type Edital,
} from "../../api/editais";
import { RelogioDemo } from "../../components/RelogioDemo";
import { AvaliacaoEdital } from "./AvaliacaoEdital";
import { InscricoesEdital } from "./InscricoesEdital";
import {
  Botao,
  Cartao,
  ErroApiBox,
  NOME_CATEGORIA,
  StatusBadge,
  classeInput,
  fmtDataHora,
  fmtMoeda,
} from "../../components/ui";

const TERMINAIS = ["ENCERRADO", "CANCELADO"];

export function DetalheEdital() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const edital = useQuery({ queryKey: ["edital", id], queryFn: () => obterEdital(id) });

  const atualizar = (e: Edital) => {
    qc.setQueryData(["edital", id], e);
    qc.invalidateQueries({ queryKey: ["editais"] });
  };
  const publicar = useMutation({ mutationFn: () => publicarEdital(id), onSuccess: atualizar });
  const iniciar = useMutation({ mutationFn: () => iniciarAvaliacao(id), onSuccess: atualizar });

  if (edital.isLoading) return <p role="status">Carregando…</p>;
  if (edital.error || !edital.data) return <ErroApiBox erro={edital.error} />;
  const e = edital.data;

  return (
    <div className="space-y-5">
      <div>
        <Link to="/gestao/editais" className="text-sm text-marca-700 underline">← Gestão de editais</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">{e.titulo}</h1>
          <StatusBadge status={e.status} />
        </div>
      </div>

      <RelogioDemo />

      <Cartao
        titulo="Ações"
        acoes={
          !TERMINAIS.includes(e.status) && (
            <Link to={`/gestao/editais/${id}/editar`} className="text-sm text-marca-700 underline">
              {e.status === "RASCUNHO" ? "Editar" : "Editar descrição"}
            </Link>
          )
        }
      >
        <div className="flex flex-wrap gap-2">
          {e.status === "RASCUNHO" && (
            <Botao onClick={() => publicar.mutate()} disabled={publicar.isPending}>Publicar edital</Botao>
          )}
          {e.status === "INSCRICOES_ENCERRADAS" && (
            <Botao onClick={() => iniciar.mutate()} disabled={iniciar.isPending}>Iniciar avaliação agora</Botao>
          )}
          {e.status === "ABERTO" && (
            <p className="text-sm text-slate-600">
              As inscrições encerram automaticamente em {fmtDataHora(e.data_fim_inscricao)}.
            </p>
          )}
        </div>
        <div className="mt-3 space-y-2">
          <ErroApiBox erro={publicar.error ?? iniciar.error} />
        </div>
        {!TERMINAIS.includes(e.status) && <Cancelamento edital={e} aoCancelar={atualizar} />}
        {e.status === "CANCELADO" && (
          <p className="rounded bg-red-50 p-3 text-sm text-red-900">
            <strong>Cancelado.</strong> Justificativa: {e.justificativa_cancelamento}
          </p>
        )}
      </Cartao>

      <div className="grid gap-5 lg:grid-cols-2">
        <Cartao titulo="Parâmetros">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-slate-500">Categoria</dt><dd>{NOME_CATEGORIA[e.categoria]}</dd>
            <dt className="text-slate-500">Modalidade</dt><dd>{e.modalidade}</dd>
            <dt className="text-slate-500">Vagas</dt><dd>{e.vagas}</dd>
            <dt className="text-slate-500">Bolsa</dt><dd>{fmtMoeda(e.valor_bolsa)}</dd>
            <dt className="text-slate-500">Carga horária</dt><dd>{e.carga_horaria_semanal} h/semana</dd>
            <dt className="text-slate-500">CR mínimo</dt><dd>{Number(e.cr_minimo).toFixed(2)}</dd>
            <dt className="text-slate-500">Prazo de recurso</dt><dd>{e.prazo_recurso_horas} h</dd>
          </dl>
          <h3 className="mt-4 text-sm font-semibold">Cursos autorizados</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {e.cursos.map((c) => <li key={c.id}>{c.nome_curso} ({c.codigo_curso})</li>)}
            {e.cursos.length === 0 && <li className="text-slate-500">Nenhum curso cadastrado.</li>}
          </ul>
          <h3 className="mt-4 text-sm font-semibold">Documentos exigidos</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {e.documentos.map((d) => (
              <li key={d.id}>{d.nome} {d.obrigatorio ? "" : <span className="text-slate-500">(opcional)</span>}</li>
            ))}
            {e.documentos.length === 0 && <li className="text-slate-500">Nenhum documento cadastrado.</li>}
          </ul>
        </Cartao>

        <Cartao titulo="Cronograma">
          <ol className="space-y-2 text-sm">
            {[
              ["Início das inscrições", e.data_inicio_inscricao],
              ["Fim das inscrições", e.data_fim_inscricao],
              ["Início da avaliação", e.data_inicio_avaliacao],
              ["Resultado preliminar", e.data_resultado_preliminar],
              ["Homologação final", e.data_homologacao_final],
            ].map(([rotulo, data]) => (
              <li key={rotulo} className="flex justify-between border-b pb-1">
                <span className="text-slate-600">{rotulo}</span>
                <span>{fmtDataHora(data)}</span>
              </li>
            ))}
          </ol>
          <h3 className="mt-4 text-sm font-semibold">Descrição</h3>
          <p className="mt-1 whitespace-pre-line text-sm text-slate-700">{e.descricao}</p>
        </Cartao>
      </div>

      <AvaliacaoEdital edital={e} />

      {e.status !== "RASCUNHO" && <InscricoesEdital editalId={e.id} />}

      <Comissao edital={e} />
    </div>
  );
}

function Cancelamento({ edital, aoCancelar }: { edital: Edital; aoCancelar: (e: Edital) => void }) {
  const [aberto, setAberto] = useState(false);
  const [justificativa, setJustificativa] = useState("");
  const cancelar = useMutation({
    mutationFn: () => cancelarEdital(edital.id, justificativa),
    onSuccess: (e) => {
      setAberto(false);
      aoCancelar(e);
    },
  });

  if (!aberto) {
    return (
      <div className="mt-4 border-t pt-3">
        <Botao variante="secundario" onClick={() => setAberto(true)}>Cancelar edital…</Botao>
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-2 border-t pt-3">
      <label htmlFor="justificativa" className="block text-sm font-medium">
        Justificativa do cancelamento (mínimo 10 caracteres) — será enviada a todos os inscritos
      </label>
      <textarea id="justificativa" rows={3} className={classeInput} value={justificativa}
        onChange={(ev) => setJustificativa(ev.target.value)} />
      <ErroApiBox erro={cancelar.error} />
      <div className="flex gap-2">
        <Botao variante="perigo" disabled={cancelar.isPending || justificativa.trim().length < 10}
          onClick={() => cancelar.mutate()}>
          Confirmar cancelamento
        </Botao>
        <Botao variante="secundario" onClick={() => setAberto(false)}>Desistir</Botao>
      </div>
    </div>
  );
}

function Comissao({ edital }: { edital: Edital }) {
  const qc = useQueryClient();
  const chave = ["comissao", edital.id];
  const membros = useQuery({ queryKey: chave, queryFn: () => listarComissao(edital.id) });
  const avaliadores = useQuery({ queryKey: ["avaliadores"], queryFn: listarAvaliadores });
  const [selecionados, setSelecionados] = useState<number[]>([]);

  const designar = useMutation({
    mutationFn: () => designarComissao(edital.id, selecionados),
    onSuccess: (m) => {
      qc.setQueryData(chave, m);
      setSelecionados([]);
    },
  });
  const remover = useMutation({
    mutationFn: (avaliadorId: number) => removerDaComissao(edital.id, avaliadorId),
    onSuccess: () => qc.invalidateQueries({ queryKey: chave }),
  });

  const editavel = !TERMINAIS.includes(edital.status);
  const idsMembros = new Set(membros.data?.map((m) => m.avaliador_id));
  const disponiveis = avaliadores.data?.filter((a) => !idsMembros.has(a.id)) ?? [];

  return (
    <Cartao titulo="Comissão avaliadora (EDT-04)">
      {membros.data?.length === 0 && <p className="text-sm text-slate-500">Nenhum avaliador designado.</p>}
      <ul className="divide-y text-sm">
        {membros.data?.map((m) => (
          <li key={m.avaliador_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              <strong>{m.nome}</strong> <span className="text-slate-500">· {m.email}</span>
            </span>
            {editavel && (
              <Botao variante="secundario" disabled={remover.isPending} onClick={() => remover.mutate(m.avaliador_id)}
                aria-label={`Remover ${m.nome} da comissão`}>
                Remover
              </Botao>
            )}
          </li>
        ))}
      </ul>
      {membros.data?.length === 1 && (
        <p className="mt-2 text-xs text-amber-800">
          Comissão com um único membro: recursos exigirão justificativa reforçada (RN-11).
        </p>
      )}

      {editavel && disponiveis.length > 0 && (
        <fieldset className="mt-4 border-t pt-3">
          <legend className="text-sm font-medium">Designar avaliadores</legend>
          <div className="mt-2 grid gap-1 sm:grid-cols-2">
            {disponiveis.map((a) => (
              <label key={a.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={selecionados.includes(a.id)}
                  onChange={(ev) =>
                    setSelecionados((s) => (ev.target.checked ? [...s, a.id] : s.filter((x) => x !== a.id)))
                  } />
                {a.nome}
              </label>
            ))}
          </div>
          <Botao className="mt-3" disabled={selecionados.length === 0 || designar.isPending} onClick={() => designar.mutate()}>
            Designar selecionados
          </Botao>
        </fieldset>
      )}
      <div className="mt-3 space-y-2">
        <ErroApiBox erro={designar.error ?? remover.error ?? membros.error} />
      </div>
    </Cartao>
  );
}
