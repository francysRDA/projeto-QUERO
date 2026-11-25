import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  atualizarEdital,
  criarEdital,
  obterEdital,
  type Categoria,
  type Curso,
  type Documento,
  type EditalEntrada,
} from "../../api/editais";
import { Botao, Campo, Cartao, ErroApiBox, classeInput } from "../../components/ui";

// O relógio oficial é America/Sao_Paulo (RN-03), sem horário de verão desde 2019: UTC-03:00.
const OFFSET_SP = "-03:00";

function isoParaLocal(iso: string): string {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const v = (t: string) => p.find((x) => x.type === t)!.value;
  return `${v("year")}-${v("month")}-${v("day")}T${v("hour")}:${v("minute")}`;
}
const localParaIso = (local: string) => `${local}:00${OFFSET_SP}`;

const DATAS = [
  ["data_inicio_inscricao", "Início das inscrições"],
  ["data_fim_inscricao", "Fim das inscrições"],
  ["data_inicio_avaliacao", "Início da avaliação"],
  ["data_resultado_preliminar", "Resultado preliminar"],
  ["data_homologacao_final", "Homologação final"],
] as const;
type CampoData = (typeof DATAS)[number][0];

interface Estado {
  titulo: string;
  descricao: string;
  categoria: Categoria;
  modalidade: string;
  valor_bolsa: string;
  carga_horaria_semanal: string;
  vagas: string;
  cr_minimo: string;
  prazo_recurso_horas: string;
  datas: Record<CampoData, string>;
  cursos: Curso[];
  documentos: Documento[];
}

function vazio(): Estado {
  const d = (dias: number) => {
    const t = new Date(Date.now() + dias * 86400000);
    t.setMinutes(0, 0, 0);
    return isoParaLocal(t.toISOString());
  };
  return {
    titulo: "", descricao: "", categoria: "MONITORIA", modalidade: "Presencial",
    valor_bolsa: "700.00", carga_horaria_semanal: "12", vagas: "1", cr_minimo: "7.00", prazo_recurso_horas: "48",
    datas: {
      data_inicio_inscricao: d(0), data_fim_inscricao: d(7), data_inicio_avaliacao: d(8),
      data_resultado_preliminar: d(12), data_homologacao_final: d(16),
    },
    cursos: [{ codigo_curso: "", nome_curso: "" }],
    documentos: [{ nome: "Histórico escolar", descricao: "", obrigatorio: true }],
  };
}

