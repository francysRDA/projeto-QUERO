import type { Documento } from "../api/editais";
import { problemaNoArquivo } from "../api/inscricoes";

const fmtTamanho = (b: number) => (b < 1024 * 1024 ? `${Math.ceil(b / 1024)} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`);

/** Um campo de arquivo por documento exigido do edital. */
export function CamposDocumentos({
  documentos,
  arquivos,
  aoMudar,
  todosOpcionais = false,
}: {
  documentos: Documento[];
  arquivos: Record<number, File>;
  aoMudar: (a: Record<number, File>) => void;
  todosOpcionais?: boolean;
}) {
  return (
    <ul className="space-y-3">
      {documentos.map((d) => {
        const id = d.id!;
        const arquivo = arquivos[id];
        const problema = arquivo ? problemaNoArquivo(arquivo) : null;
        const campoId = `doc-${id}`;
        const obrigatorio = d.obrigatorio && !todosOpcionais;
        return (
          <li key={id} className="rounded border border-slate-200 p-3">
            <label htmlFor={campoId} className="block text-sm font-medium">
              {d.nome} {obrigatorio ? <span className="text-red-700">*</span> : <span className="text-slate-500">(opcional)</span>}
            </label>
            {d.descricao && <p className="text-xs text-slate-600">{d.descricao}</p>}
            <input
              id={campoId}
              type="file"
              accept="application/pdf,.pdf"
              aria-invalid={problema ? true : undefined}
              aria-describedby={problema ? `${campoId}-erro` : undefined}
              className="mt-2 block w-full text-sm file:mr-3 file:rounded file:border-0 file:bg-marca-50 file:px-3 file:py-1.5 file:text-marca-800"
              onChange={(e) => {
                const f = e.target.files?.[0];
                const novo = { ...arquivos };
                if (f) novo[id] = f;
                else delete novo[id];
                aoMudar(novo);
              }}
            />
            {arquivo && !problema && <p className="mt-1 text-xs text-green-800">{arquivo.name} · {fmtTamanho(arquivo.size)}</p>}
            {problema && (
              <p id={`${campoId}-erro`} className="mt-1 text-xs text-red-800">{problema}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function arquivosValidos(documentos: Documento[], arquivos: Record<number, File>, exigirObrigatorios: boolean) {
  const algumInvalido = Object.values(arquivos).some((f) => problemaNoArquivo(f));
  const faltando = exigirObrigatorios && documentos.some((d) => d.obrigatorio && !arquivos[d.id!]);
  return !algumInvalido && !faltando && Object.keys(arquivos).length > 0;
}
