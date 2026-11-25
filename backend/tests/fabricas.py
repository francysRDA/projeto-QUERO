"""Fábricas de dados de teste compartilhadas."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")
URL = "/api/v1/editais"


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
