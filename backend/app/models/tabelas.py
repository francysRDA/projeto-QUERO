"""Modelo relacional (Documento de Projeto §10 + ajustes do PLANO_PROTOTIPO §1.3).

Ajustes em relação ao §10:
  - L-01: tabela `classificacoes` (resultado preliminar / pós-recurso / final imutável).
  - L-02: tabela `impedimentos` (declaração de impedimento por avaliador e inscrição).
  - L-03: tabelas `tarefas` (fila do worker) e `sessoes` (refresh token revogável).
  - L-12: `usuarios.cpf` opcional (minimização LGPD; SSO pode não fornecer).
  - `relogio_dev`: deslocamento de relógio para demonstrações (somente dev/test).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domain.estados import StatusAvaliacao, StatusEdital, StatusInscricao, StatusRecurso
from app.domain.perfis import Perfil


def _in(coluna: str, valores) -> str:
    return f"{coluna} IN ({', '.join(repr(str(v)) for v in valores)})"


TS = DateTime(timezone=True)


# 1. Usuários -----------------------------------------------------------------------------------
class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint(_in("perfil", Perfil), name="ck_usuarios_perfil"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sso_sub: Mapped[str | None] = mapped_column(String(120), unique=True)
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True)
    matricula: Mapped[str | None] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    senha_hash: Mapped[str | None] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Sessao(Base):
    """L-03: refresh tokens (apenas hash) para permitir revogação no logout (RNF-06)."""

    __tablename__ = "sessoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(TS)
    revogada_em: Mapped[datetime | None] = mapped_column(TS)
    ip_origem: Mapped[str | None] = mapped_column(String(45))


# 2-5. Editais ----------------------------------------------------------------------------------
class Edital(Base):
    __tablename__ = "editais"
    __table_args__ = (
        CheckConstraint("categoria IN ('ESTAGIO', 'MONITORIA', 'BOLSA')", name="ck_editais_categoria"),
        CheckConstraint("valor_bolsa >= 0", name="ck_editais_valor"),
        CheckConstraint("carga_horaria_semanal > 0", name="ck_editais_carga"),
        CheckConstraint("vagas > 0", name="ck_editais_vagas"),
        CheckConstraint("cr_minimo >= 0 AND cr_minimo <= 10", name="ck_editais_cr"),
        CheckConstraint("prazo_recurso_horas > 0", name="ck_editais_prazo_recurso"),
        CheckConstraint(_in("status", StatusEdital), name="ck_editais_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(String(30))
    modalidade: Mapped[str] = mapped_column(String(50))
    valor_bolsa: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    carga_horaria_semanal: Mapped[int] = mapped_column(Integer)
    vagas: Mapped[int] = mapped_column(Integer)
    cr_minimo: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    prazo_recurso_horas: Mapped[int] = mapped_column(Integer, server_default=text("48"))
    criterios_pontuacao: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    criterios_desempate: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[\"CR_DESC\", \"SUBMISSAO_ASC\"]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(30), server_default=text("'RASCUNHO'"), index=True)
    data_inicio_inscricao: Mapped[datetime] = mapped_column(TS)
    data_fim_inscricao: Mapped[datetime] = mapped_column(TS)
    data_inicio_avaliacao: Mapped[datetime] = mapped_column(TS)
    data_resultado_preliminar: Mapped[datetime] = mapped_column(TS)
    data_homologacao_final: Mapped[datetime] = mapped_column(TS)
    data_fim_recurso: Mapped[datetime | None] = mapped_column(TS)  # preenchida ao abrir recurso (RN-10)
    justificativa_cancelamento: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    cursos: Mapped[list["EditalCurso"]] = relationship(
        back_populates="edital", cascade="all, delete-orphan", order_by="EditalCurso.id"
    )
    documentos: Mapped[list["EditalDocumentoExigido"]] = relationship(
        back_populates="edital", cascade="all, delete-orphan", order_by="EditalDocumentoExigido.id"
    )
    comissao: Mapped[list["ComissaoEdital"]] = relationship(
        back_populates="edital", cascade="all, delete-orphan"
    )


class EditalCurso(Base):
    __tablename__ = "edital_cursos"
    __table_args__ = (UniqueConstraint("edital_id", "codigo_curso"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id", ondelete="CASCADE"))
    codigo_curso: Mapped[str] = mapped_column(String(40))
    nome_curso: Mapped[str] = mapped_column(String(120))

    edital: Mapped[Edital] = relationship(back_populates="cursos")


class EditalDocumentoExigido(Base):
    __tablename__ = "edital_documentos_exigidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    edital: Mapped[Edital] = relationship(back_populates="documentos")


class ComissaoEdital(Base):
    __tablename__ = "comissao_edital"
    __table_args__ = (UniqueConstraint("edital_id", "avaliador_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id", ondelete="CASCADE"))
    avaliador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    designado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    designado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    edital: Mapped[Edital] = relationship(back_populates="comissao")


# 6-7. Inscrições e arquivos --------------------------------------------------------------------
class Inscricao(Base):
    __tablename__ = "inscricoes"
    __table_args__ = (
        UniqueConstraint("edital_id", "estudante_id"),  # RN-01 (L-04: desistência é definitiva)
        CheckConstraint(_in("status", StatusInscricao), name="ck_inscricoes_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    protocolo: Mapped[str] = mapped_column(String(50), unique=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id"), index=True)
    estudante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    status: Mapped[str] = mapped_column(String(35))
    motivos_indeferimento: Mapped[list[str] | None] = mapped_column(JSONB)
    vinculo_ativo_congelado: Mapped[bool | None] = mapped_column(Boolean)
    curso_congelado: Mapped[str | None] = mapped_column(String(120))
    cr_congelado: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    data_submissao_original: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    data_ultima_retificacao: Mapped[datetime | None] = mapped_column(TS)
    reanalisada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    justificativa_reanalise: Mapped[str | None] = mapped_column(Text)


class Arquivo(Base):
    __tablename__ = "arquivos"
    __table_args__ = (
        CheckConstraint("tamanho_bytes > 0 AND tamanho_bytes <= 10485760", name="ck_arquivos_tamanho"),
        CheckConstraint(
            "status_varredura IN ('PENDENTE', 'VALIDADO', 'QUARENTENA', 'REJEITADO')",
            name="ck_arquivos_varredura",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inscricao_id: Mapped[int | None] = mapped_column(ForeignKey("inscricoes.id", ondelete="CASCADE"), index=True)
    documento_exigido_id: Mapped[int | None] = mapped_column(ForeignKey("edital_documentos_exigidos.id"))
    chave: Mapped[str] = mapped_column(String(255), unique=True)
    nome_original: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(100), server_default=text("'application/pdf'"))
    versao: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    status_varredura: Mapped[str] = mapped_column(String(20), server_default=text("'VALIDADO'"))
    enviado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


# 8. Avaliações ---------------------------------------------------------------------------------
class Avaliacao(Base):
    __tablename__ = "avaliacoes"
    __table_args__ = (
        CheckConstraint("nota_merito >= 0 AND nota_merito <= 10", name="ck_avaliacoes_nota"),
        CheckConstraint("parecer IN ('DEFERIDO', 'INDEFERIDO')", name="ck_avaliacoes_parecer"),
        CheckConstraint(_in("status", StatusAvaliacao), name="ck_avaliacoes_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inscricao_id: Mapped[int] = mapped_column(ForeignKey("inscricoes.id"), unique=True)
    avaliador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    declaracao_sem_impedimento: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    nota_merito: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    parecer: Mapped[str | None] = mapped_column(String(20))
    justificativa: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'RASCUNHO'"))
    justificativa_retificacao: Mapped[str | None] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Impedimento(Base):
    """L-02: avaliador declarou impedimento/suspeição para uma inscrição (RN-07, UC-07 E1)."""

    __tablename__ = "impedimentos"
    __table_args__ = (UniqueConstraint("inscricao_id", "avaliador_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    inscricao_id: Mapped[int] = mapped_column(ForeignKey("inscricoes.id"))
    avaliador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str] = mapped_column(Text)
    declarado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


# 9-10. Recursos e atas -------------------------------------------------------------------------
class Recurso(Base):
    __tablename__ = "recursos"
    __table_args__ = (
        CheckConstraint("char_length(texto) <= 5000", name="ck_recursos_texto"),
        CheckConstraint(_in("status", StatusRecurso), name="ck_recursos_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inscricao_id: Mapped[int] = mapped_column(ForeignKey("inscricoes.id"), unique=True)
    texto: Mapped[str] = mapped_column(Text)
    arquivo_anexo_id: Mapped[int | None] = mapped_column(ForeignKey("arquivos.id"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ABERTO'"))
    julgado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    justificativa_decisao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    julgado_em: Mapped[datetime | None] = mapped_column(TS)


class AtaHomologacao(Base):
    __tablename__ = "atas_homologacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id"))
    homologado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    arquivo_pdf_id: Mapped[int] = mapped_column(ForeignKey("arquivos.id"))
    arquivo_csv_id: Mapped[int] = mapped_column(ForeignKey("arquivos.id"))
    eh_retificacao: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    justificativa_retificacao: Mapped[str | None] = mapped_column(Text)
    homologado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Classificacao(Base):
    """L-01: posição de cada candidato em cada fase do resultado (RN-09, RN-12, RN-13)."""

    __tablename__ = "classificacoes"
    __table_args__ = (
        UniqueConstraint("inscricao_id", "fase"),
        CheckConstraint("fase IN ('PRELIMINAR', 'POS_RECURSO', 'FINAL')", name="ck_classificacoes_fase"),
        CheckConstraint(
            "situacao IN ('CONTEMPLADO', 'SUPLENTE', 'NAO_CLASSIFICADO')", name="ck_classificacoes_situacao"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id"), index=True)
    inscricao_id: Mapped[int] = mapped_column(ForeignKey("inscricoes.id"))
    fase: Mapped[str] = mapped_column(String(20))
    posicao: Mapped[int | None] = mapped_column(Integer)
    nota: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    situacao: Mapped[str] = mapped_column(String(20))
    calculado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


# 11-12. Notificações e auditoria ---------------------------------------------------------------
class Notificacao(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        CheckConstraint("email_status IN ('PENDENTE', 'ENVIADO', 'FALHA')", name="ck_notificacoes_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(50))
    titulo: Mapped[str] = mapped_column(String(200))
    mensagem: Mapped[str] = mapped_column(Text)
    lida: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    email_status: Mapped[str] = mapped_column(String(20), server_default=text("'PENDENTE'"))
    tentativas_email: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AuditoriaLog(Base):
    """RN-14 / RNF-10. Imutável: trigger no banco rejeita UPDATE e DELETE (L-09)."""

    __tablename__ = "auditoria_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    acao: Mapped[str] = mapped_column(String(60))
    entidade: Mapped[str] = mapped_column(String(50))
    entidade_id: Mapped[int] = mapped_column(Integer)
    dados_antes: Mapped[dict | None] = mapped_column(JSONB)
    dados_depois: Mapped[dict | None] = mapped_column(JSONB)
    ip_origem: Mapped[str | None] = mapped_column(String(45))
    destaque: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # ex.: RN-11 comissão única
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


# Infraestrutura --------------------------------------------------------------------------------
class Tarefa(Base):
    """L-03: fila simples do worker, consumida com SELECT ... FOR UPDATE SKIP LOCKED (§8.2)."""

    __tablename__ = "tarefas"
    __table_args__ = (
        CheckConstraint("status IN ('PENDENTE', 'CONCLUIDA', 'FALHA')", name="ck_tarefas_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    executar_em: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)
    tentativas: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'PENDENTE'"))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class RelogioDev(Base):
    __tablename__ = "relogio_dev"
    __table_args__ = (CheckConstraint("id = 1", name="ck_relogio_unico"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    segundos: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
