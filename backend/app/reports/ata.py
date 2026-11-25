"""Ata de homologação do resultado final e listas (HOM-02).

A ata contém: identificação do edital, data/hora, homologador, listas de contemplados, suplentes,
não classificados no mérito, indeferidos na homologação formal e o resumo dos recursos.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1b365d")
NOME_CATEGORIA = {"ESTAGIO": "Estágio", "MONITORIA": "Monitoria", "BOLSA": "Bolsa"}


@dataclass(frozen=True)
class LinhaResultado:
    posicao: int | None
    protocolo: str
    nome: str
    matricula: str | None
    nota: Decimal | None
    cr: Decimal | None
    situacao: str  # CONTEMPLADO | SUPLENTE | NAO_CLASSIFICADO | INDEFERIDA_HOMOLOGACAO


@dataclass(frozen=True)
class DadosAta:
    edital_id: int
    titulo: str
    categoria: str
    vagas: int
    valor_bolsa: Decimal
    homologado_por: str
    homologado_em: datetime
    linhas: list[LinhaResultado]
    recursos_deferidos: int
    recursos_indeferidos: int


def _fmt_dec(v: Decimal | None) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",")


def gerar_csv(d: DadosAta) -> bytes:
    """CSV com ';' e BOM UTF-8 para abrir corretamente no Excel em português."""
    buffer = io.StringIO()
    w = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    w.writerow(["edital_id", "posicao", "protocolo", "nome", "matricula", "nota", "cr", "situacao"])
    for linha in d.linhas:
        w.writerow([d.edital_id, linha.posicao or "", linha.protocolo, linha.nome, linha.matricula or "",
                    _fmt_dec(linha.nota) if linha.nota is not None else "",
                    _fmt_dec(linha.cr) if linha.cr is not None else "", linha.situacao])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def gerar_pdf(d: DadosAta) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                            bottomMargin=2 * cm, title=f"Ata de homologação — edital {d.edital_id}", author="QUERO")
    est = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=est["Title"], textColor=AZUL, fontSize=16)
    h2 = ParagraphStyle("h2", parent=est["Heading2"], textColor=AZUL, fontSize=12)
    normal = est["BodyText"]
    celula = ParagraphStyle("c", parent=normal, fontSize=9, leading=11)
    quando = d.homologado_em.strftime("%d/%m/%Y às %H:%M")

    elementos = [
        Paragraph("Ata de Homologação do Resultado Final", titulo),
        Paragraph(
            f"Aos {quando} (horário oficial de Brasília), a Pró-Reitoria, representada por <b>{d.homologado_por}</b>, "
            f"HOMOLOGA o resultado final do edital <b>nº {d.edital_id} — {d.titulo}</b> "
            f"({NOME_CATEGORIA.get(d.categoria, d.categoria)}, {d.vagas} vaga(s), bolsa de R$ {_fmt_dec(d.valor_bolsa)}), "
            "após a conclusão das fases de homologação das inscrições, avaliação de mérito e julgamento de recursos, "
            "conforme as listas abaixo. Este resultado é definitivo e imutável no sistema (RN-13).",
            normal,
        ),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Recursos julgados: {d.recursos_deferidos} deferido(s) e {d.recursos_indeferidos} indeferido(s). "
            "Critérios de desempate: maior CR congelado e, persistindo o empate, submissão original mais antiga (RN-09).",
            normal,
        ),
    ]

    grupos = [
        ("Contemplados", "CONTEMPLADO", True),
        ("Suplentes (em ordem de classificação)", "SUPLENTE", True),
        ("Não classificados na avaliação de mérito", "NAO_CLASSIFICADO", False),
        ("Inscrições indeferidas na homologação formal", "INDEFERIDA_HOMOLOGACAO", False),
    ]
    for nome_grupo, situacao, com_posicao in grupos:
        linhas = [linha for linha in d.linhas if linha.situacao == situacao]
        elementos += [Spacer(1, 0.4 * cm), Paragraph(f"{nome_grupo} ({len(linhas)})", h2)]
        if not linhas:
            elementos.append(Paragraph("Nenhum.", normal))
            continue
        cab = (["Pos."] if com_posicao else []) + ["Protocolo", "Nome", "Matrícula", "Nota", "CR"]
        dados = [cab] + [
            ([f"{linha.posicao}º"] if com_posicao else [])
            + [linha.protocolo, Paragraph(linha.nome, celula), linha.matricula or "—", _fmt_dec(linha.nota), _fmt_dec(linha.cr)]
            for linha in linhas
        ]
        larguras = ([1.2 * cm] if com_posicao else []) + [4.4 * cm, 5.4 * cm, 2.4 * cm, 1.6 * cm, 1.6 * cm]
        tabela = Table(dados, colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabela)

    elementos += [
        Spacer(1, 1.2 * cm),
        Paragraph("_______________________________________________", normal),
        Paragraph(f"{d.homologado_por} — Pró-Reitoria", normal),
        Spacer(1, 0.4 * cm),
        Paragraph(
            "<font size=7 color=grey>Documento gerado pelo sistema QUERO. A integridade pode ser verificada pelo hash "
            "SHA-256 registrado na trilha de auditoria. Assinatura digital qualificada (ICP-Brasil) fora do escopo do MVP.</font>",
            normal,
        ),
    ]
    doc.build(elementos)
    return buffer.getvalue()
