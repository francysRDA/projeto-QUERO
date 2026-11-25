import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { obterEdital } from "../../api/editais";
import {
  baixarComprovante,
  baixarDocumento,
  desistir,
  minhasInscricoes,
  retificar,
  type Inscricao,
  type StatusInscricao,
} from "../../api/inscricoes";
import { CamposDocumentos, arquivosValidos } from "../../components/CamposDocumentos";
import { Botao, Cartao, ErroApiBox, StatusBadge, fmtDataHora } from "../../components/ui";

const SITUACAO: Record<StatusInscricao, { rotulo: string; cor: string }> = {
  HOMOLOGADA: { rotulo: "Homologada", cor: "bg-green-50 text-green-800 border-green-300" },
  INDEFERIDA: { rotulo: "Indeferida", cor: "bg-red-50 text-red-800 border-red-300" },
  PENDENTE_VALIDACAO_VINCULO: { rotulo: "Aguardando validação do vínculo", cor: "bg-amber-50 text-amber-900 border-amber-300" },
  DESISTENTE: { rotulo: "Desistente", cor: "bg-slate-100 text-slate-700 border-slate-300" },
};

/** INS-06: acompanhamento das próprias inscrições. */
export function MinhasInscricoes() {
  const consulta = useQuery({ queryKey: ["inscricoes", "me"], queryFn: minhasInscricoes });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Minhas inscrições</h1>
      <ErroApiBox erro={consulta.error} />
      {consulta.isLoading && <p role="status">Carregando…</p>}
      {consulta.data?.length === 0 && (
        <Cartao>
          <p className="text-sm text-slate-600">
            Você ainda não se inscreveu em nenhum edital. <Link to="/editais" className="text-marca-700 underline">Ver editais abertos</Link>.
          </p>
        </Cartao>
      )}
      {consulta.data?.map((i) => <CartaoInscricao key={i.id} inscricao={i} />)}
    </div>
  );
}

