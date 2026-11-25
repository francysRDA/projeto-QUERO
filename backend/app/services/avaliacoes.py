"""Avaliação de mérito e resultado preliminar (UC-07: AVA-01, AVA-02; RN-06…09, RN-12)."""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.auditoria import registrar, snapshot
from app.core.errors import Conflito, NaoEncontrado, Proibido, RegraViolada
from app.core.relogio import agora
from app.domain.classificacao import Candidato, Posicao, Situacao, classificar
from app.domain.estados import (
    MAQUINA_AVALIACAO,
    MAQUINA_EDITAL,
    NOVO,
    EventoAvaliacao,
    EventoEdital,
    StatusAvaliacao,
    StatusEdital,
    StatusInscricao,
)
from app.domain.perfis import Perfil
from app.models import Arquivo, Avaliacao, Classificacao, ComissaoEdital, Edital, Impedimento, Inscricao, Usuario
from app.schemas.avaliacao import (
    AvaliacaoEntrada,
    AvaliacaoSaida,
    FilaSaida,
    ItemClassificacao,
    ItemFila,
    Progresso,
)
from app.schemas.inscricao import ArquivoSaida
from app.services import editais as svc_editais
from app.services.notificacoes import notificar

AVALIACAO_FINALIZADA = {StatusAvaliacao.CONFIRMADA, StatusAvaliacao.RETIFICADA}
STATUS_RESULTADO_PUBLICADO = {
    StatusEdital.RESULTADO_PRELIMINAR,
    StatusEdital.EM_RECURSO,
    StatusEdital.EM_HOMOLOGACAO_FINAL,
    StatusEdital.ENCERRADO,
}


# --- Acesso ------------------------------------------------------------------------------------------
def _exigir_membro(db: Session, edital_id: int, avaliador: Usuario) -> Edital:
    """RN-07: avaliador não designado não enxerga o edital (404, sem revelar existência)."""
    edital = svc_editais.carregar(db, edital_id)
    if not svc_editais.eh_membro_comissao(db, edital_id, avaliador.id):
        raise NaoEncontrado("Edital não encontrado entre as suas comissões.")
    return edital


def _homologadas(db: Session, edital_id: int) -> list[Inscricao]:
    """RN-06: apenas inscrições HOMOLOGADAS entram na avaliação de mérito."""
    return list(db.scalars(
        select(Inscricao)
        .where(Inscricao.edital_id == edital_id, Inscricao.status == StatusInscricao.HOMOLOGADA)
        .order_by(Inscricao.data_submissao_original)
    ))


# --- Fila (AVA-01) -------------------------------------------------------------------------------------
def progresso(db: Session, edital: Edital) -> Progresso:
    homologadas = _homologadas(db, edital.id)
    ids = [i.id for i in homologadas]
    avaliacoes = {a.inscricao_id: a for a in db.scalars(select(Avaliacao).where(Avaliacao.inscricao_id.in_(ids)))}
    membros = set(db.scalars(select(ComissaoEdital.avaliador_id).where(ComissaoEdital.edital_id == edital.id)))
    impedidos: dict[int, set[int]] = {}
    for imp in db.scalars(select(Impedimento).where(Impedimento.inscricao_id.in_(ids))):
        impedidos.setdefault(imp.inscricao_id, set()).add(imp.avaliador_id)

    confirmadas = sum(1 for a in avaliacoes.values() if a.status in AVALIACAO_FINALIZADA)
    rascunhos = sum(1 for a in avaliacoes.values() if a.status == StatusAvaliacao.RASCUNHO)
    sem_avaliador = [
        i.protocolo for i in homologadas
        if i.id not in avaliacoes and membros and membros <= impedidos.get(i.id, set())
    ]
    return Progresso(
        homologadas=len(homologadas),
        confirmadas=confirmadas,
        em_rascunho=rascunhos,
        nao_iniciadas=len(homologadas) - len(avaliacoes),
        sem_avaliador_disponivel=sem_avaliador,
        pode_publicar=edital.status == StatusEdital.EM_AVALIACAO and confirmadas == len(homologadas),
    )