export function FormEdital() {
  const { id } = useParams();
  const editando = id !== undefined;
  const navegar = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState<Estado>(vazio);

  const existente = useQuery({ queryKey: ["edital", Number(id)], queryFn: () => obterEdital(Number(id)), enabled: editando });
  const somenteDescricao = editando && existente.data !== undefined && existente.data.status !== "RASCUNHO";

  useEffect(() => {
    const e = existente.data;
    if (!e) return;
    setF({
      titulo: e.titulo, descricao: e.descricao, categoria: e.categoria, modalidade: e.modalidade,
      valor_bolsa: e.valor_bolsa, carga_horaria_semanal: String(e.carga_horaria_semanal), vagas: String(e.vagas),
      cr_minimo: e.cr_minimo, prazo_recurso_horas: String(e.prazo_recurso_horas),
      datas: Object.fromEntries(DATAS.map(([k]) => [k, isoParaLocal(e[k])])) as Record<CampoData, string>,
      cursos: e.cursos.map(({ codigo_curso, nome_curso }) => ({ codigo_curso, nome_curso })),
      documentos: e.documentos.map(({ nome, descricao, obrigatorio }) => ({ nome, descricao, obrigatorio })),
    });
  }, [existente.data]);

  const salvar = useMutation({
    mutationFn: async () => {
      if (somenteDescricao) return atualizarEdital(Number(id), { descricao: f.descricao });
      const corpo: EditalEntrada = {
        titulo: f.titulo, descricao: f.descricao, categoria: f.categoria, modalidade: f.modalidade,
        valor_bolsa: f.valor_bolsa, carga_horaria_semanal: Number(f.carga_horaria_semanal), vagas: Number(f.vagas),
        cr_minimo: f.cr_minimo, prazo_recurso_horas: Number(f.prazo_recurso_horas),
        criterios_pontuacao: existente.data?.criterios_pontuacao ?? {},
        criterios_desempate: existente.data?.criterios_desempate ?? ["CR_DESC", "SUBMISSAO_ASC"],
        ...(Object.fromEntries(DATAS.map(([k]) => [k, localParaIso(f.datas[k])])) as Record<CampoData, string>),
        cursos: f.cursos.filter((c) => c.codigo_curso.trim() || c.nome_curso.trim()),
        documentos: f.documentos.filter((d) => d.nome.trim()),
      };
      return editando ? atualizarEdital(Number(id), corpo) : criarEdital(corpo);
    },
    onSuccess: (e) => {
      qc.invalidateQueries({ queryKey: ["editais"] });
      qc.setQueryData(["edital", e.id], e);
      navegar(`/gestao/editais/${e.id}`);
    },
  });

  const set = <K extends keyof Estado>(k: K, v: Estado[K]) => setF((s) => ({ ...s, [k]: v }));
  const bloq = somenteDescricao;

  function enviar(e: FormEvent) {
    e.preventDefault();
    salvar.mutate();
  }

  if (editando && existente.isLoading) return <p role="status">Carregando…</p>;

  return (
    <form onSubmit={enviar} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{editando ? "Editar edital" : "Novo edital"}</h1>
        <Link to={editando ? `/gestao/editais/${id}` : "/gestao/editais"} className="text-sm text-marca-700 underline">
          Voltar
        </Link>
      </div>

      {bloq && (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Este edital já foi publicado: apenas o texto descritivo pode ser alterado, e a alteração fica registrada na auditoria (EDT-01).
        </p>
      )}

      <Cartao titulo="Dados gerais">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <Campo rotulo="Título" id="titulo">
              <input id="titulo" required maxLength={200} disabled={bloq} className={classeInput}
                value={f.titulo} onChange={(e) => set("titulo", e.target.value)} />
            </Campo>
          </div>
          <div className="md:col-span-2">
            <Campo rotulo="Descrição" id="descricao">
              <textarea id="descricao" required rows={5} className={classeInput}
                value={f.descricao} onChange={(e) => set("descricao", e.target.value)} />
            </Campo>
          </div>
          <Campo rotulo="Categoria" id="categoria">
            <select id="categoria" disabled={bloq} className={classeInput} value={f.categoria}
              onChange={(e) => set("categoria", e.target.value as Categoria)}>
              <option value="ESTAGIO">Estágio</option>
              <option value="MONITORIA">Monitoria</option>
              <option value="BOLSA">Bolsa</option>
            </select>
          </Campo>
          <Campo rotulo="Modalidade" id="modalidade">
            <input id="modalidade" required maxLength={50} disabled={bloq} className={classeInput}
              value={f.modalidade} onChange={(e) => set("modalidade", e.target.value)} />
          </Campo>
          <Campo rotulo="Valor da bolsa (R$)" id="valor">
            <input id="valor" type="number" min="0" step="0.01" required disabled={bloq} className={classeInput}
              value={f.valor_bolsa} onChange={(e) => set("valor_bolsa", e.target.value)} />
          </Campo>
          <Campo rotulo="Carga horária semanal (h)" id="carga">
            <input id="carga" type="number" min="1" max="44" required disabled={bloq} className={classeInput}
              value={f.carga_horaria_semanal} onChange={(e) => set("carga_horaria_semanal", e.target.value)} />
          </Campo>
          <Campo rotulo="Vagas" id="vagas">
            <input id="vagas" type="number" min="1" required disabled={bloq} className={classeInput}
              value={f.vagas} onChange={(e) => set("vagas", e.target.value)} />
          </Campo>
          <Campo rotulo="CR mínimo" id="cr">
            <input id="cr" type="number" min="0" max="10" step="0.01" required disabled={bloq} className={classeInput}
              value={f.cr_minimo} onChange={(e) => set("cr_minimo", e.target.value)} />
          </Campo>
          <Campo rotulo="Prazo de recurso (horas)" id="recurso" ajuda="Padrão sugerido: 48 h (RN-10, DP-06).">
            <input id="recurso" type="number" min="1" required disabled={bloq} className={classeInput}
              value={f.prazo_recurso_horas} onChange={(e) => set("prazo_recurso_horas", e.target.value)} />
          </Campo>
        </div>
      </Cartao>

      <Cartao titulo="Cronograma (horário de Brasília)">
        <div className="grid gap-4 md:grid-cols-3">
          {DATAS.map(([k, rotulo]) => (
            <Campo key={k} rotulo={rotulo} id={k}>
              <input id={k} type="datetime-local" required disabled={bloq} className={classeInput}
                value={f.datas[k]} onChange={(e) => set("datas", { ...f.datas, [k]: e.target.value })} />
            </Campo>
          ))}
        </div>
      </Cartao>

      <Cartao titulo="Cursos autorizados">
        <div className="space-y-2">
          {f.cursos.map((c, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <input aria-label={`Código do curso ${i + 1}`} placeholder="Código (ex.: MAT)" disabled={bloq}
                className={`${classeInput} max-w-[10rem]`} value={c.codigo_curso}
                onChange={(e) => set("cursos", f.cursos.map((x, j) => (j === i ? { ...x, codigo_curso: e.target.value } : x)))} />
              <input aria-label={`Nome do curso ${i + 1}`} placeholder="Nome do curso" disabled={bloq}
                className={`${classeInput} flex-1`} value={c.nome_curso}
                onChange={(e) => set("cursos", f.cursos.map((x, j) => (j === i ? { ...x, nome_curso: e.target.value } : x)))} />
              {!bloq && (
                <Botao type="button" variante="secundario" aria-label={`Remover curso ${i + 1}`}
                  onClick={() => set("cursos", f.cursos.filter((_, j) => j !== i))}>Remover</Botao>
              )}
            </div>
          ))}
          {!bloq && (
            <Botao type="button" variante="secundario"
              onClick={() => set("cursos", [...f.cursos, { codigo_curso: "", nome_curso: "" }])}>+ Adicionar curso</Botao>
          )}
        </div>
      </Cartao>

      <Cartao titulo="Documentos exigidos (PDF, até 10 MB cada)">
        <div className="space-y-2">
          {f.documentos.map((d, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <input aria-label={`Nome do documento ${i + 1}`} placeholder="Nome do documento" disabled={bloq}
                className={`${classeInput} flex-1`} value={d.nome}
                onChange={(e) => set("documentos", f.documentos.map((x, j) => (j === i ? { ...x, nome: e.target.value } : x)))} />
              <input aria-label={`Instruções do documento ${i + 1}`} placeholder="Instruções (opcional)" disabled={bloq}
                className={`${classeInput} flex-1`} value={d.descricao ?? ""}
                onChange={(e) => set("documentos", f.documentos.map((x, j) => (j === i ? { ...x, descricao: e.target.value } : x)))} />
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" disabled={bloq} checked={d.obrigatorio}
                  onChange={(e) => set("documentos", f.documentos.map((x, j) => (j === i ? { ...x, obrigatorio: e.target.checked } : x)))} />
                Obrigatório
              </label>
              {!bloq && (
                <Botao type="button" variante="secundario" aria-label={`Remover documento ${i + 1}`}
                  onClick={() => set("documentos", f.documentos.filter((_, j) => j !== i))}>Remover</Botao>
              )}
            </div>
          ))}
          {!bloq && (
            <Botao type="button" variante="secundario"
              onClick={() => set("documentos", [...f.documentos, { nome: "", descricao: "", obrigatorio: true }])}>
              + Adicionar documento
            </Botao>
          )}
        </div>
      </Cartao>

      <ErroApiBox erro={salvar.error} />
      <div className="flex gap-2">
        <Botao type="submit" disabled={salvar.isPending}>{salvar.isPending ? "Salvando…" : "Salvar"}</Botao>
        {!editando && <span className="self-center text-sm text-slate-500">O edital será salvo como rascunho.</span>}
      </div>
    </form>
  );
}
