"""Comprovante de inscrição em PDF (INS-04): protocolo, carimbo de data/hora e hash dos documentos."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import get_settings
from app.models import Arquivo, Edital, EditalDocumentoExigido, Inscricao, Usuario

AZUL = colors.HexColor("#1b365d")


def _fmt(dt) -> str:
    return dt.astimezone(get_settings().tz).strftime("%d/%m/%Y às %H:%M:%S")


def gerar_comprovante(
    inscricao: Inscricao,
    edital: Edital,
    estudante: Usuario,
    arquivos: list[Arquivo],
    documentos: dict[int, EditalDocumentoExigido],
    emitido_em,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Comprovante {inscricao.protocolo}", author="QUERO",
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=AZUL, fontSize=18)
    normal = estilos["BodyText"]
    pequeno = ParagraphStyle("p", parent=normal, fontSize=8, textColor=colors.grey)

    dados = [
        ["Protocolo", inscricao.protocolo],
        ["Edital", Paragraph(edital.titulo, normal)],
        ["Candidato(a)", Paragraph(estudante.nome, normal)],
        ["Matrícula", estudante.matricula or "—"],
        ["Submissão original", _fmt(inscricao.data_submissao_original)],
        ["Última retificação", _fmt(inscricao.data_ultima_retificacao) if inscricao.data_ultima_retificacao else "—"],
        ["Situação na emissão", inscricao.status.replace("_", " ").title()],
    ]
    t_dados = Table(dados, colWidths=[4.5 * cm, 12.5 * cm])
    t_dados.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("FONTSIZE", (1, 0), (1, 0), 13),
    ]))

    linhas = [["Documento", "Arquivo", "Versão", "SHA-256"]]
    for a in arquivos:
        d = documentos.get(a.documento_exigido_id)
        linhas.append([
            Paragraph(d.nome if d else "—", normal),
            Paragraph(a.nome_original, normal),
            str(a.versao),
            Paragraph(f"<font size=6>{a.sha256}</font>", normal),
        ])
    t_docs = Table(linhas, colWidths=[4 * cm, 4.5 * cm, 1.5 * cm, 7 * cm], repeatRows=1)
    t_docs.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))

    doc.build([
        Paragraph("Comprovante de Inscrição", titulo),
        Paragraph("QUERO — Quadro Universitário de Estágios Remunerados e Oportunidades", normal),
        Spacer(1, 0.6 * cm),
        t_dados,
        Spacer(1, 0.6 * cm),
        Paragraph("<b>Documentos vigentes</b>", normal),
        Spacer(1, 0.2 * cm),
        t_docs,
        Spacer(1, 0.8 * cm),
        Paragraph(
            f"Emitido em {_fmt(emitido_em)} (horário oficial de Brasília). O hash SHA-256 permite verificar a "
            "integridade de cada arquivo recebido. A homologação da inscrição não garante a classificação.",
            pequeno,
        ),
    ])
    return buffer.getvalue()