def fila(db: Session, edital_id: int, avaliador: Usuario) -> FilaSaida:
    edital = _exigir_membro(db, edital_id, avaliador)
    homologadas = _homologadas(db, edital.id) if edital.status != StatusEdital.INSCRICOES_ENCERRADAS else []
    ids = [i.id for i in homologadas]
    avaliacoes = {a.inscricao_id: a for a in db.scalars(select(Avaliacao).where(Avaliacao.inscricao_id.in_(ids)))}
    meus_impedimentos = set(db.scalars(
        select(Impedimento.inscricao_id).where(Impedimento.avaliador_id == avaliador.id, Impedimento.inscricao_id.in_(ids))
    ))
    arquivos: dict[int, list[Arquivo]] = {}
    for a in db.scalars(select(Arquivo).where(Arquivo.inscricao_id.in_(ids), Arquivo.ativo.is_(True)).order_by(Arquivo.id)):
        arquivos.setdefault(a.inscricao_id, []).append(a)
    nomes = dict(db.execute(
        select(Usuario.id, Usuario.nome).where(Usuario.id.in_([i.estudante_id for i in homologadas]))
    ).all())

    itens = []
    for i in homologadas:
        av = avaliacoes.get(i.id)
        if i.id in meus_impedimentos:
            continue  # UC-07 E1: redirecionada aos demais membros
        if av is not None and av.avaliador_id != avaliador.id:
            continue  # já assumida por outro membro da comissão
        itens.append(ItemFila(
            inscricao_id=i.id, protocolo=i.protocolo, estudante_nome=nomes[i.estudante_id],
            curso_congelado=i.curso_congelado, cr_congelado=i.cr_congelado,
            data_submissao_original=i.data_submissao_original,
            arquivos=[ArquivoSaida.model_validate(a) for a in arquivos.get(i.id, [])],
            avaliacao=AvaliacaoSaida.model_validate(av) if av else None,
        ))
    return FilaSaida(
        edital_id=edital.id, edital_titulo=edital.titulo, edital_status=edital.status,
        pode_avaliar=edital.status == StatusEdital.EM_AVALIACAO, itens=itens, progresso=progresso(db, edital),
    )


# --- Lançamento de nota e parecer (AVA-01, RN-07, RN-08, §7.3) -----------------------------------------
def _carregar_para_avaliar(db: Session, inscricao_id: int, avaliador: Usuario) -> tuple[Inscricao, Edital]:
    insc = db.scalar(select(Inscricao).where(Inscricao.id == inscricao_id).with_for_update())
    if insc is None or not svc_editais.eh_membro_comissao(db, insc.edital_id, avaliador.id):
        raise NaoEncontrado("Inscrição não encontrada.")
    edital = db.get(Edital, insc.edital_id)
    if edital.status != StatusEdital.EM_AVALIACAO:
        raise Conflito("O edital não está em fase de avaliação.")
    if insc.status != StatusInscricao.HOMOLOGADA:
        raise Conflito("Apenas inscrições homologadas podem ser avaliadas (RN-06).")
    if db.scalar(select(Impedimento.id).where(Impedimento.inscricao_id == insc.id,
                                              Impedimento.avaliador_id == avaliador.id)):
        raise Conflito("Você declarou impedimento para esta inscrição (RN-07).")
    return insc, edital


def _validar_completa(dados: AvaliacaoEntrada) -> None:
    problemas = []
    if dados.nota_merito is None:
        problemas.append("Informe a nota de mérito (0,00 a 10,00).")
    if dados.parecer is None:
        problemas.append("Informe o parecer (Deferido ou Indeferido).")
    if dados.parecer == "INDEFERIDO" and not dados.justificativa:
        problemas.append("O parecer Indeferido exige justificativa técnica (RN-08).")
    if not dados.declaracao_sem_impedimento:
        problemas.append("Marque a declaração de ausência de impedimento/suspeição (RN-07).")
    if problemas:
        raise RegraViolada("Avaliação incompleta.", detalhes=problemas)


def salvar(db: Session, inscricao_id: int, dados: AvaliacaoEntrada, avaliador: Usuario, ip: str | None) -> Avaliacao:
    insc, _ = _carregar_para_avaliar(db, inscricao_id, avaliador)
    av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == insc.id).with_for_update())
    if av is not None and av.avaliador_id != avaliador.id:
        raise Conflito("Esta inscrição já está sendo avaliada por outro membro da comissão.")

    estado = av.status if av else NOVO
    antes = snapshot(av) if av else None

    if dados.acao == "RASCUNHO":
        evento = [EventoAvaliacao.SALVAR_RASCUNHO]
    elif dados.acao == "CONFIRMAR":
        _validar_completa(dados)
        # Confirmar direto (sem rascunho prévio) percorre (Nova) → RASCUNHO → CONFIRMADA, como em §7.3.
        evento = [EventoAvaliacao.SALVAR_RASCUNHO, EventoAvaliacao.CONFIRMAR] if estado == NOVO else [EventoAvaliacao.CONFIRMAR]
    else:  # RETIFICAR
        _validar_completa(dados)
        if not dados.justificativa_retificacao or len(dados.justificativa_retificacao) < 10:
            raise RegraViolada("A retificação exige motivo (mínimo 10 caracteres).")
        evento = [EventoAvaliacao.RETIFICAR]

    for e in evento:
        estado = MAQUINA_AVALIACAO.proximo(estado, e)  # 409 em transição inválida

    if av is None:
        av = Avaliacao(inscricao_id=insc.id, avaliador_id=avaliador.id)
        db.add(av)
    av.nota_merito = dados.nota_merito
    av.parecer = dados.parecer
    av.justificativa = dados.justificativa or None
    av.declaracao_sem_impedimento = dados.declaracao_sem_impedimento
    if dados.acao == "RETIFICAR":
        av.justificativa_retificacao = dados.justificativa_retificacao
    av.status = estado
    av.atualizado_em = agora(db)
    db.flush()
    registrar(db, usuario_id=avaliador.id, acao=f"AVALIACAO_{dados.acao}", entidade="avaliacao",
              entidade_id=av.id, antes=antes, depois=snapshot(av), ip=ip)
    db.commit()
    return av


