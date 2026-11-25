"""Homologação formal da inscrição (UC-04: INS-03, INT-01, RN-02, RN-05).

Gateway AND (§7.5): a consulta ao Sistema Acadêmico roda em paralelo ao recebimento dos PDFs
(ver `services.inscricoes.submeter`); aqui os dois ramos se encontram e a decisão é tomada:
  HOMOLOGADA  XOR  INDEFERIDA (com todos os motivos)  XOR  PENDENTE_VALIDACAO_VINCULO.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auditoria import registrar, snapshot
from app.core.errors import Conflito, NaoEncontrado
from app.core.relogio import agora
from app.domain.elegibilidade import motivos_academicos
from app.domain.estados import MAQUINA_INSCRICAO, EventoInscricao, StatusEdital, StatusInscricao
from app.integrations import academico
from app.integrations.academico import AcademicoIndisponivel, DadosAcademicos, ServicoAcademico
from app.models import Arquivo, Edital, Inscricao, Usuario
from app.services.notificacoes import notificar

log = logging.getLogger("quero.homologacao")

MOTIVO_EXPIRADO = "Não foi possível validar o vínculo no Sistema Acadêmico até o início da avaliação."
MOTIVO_SEM_MATRICULA = "Seu cadastro não possui matrícula; procure a secretaria acadêmica."


# --- Verificações -------------------------------------------------------------------------------
def motivos_documentais(db: Session, edital: Edital, inscricao: Inscricao) -> list[str]:
    enviados = set(
        db.scalars(
            select(Arquivo.documento_exigido_id).where(
                Arquivo.inscricao_id == inscricao.id,
                Arquivo.ativo.is_(True),
                Arquivo.status_varredura == "VALIDADO",
            )
        )
    )
    return [
        f"Documento obrigatório ausente: {d.nome}."
        for d in edital.documentos
        if d.obrigatorio and d.id not in enviados
    ]


def congelar(insc: Inscricao, dados: DadosAcademicos | None) -> None:
    """RN-02: vínculo, curso e CR são congelados na inscrição e não mudam mais (nem na retificação)."""
    if dados is None:
        return
    insc.vinculo_ativo_congelado = dados.vinculo_ativo
    insc.codigo_curso_congelado = dados.codigo_curso
    insc.curso_congelado = dados.nome_curso
    insc.cr_congelado = dados.cr


def motivos_congelados(insc: Inscricao, edital: Edital) -> list[str]:
    return motivos_academicos(
        vinculo_ativo=insc.vinculo_ativo_congelado,
        codigo_curso=insc.codigo_curso_congelado,
        nome_curso=insc.curso_congelado,
        cr=insc.cr_congelado,
        cursos_autorizados={c.codigo_curso for c in edital.cursos},
        cr_minimo=edital.cr_minimo,
    )


def todos_os_motivos(db: Session, edital: Edital, insc: Inscricao) -> list[str]:
    return motivos_congelados(insc, edital) + motivos_documentais(db, edital, insc)


# --- Ramo acadêmico (executado em paralelo na submissão) -----------------------------------------
class ResultadoAcademico:
    """Resultado do ramo acadêmico do gateway AND."""

    def __init__(self, dados: DadosAcademicos | None = None, *, indisponivel: bool = False,
                 sem_matricula: bool = False):
        self.dados = dados
        self.indisponivel = indisponivel
        self.sem_matricula = sem_matricula


def consultar_ramo_academico(servico: ServicoAcademico, matricula: str | None) -> ResultadoAcademico:
    if not matricula:
        return ResultadoAcademico(sem_matricula=True)
    try:
        return ResultadoAcademico(academico.consultar(servico, matricula))
    except AcademicoIndisponivel:
        return ResultadoAcademico(indisponivel=True)


def decidir_submissao(db: Session, edital: Edital, insc: Inscricao, ramo: ResultadoAcademico) -> EventoInscricao:
    """Sincroniza os dois ramos e devolve o evento da máquina §7.2 (aplicado pelo chamador)."""
    if ramo.indisponivel:
        insc.motivos_indeferimento = None
        return EventoInscricao.SUBMETER_ACADEMICO_INDISPONIVEL
    congelar(insc, ramo.dados)
    motivos = [MOTIVO_SEM_MATRICULA] if ramo.sem_matricula else motivos_congelados(insc, edital)
    motivos += motivos_documentais(db, edital, insc)
    insc.motivos_indeferimento = motivos or None
    return EventoInscricao.SUBMETER_INELEGIVEL if motivos else EventoInscricao.SUBMETER_ELEGIVEL


# --- INT-01: reprocessamento das pendentes (worker) ---------------------------------------------------
def reprocessar_pendentes(db: Session, servico: ServicoAcademico) -> dict[str, int]:
    momento = agora(db)
    pendentes = db.scalars(
        select(Inscricao)
        .where(Inscricao.status == StatusInscricao.PENDENTE_VALIDACAO_VINCULO)
        .order_by(Inscricao.id)
        .with_for_update(skip_locked=True)
    ).all()
    contagem = {"homologadas": 0, "indeferidas": 0, "aguardando": 0}

    for insc in pendentes:
        edital = db.get(Edital, insc.edital_id)
        if edital.status == StatusEdital.CANCELADO:
            continue
        antes = snapshot(insc)
        expirou = momento >= edital.data_inicio_avaliacao or edital.status not in (
            StatusEdital.ABERTO, StatusEdital.INSCRICOES_ENCERRADAS,
        )
        if expirou:
            motivos = [MOTIVO_EXPIRADO]
        else:
            estudante = db.get(Usuario, insc.estudante_id)
            ramo = consultar_ramo_academico(servico, estudante.matricula)
            if ramo.indisponivel:
                contagem["aguardando"] += 1
                continue
            congelar(insc, ramo.dados)
            motivos = [MOTIVO_SEM_MATRICULA] if ramo.sem_matricula else todos_os_motivos(db, edital, insc)

        evento = EventoInscricao.REPROCESSAR_INELEGIVEL if motivos else EventoInscricao.REPROCESSAR_ELEGIVEL
        insc.status = MAQUINA_INSCRICAO.proximo(insc.status, evento)
        insc.motivos_indeferimento = motivos or None
        db.flush()
        registrar(db, usuario_id=None, acao="INSCRICAO_REPROCESSAR_VINCULO", entidade="inscricao",
                  entidade_id=insc.id, antes=antes, depois=snapshot(insc))
        notificar(
            db,
            usuario_id=insc.estudante_id,
            tipo="INSCRICAO_STATUS",
            titulo=f"Inscrição {insc.protocolo}: {'homologada' if not motivos else 'indeferida'}",
            mensagem=(
                f"A validação do seu vínculo no edital \"{edital.titulo}\" foi concluída.\n"
                + ("Sua inscrição foi HOMOLOGADA." if not motivos else "Sua inscrição foi INDEFERIDA:\n- " + "\n- ".join(motivos))
            ),
        )
        contagem["homologadas" if not motivos else "indeferidas"] += 1
        log.info("Inscrição %s reprocessada: %s", insc.id, insc.status)
    db.commit()
    return contagem


# --- RN-05: reanálise manual pelo Pró-Reitor ---------------------------------------------------------
def pode_reanalisar(db: Session, edital: Edital, insc: Inscricao) -> bool:
    """Até o início da avaliação do cronograma OU até o edital entrar em avaliação — o que vier primeiro."""
    return (
        insc.status == StatusInscricao.INDEFERIDA
        and edital.status in (StatusEdital.ABERTO, StatusEdital.INSCRICOES_ENCERRADAS)
        and agora(db) < edital.data_inicio_avaliacao
    )


def reanalisar(db: Session, inscricao_id: int, justificativa: str, pro_reitor: Usuario, ip: str | None) -> Inscricao:
    insc = db.scalar(select(Inscricao).where(Inscricao.id == inscricao_id).with_for_update())
    if insc is None:
        raise NaoEncontrado("Inscrição não encontrada.")
    edital = db.get(Edital, insc.edital_id)
    if insc.status != StatusInscricao.INDEFERIDA:
        MAQUINA_INSCRICAO.proximo(insc.status, EventoInscricao.REANALISAR_DEFERIR)  # 409 padronizado
    if not pode_reanalisar(db, edital, insc):
        raise Conflito("O prazo de reanálise terminou: a avaliação deste edital já começou (RN-05).")

    antes = snapshot(insc)
    insc.status = MAQUINA_INSCRICAO.proximo(insc.status, EventoInscricao.REANALISAR_DEFERIR)
    insc.reanalisada_por = pro_reitor.id
    insc.justificativa_reanalise = justificativa
    insc.motivos_indeferimento = None  # os motivos originais ficam preservados na auditoria (dados_antes)
    db.flush()
    registrar(db, usuario_id=pro_reitor.id, acao="INSCRICAO_REANALISAR", entidade="inscricao",
              entidade_id=insc.id, antes=antes, depois=snapshot(insc), ip=ip)
    notificar(
        db,
        usuario_id=insc.estudante_id,
        tipo="INSCRICAO_STATUS",
        titulo=f"Inscrição {insc.protocolo}: homologada após reanálise",
        mensagem=(
            f"Após reanálise da Pró-Reitoria, sua inscrição no edital \"{edital.titulo}\" foi HOMOLOGADA.\n\n"
            f"Justificativa: {justificativa}"
        ),
    )
    db.commit()
    return insc
