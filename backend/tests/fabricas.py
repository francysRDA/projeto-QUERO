"""Fábricas de dados de teste compartilhadas."""

import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.storage.disco import ArmazenamentoDisco

SP = ZoneInfo("America/Sao_Paulo")
URL = "/api/v1/editais"
URL_INSC = "/api/v1/inscricoes"


def payload(**sobrescrever) -> dict:
    base = datetime.now(SP).replace(microsecond=0)
    dados = {
        "titulo": "Monitoria de Cálculo I",
        "descricao": "Seleção de monitores para Cálculo I no semestre 2027.1.",
        "categoria": "MONITORIA",
        "modalidade": "Presencial",
        "valor_bolsa": "700.00",
        "carga_horaria_semanal": 12,
        "vagas": 2,
        "cr_minimo": "7.00",
        "prazo_recurso_horas": 48,
        "data_inicio_inscricao": (base - timedelta(hours=1)).isoformat(),
        "data_fim_inscricao": (base + timedelta(days=7)).isoformat(),
        "data_inicio_avaliacao": (base + timedelta(days=8)).isoformat(),
        "data_resultado_preliminar": (base + timedelta(days=12)).isoformat(),
        "data_homologacao_final": (base + timedelta(days=16)).isoformat(),
        "cursos": [
            {"codigo_curso": "ENG-CIV", "nome_curso": "Engenharia Civil"},
            {"codigo_curso": "MAT", "nome_curso": "Matemática"},
        ],
        "documentos": [
            {"nome": "Histórico escolar", "obrigatorio": True},
            {"nome": "Carta de motivação", "obrigatorio": True},
        ],
    }
    dados.update(sobrescrever)
    return dados


MB = 1024 * 1024


def pdf(tamanho: int = 2048, marca: bytes = b"") -> bytes:
    corpo = b"%PDF-1.4\n" + marca
    return corpo + b"0" * max(0, tamanho - len(corpo))


def docs_ids(ed) -> tuple[int, int, int]:
    return tuple(d["id"] for d in ed["documentos"])  # type: ignore[return-value]


def arquivos_form(*pares) -> list:
    """pares: (documento_id, conteudo, nome_arquivo[, content_type])"""
    return [
        (f"doc_{doc}", (nome, io.BytesIO(conteudo), ct[0] if ct else "application/pdf"))
        for doc, conteudo, nome, *ct in pares
    ]


def inscrever(client, ed, headers, *pares):
    h, c = docs_ids(ed)[:2]
    pares = pares or ((h, pdf(marca=b"hist"), "historico.pdf"), (c, pdf(marca=b"carta"), "carta.pdf"))
    return client.post(f"{URL}/{ed['id']}/inscricoes", headers=headers, files=arquivos_form(*pares))


def avancar_relogio(db, horas: float):
    db.execute(text("UPDATE relogio_dev SET segundos = segundos + :s WHERE id = 1"), {"s": int(horas * 3600)})


def arquivos_no_disco(armazenamento: ArmazenamentoDisco) -> list[str]:
    return [c for c, _ in armazenamento.listar()]