def declarar_impedimento(db: Session, inscricao_id: int, motivo: str, avaliador: Usuario, ip: str | None) -> None:
    """UC-07 E1: a inscrição sai da fila deste avaliador e fica disponível aos demais membros."""
    insc, edital = _carregar_para_avaliar(db, inscricao_id, avaliador)
    av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == insc.id))
    if av is not None and av.avaliador_id == avaliador.id:
        if av.status in AVALIACAO_FINALIZADA:
            raise Conflito("Avaliação já confirmada: para corrigir, retifique-a com justificativa.")
        db.delete(av)  # descarta o rascunho
    elif av is not None:
        raise Conflito("Esta inscrição já está sendo avaliada por outro membro da comissão.")
    imp = Impedimento(inscricao_id=insc.id, avaliador_id=avaliador.id, motivo=motivo)
    db.add(imp)
    db.flush()
    registrar(db, usuario_id=avaliador.id, acao="AVALIACAO_IMPEDIMENTO", entidade="inscricao",
              entidade_id=insc.id, depois={"avaliador_id": avaliador.id, "motivo": motivo}, ip=ip)

    # Se ninguém mais da comissão puder avaliar, a Pró-Reitoria precisa designar outro membro.
    membros = set(db.scalars(select(ComissaoEdital.avaliador_id).where(ComissaoEdital.edital_id == edital.id)))
    impedidos = set(db.scalars(select(Impedimento.avaliador_id).where(Impedimento.inscricao_id == insc.id)))
    if membros <= impedidos:
        for pr_id in db.scalars(select(Usuario.id).where(Usuario.perfil == Perfil.PRO_REITOR, Usuario.ativo.is_(True))):
            notificar(
                db, usuario_id=pr_id, tipo="COMISSAO_SEM_AVALIADOR",
                titulo=f"Inscrição {insc.protocolo} sem avaliador disponível",
                mensagem=(f"Todos os membros da comissão do edital \"{edital.titulo}\" declararam impedimento para "
                          f"a inscrição {insc.protocolo}. Designe outro avaliador."),
            )
    db.commit()


# --- Classificação (AVA-02, RN-09, RN-12) ------------------------------------------------------------------
def _candidatos(db: Session, edital: Edital) -> list[Candidato]:
    linhas = db.execute(
        select(Inscricao, Avaliacao)
        .join(Avaliacao, Avaliacao.inscricao_id == Inscricao.id)
        .where(Inscricao.edital_id == edital.id, Inscricao.status == StatusInscricao.HOMOLOGADA,
               Avaliacao.status.in_([str(s) for s in AVALIACAO_FINALIZADA]))
    ).all()
    return [
        Candidato(inscricao_id=i.id, nota=a.nota_merito, deferido=a.parecer == "DEFERIDO",
                  cr=i.cr_congelado, submissao_original=i.data_submissao_original)
        for i, a in linhas
    ]


def calcular(db: Session, edital: Edital) -> list[Posicao]:
    return classificar(_candidatos(db, edital), edital.vagas, edital.criterios_desempate)


def gravar_classificacao(db: Session, edital: Edital, fase: str) -> list[Posicao]:
    posicoes = calcular(db, edital)
    db.execute(delete(Classificacao).where(Classificacao.edital_id == edital.id, Classificacao.fase == fase))
    momento = agora(db)
    db.add_all(
        Classificacao(edital_id=edital.id, inscricao_id=p.inscricao_id, fase=fase, posicao=p.posicao,
                      nota=p.nota, situacao=p.situacao, calculado_em=momento)
        for p in posicoes
    )
    db.flush()
    return posicoes