function CartaoInscricao({ inscricao: i }: { inscricao: Inscricao }) {
  const qc = useQueryClient();
  const [modo, setModo] = useState<"ver" | "retificar" | "desistir">("ver");
  const [arquivos, setArquivos] = useState<Record<number, File>>({});
  const edital = useQuery({ queryKey: ["edital", i.edital.id], queryFn: () => obterEdital(i.edital.id), enabled: modo === "retificar" });
  const atualizar = () => {
    setModo("ver");
    setArquivos({});
    qc.invalidateQueries({ queryKey: ["inscricoes"] });
  };
  const ret = useMutation({ mutationFn: () => retificar(i.id, arquivos), onSuccess: atualizar });
  const des = useMutation({ mutationFn: () => desistir(i.id), onSuccess: atualizar });
  const baixar = useMutation({ mutationFn: (f: () => Promise<void>) => f() });

  const nomeDoc = (docId: number | null) => edital.data?.documentos.find((d) => d.id === docId)?.nome;
  const vigentes = i.arquivos.filter((a) => a.ativo);
  const anteriores = i.arquivos.filter((a) => !a.ativo);
  const situacao = SITUACAO[i.status];

  return (
    <Cartao>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{i.edital.titulo}</h2>
          <p className="text-sm text-slate-600">
            Protocolo <strong className="font-mono">{i.protocolo}</strong> · enviada em {fmtDataHora(i.data_submissao_original)}
            {i.data_ultima_retificacao && <> · retificada em {fmtDataHora(i.data_ultima_retificacao)}</>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`rounded border px-2 py-0.5 text-xs font-medium ${situacao.cor}`}>{situacao.rotulo}</span>
          <span className="text-xs text-slate-500">Edital: <StatusBadge status={i.edital.status} /></span>
        </div>
      </div>

      {i.status === "PENDENTE_VALIDACAO_VINCULO" && (
        <p className="mt-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          O Sistema Acadêmico estava indisponível no envio. Sua inscrição está registrada e o vínculo será validado
          automaticamente; você receberá uma notificação com o resultado (INT-01).
        </p>
      )}
      {i.curso_congelado && (
        <p className="mt-2 text-xs text-slate-600">
          Dados acadêmicos registrados na inscrição: {i.curso_congelado} · CR {Number(i.cr_congelado).toFixed(2)} ·
          vínculo {i.vinculo_ativo_congelado ? "ativo" : "inativo"}
        </p>
      )}
      {i.motivos_indeferimento && i.motivos_indeferimento.length > 0 && (
        <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          <p className="font-semibold">Motivos do indeferimento (RN-05):</p>
          <ul className="list-disc pl-5">{i.motivos_indeferimento.map((m) => <li key={m}>{m}</li>)}</ul>
          {i.pode_retificar && <p className="mt-1">Você pode corrigir enviando novos documentos até {fmtDataHora(i.edital.data_fim_inscricao)}.</p>}
        </div>
      )}

      <h3 className="mt-4 text-sm font-semibold">Documentos enviados</h3>
      <ul className="mt-1 divide-y text-sm">
        {vigentes.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span>{a.nome_original} <span className="text-xs text-slate-500">(versão {a.versao})</span></span>
            <button className="text-marca-700 underline" onClick={() => baixar.mutate(() => baixarDocumento(a))}>Baixar</button>
          </li>
        ))}
      </ul>
      {anteriores.length > 0 && (
        <details className="mt-1 text-sm">
          <summary className="cursor-pointer text-slate-600">Versões anteriores ({anteriores.length})</summary>
          <ul className="mt-1 space-y-1 pl-4">
            {anteriores.map((a) => (
              <li key={a.id}>
                {a.nome_original} (versão {a.versao}, {fmtDataHora(a.enviado_em)}){" "}
                <button className="text-marca-700 underline" onClick={() => baixar.mutate(() => baixarDocumento(a))}>Baixar</button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
        <Botao variante="secundario" onClick={() => baixar.mutate(() => baixarComprovante(i))}>Baixar comprovante</Botao>
        {i.pode_retificar && modo === "ver" && <Botao variante="secundario" onClick={() => setModo("retificar")}>Substituir documentos</Botao>}
        {i.pode_desistir && modo === "ver" && <Botao variante="secundario" onClick={() => setModo("desistir")}>Desistir</Botao>}
      </div>
      <div className="mt-2"><ErroApiBox erro={baixar.error} /></div>

      {modo === "retificar" && (
        <div className="mt-3 space-y-3 rounded border border-marca-100 bg-marca-50 p-3">
          <p className="text-sm">
            Selecione apenas os documentos que deseja substituir. O protocolo, a data original de envio e seus dados
            acadêmicos são mantidos (INS-05).
          </p>
          {edital.data && (
            <CamposDocumentos documentos={edital.data.documentos} arquivos={arquivos} aoMudar={setArquivos} todosOpcionais />
          )}
          {vigentes.length > 0 && edital.data && (
            <p className="text-xs text-slate-600">Atuais: {vigentes.map((a) => `${nomeDoc(a.documento_exigido_id)} (v${a.versao})`).join(", ")}</p>
          )}
          <ErroApiBox erro={ret.error} />
          <div className="flex gap-2">
            <Botao disabled={ret.isPending || !edital.data || !arquivosValidos(edital.data.documentos, arquivos, false)} onClick={() => ret.mutate()}>
              {ret.isPending ? "Enviando…" : "Enviar substituição"}
            </Botao>
            <Botao variante="secundario" onClick={() => setModo("ver")}>Cancelar</Botao>
          </div>
        </div>
      )}

      {modo === "desistir" && (
        <div role="alertdialog" aria-labelledby={`desistir-${i.id}`} className="mt-3 space-y-2 rounded border border-red-200 bg-red-50 p-3">
          <p id={`desistir-${i.id}`} className="text-sm text-red-900">
            <strong>Confirma a desistência?</strong> Ela é definitiva: você sairá da avaliação e não poderá se inscrever
            novamente neste edital.
          </p>
          <ErroApiBox erro={des.error} />
          <div className="flex gap-2">
            <Botao variante="perigo" disabled={des.isPending} onClick={() => des.mutate()}>Confirmar desistência</Botao>
            <Botao variante="secundario" onClick={() => setModo("ver")}>Voltar</Botao>
          </div>
        </div>
      )}
    </Cartao>
  );
}
