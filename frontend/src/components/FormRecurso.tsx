import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { problemaNoArquivo, type Inscricao } from "../api/inscricoes";
import { NOME_STATUS_RECURSO, TAMANHO_MAX_RECURSO, interporRecurso } from "../api/recursos";
import { Botao, ErroApiBox, classeInput, fmtDataHora } from "./ui";

/** AVA-03: o estudante vê o próprio recurso e, dentro da janela, pode interpor um único recurso. */
export function RecursoDoEstudante({ inscricao: i }: { inscricao: Inscricao }) {
  const qc = useQueryClient();
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState("");
  const [anexo, setAnexo] = useState<File | null>(null);
  const mut = useMutation({
    mutationFn: () => interporRecurso(i.id, texto, anexo),
    onSuccess: () => {
      setAberto(false);
      qc.invalidateQueries({ queryKey: ["inscricoes"] });
    },
  });

  if (i.recurso) {
    const r = i.recurso;
    return (
      <div className="mt-3 rounded border border-slate-300 bg-white p-3 text-sm">
        <p className="font-semibold">Seu recurso — {NOME_STATUS_RECURSO[r.status as keyof typeof NOME_STATUS_RECURSO] ?? r.status}</p>
        <p className="text-xs text-slate-500">Enviado em {fmtDataHora(r.criado_em)}</p>
        <p className="mt-1 whitespace-pre-line text-slate-700">{r.texto}</p>
        {r.justificativa_decisao && (
          <p className="mt-2"><strong>Decisão da comissão:</strong> {r.justificativa_decisao}</p>
        )}
      </div>
    );
  }
  if (!i.pode_recorrer) return null; // AVA-03: fora da janela o botão não é exibido

  const problemaAnexo = anexo ? problemaNoArquivo(anexo) : null;
  if (!aberto) {
    return (
      <div className="mt-3">
        <Botao variante="secundario" onClick={() => setAberto(true)}>Interpor recurso</Botao>
      </div>
    );
  }
  return (
    <form className="mt-3 space-y-3 rounded border border-marca-100 bg-marca-50 p-3" onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
      <p className="text-sm">
        Você pode interpor <strong>um único recurso</strong> contra o resultado preliminar (RN-10). Ele será julgado por um
        membro da comissão diferente de quem emitiu o parecer.
      </p>
      <label className="block text-sm">
        <span className="font-medium">Fundamentação</span>
        <textarea rows={6} maxLength={TAMANHO_MAX_RECURSO} className={`${classeInput} mt-1`} value={texto}
          onChange={(e) => setTexto(e.target.value)} aria-describedby={`contador-${i.id}`} />
        <span id={`contador-${i.id}`} className="text-xs text-slate-500">{texto.length}/{TAMANHO_MAX_RECURSO} caracteres</span>
      </label>
      <label className="block text-sm">
        <span className="font-medium">Anexo (opcional, PDF até 10 MB)</span>
        <input type="file" accept="application/pdf,.pdf" className="mt-1 block text-sm"
          onChange={(e) => setAnexo(e.target.files?.[0] ?? null)} />
        {problemaAnexo && <span className="text-xs text-red-800">{problemaAnexo}</span>}
      </label>
      <ErroApiBox erro={mut.error} />
      <div className="flex gap-2">
        <Botao type="submit" disabled={mut.isPending || !texto.trim() || !!problemaAnexo}>Enviar recurso</Botao>
        <Botao type="button" variante="secundario" onClick={() => setAberto(false)}>Cancelar</Botao>
      </div>
    </form>
  );
}