def publicar_preliminar(db: Session, edital_id: int, usuario: Usuario, ip: str | None) -> Edital:
    edital = svc_editais.carregar(db, edital_id, bloquear=True)
    if usuario.perfil == Perfil.AVALIADOR and not svc_editais.eh_membro_comissao(db, edital.id, usuario.id):
        raise NaoEncontrado("Edital não encontrado entre as suas comissões.")
    if usuario.perfil == Perfil.ESTUDANTE:
        raise Proibido("Seu perfil não tem permissão para esta operação.")
    if not MAQUINA_EDITAL.permitido(edital.status, EventoEdital.PUBLICAR_PRELIMINAR):
        MAQUINA_EDITAL.proximo(edital.status, EventoEdital.PUBLICAR_PRELIMINAR)  # 409 padronizado

    prog = progresso(db, edital)
    if not prog.pode_publicar:
        pendentes = [
            i.protocolo for i in _homologadas(db, edital.id)
            if not db.scalar(select(Avaliacao.id).where(
                Avaliacao.inscricao_id == i.id, Avaliacao.status.in_([str(s) for s in AVALIACAO_FINALIZADA])))
        ]
        raise Conflito("Ainda há inscrições homologadas sem avaliação confirmada (AVA-02).",
                       detalhes=[f"Pendente: {p}" for p in pendentes])

    # Ao republicar após "devolver para ajustes", resultados anteriores são substituídos.
    db.execute(delete(Classificacao).where(Classificacao.edital_id == edital.id,
                                           Classificacao.fase.in_(["PRELIMINAR", "POS_RECURSO"])))
    posicoes = gravar_classificacao(db, edital, "PRELIMINAR")
    svc_editais.transicionar(db, edital, EventoEdital.PUBLICAR_PRELIMINAR, usuario_id=usuario.id, ip=ip,
                             extra_depois={"classificacao": [p.__dict__ for p in posicoes]})
    # RN-10: a janela de recurso abre automaticamente na publicação.
    edital.data_fim_recurso = agora(db) + timedelta(hours=edital.prazo_recurso_horas)
    svc_editais.transicionar(db, edital, EventoEdital.ABRIR_RECURSO, usuario_id=None, ip=ip)

    _notificar_resultado(db, edital, posicoes)
    db.commit()
    return edital


def _notificar_resultado(db: Session, edital: Edital, posicoes: list[Posicao]) -> None:
    por_inscricao = {p.inscricao_id: p for p in posicoes}
    fim = edital.data_fim_recurso.astimezone(agora(db).tzinfo).strftime("%d/%m/%Y %H:%M")
    for insc in db.scalars(select(Inscricao).where(Inscricao.edital_id == edital.id,
                                                   Inscricao.status != StatusInscricao.DESISTENTE)):
        p = por_inscricao.get(insc.id)
        if p is None:
            texto = "Sua inscrição não foi homologada e, por isso, não participou da avaliação de mérito."
        elif p.situacao == Situacao.NAO_CLASSIFICADO:
            texto = f"Nota de mérito: {p.nota:.2f}. Parecer: INDEFERIDO (não classificado)."
        else:
            texto = f"Nota de mérito: {p.nota:.2f}. Posição: {p.posicao}º — {p.situacao.lower()}."
        notificar(
            db, usuario_id=insc.estudante_id, tipo="RESULTADO_PRELIMINAR",
            titulo=f"Resultado preliminar publicado: {edital.titulo}",
            mensagem=f"{texto}\n\nVocê pode interpor recurso até {fim} (horário de Brasília).",
        )


def classificacao_atual(db: Session, edital: Edital) -> tuple[str, list[Classificacao]]:
    for fase in ("FINAL", "POS_RECURSO", "PRELIMINAR"):
        linhas = list(db.scalars(select(Classificacao).where(Classificacao.edital_id == edital.id,
                                                             Classificacao.fase == fase)))
        if linhas:
            return fase, linhas
    return "", []


def montar_itens(db: Session, posicoes: list[tuple[int, int | None, object, str]]) -> list[ItemClassificacao]:
    """posicoes: (inscricao_id, posicao, nota, situacao)."""
    ids = [p[0] for p in posicoes]
    inscs = {i.id: i for i in db.scalars(select(Inscricao).where(Inscricao.id.in_(ids)))}
    avs = {a.inscricao_id: a for a in db.scalars(select(Avaliacao).where(Avaliacao.inscricao_id.in_(ids)))}
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome).where(
        Usuario.id.in_([i.estudante_id for i in inscs.values()]))).all())
    itens = [
        ItemClassificacao(
            posicao=pos, inscricao_id=iid, protocolo=inscs[iid].protocolo, estudante_nome=nomes[inscs[iid].estudante_id],
            nota=nota, parecer=avs[iid].parecer if iid in avs else None, cr_congelado=inscs[iid].cr_congelado,
            data_submissao_original=inscs[iid].data_submissao_original, situacao=sit,
        )
        for iid, pos, nota, sit in posicoes
    ]
    return sorted(itens, key=lambda x: (x.posicao is None, x.posicao or 0, -(x.nota or 0)))
