"""Homologação formal da inscrição (INS-03, RN-05).

Fatia 3: verificação DOCUMENTAL (todos os obrigatórios presentes, íntegros e ativos).
Fatia 4: acrescenta a verificação ACADÊMICA (vínculo, curso, CR) via ServicoAcademico, em paralelo.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Arquivo, Edital, Inscricao


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
