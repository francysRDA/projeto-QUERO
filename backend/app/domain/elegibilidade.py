"""Elegibilidade acadêmica (RN-02) — função pura, sem banco nem HTTP.

Retorna TODOS os motivos de inelegibilidade (RN-05: a inscrição indeferida exibe todos os motivos).
"""

from decimal import Decimal


def motivos_academicos(
    *,
    vinculo_ativo: bool | None,
    codigo_curso: str | None,
    nome_curso: str | None,
    cr: Decimal | None,
    cursos_autorizados: set[str],
    cr_minimo: Decimal,
) -> list[str]:
    if vinculo_ativo is None:
        return ["Dados acadêmicos não localizados para a sua matrícula no Sistema Acadêmico."]
    motivos: list[str] = []
    if not vinculo_ativo:
        motivos.append("Vínculo acadêmico inativo.")
    if codigo_curso not in cursos_autorizados:
        motivos.append(f"Curso não autorizado neste edital: {nome_curso or codigo_curso or 'não informado'}.")
    if cr is None or cr < cr_minimo:
        cr_txt = f"{cr:.2f}" if cr is not None else "não informado"
        motivos.append(f"CR {cr_txt} inferior ao mínimo exigido ({cr_minimo:.2f}).")
    return motivos
