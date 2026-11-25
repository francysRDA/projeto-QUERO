import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { listarEditais, type Categoria } from "../../api/editais";
import { Cartao, ErroApiBox, NOME_CATEGORIA, classeInput, fmtDataHora, fmtMoeda } from "../../components/ui";

/** INS-01: vitrine com filtros por curso, categoria, modalidade e faixa de valor. */
export function Vitrine() {
  const [categoria, setCategoria] = useState<Categoria | "">("");
  const [curso, setCurso] = useState("");
  const [busca, setBusca] = useState("");
  const [valorMin, setValorMin] = useState("");

  const consulta = useQuery({
    queryKey: ["editais", "vitrine", categoria, curso, busca, valorMin],
    queryFn: () =>
      listarEditais({
        categoria: categoria || undefined,
        curso: curso || undefined,
        busca: busca || undefined,
        valor_min: valorMin || undefined,
      }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Editais com inscrições abertas</h1>

      <form role="search" aria-label="Filtrar editais" onSubmit={(e) => e.preventDefault()}
        className="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">
          <span className="font-medium">Busca</span>
          <input type="search" className={`${classeInput} mt-1`} placeholder="Título ou descrição"
            value={busca} onChange={(e) => setBusca(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="font-medium">Categoria</span>
          <select className={`${classeInput} mt-1`} value={categoria} onChange={(e) => setCategoria(e.target.value as Categoria | "")}>
            <option value="">Todas</option>
            {Object.entries(NOME_CATEGORIA).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="font-medium">Curso</span>
          <input className={`${classeInput} mt-1`} placeholder="Nome ou código" value={curso}
            onChange={(e) => setCurso(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="font-medium">Bolsa mínima (R$)</span>
          <input type="number" min="0" step="50" className={`${classeInput} mt-1`} value={valorMin}
            onChange={(e) => setValorMin(e.target.value)} />
        </label>
      </form>

      <ErroApiBox erro={consulta.error} />
      {consulta.isLoading && <p role="status">Carregando…</p>}
      {consulta.data && (
        <p className="text-sm text-slate-600" aria-live="polite">{consulta.data.total} edital(is) encontrado(s).</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {consulta.data?.itens.map((e) => (
          <Cartao key={e.id}>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-lg font-semibold">
                <Link to={`/editais/${e.id}`} className="text-marca-700 hover:underline">{e.titulo}</Link>
              </h2>
              <span className="rounded bg-marca-50 px-2 py-0.5 text-xs text-marca-800">{NOME_CATEGORIA[e.categoria]}</span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-sm">
              <dt className="text-slate-500">Bolsa</dt><dd>{fmtMoeda(e.valor_bolsa)}</dd>
              <dt className="text-slate-500">Vagas</dt><dd>{e.vagas}</dd>
              <dt className="text-slate-500">Carga horária</dt><dd>{e.carga_horaria_semanal} h/semana</dd>
              <dt className="text-slate-500">CR mínimo</dt><dd>{Number(e.cr_minimo).toFixed(2)}</dd>
              <dt className="text-slate-500">Inscrições até</dt><dd className="font-medium">{fmtDataHora(e.data_fim_inscricao)}</dd>
            </dl>
          </Cartao>
        ))}
      </div>
    </div>
  );
}
