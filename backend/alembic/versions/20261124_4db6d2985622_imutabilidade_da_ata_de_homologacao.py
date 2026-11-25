"""imutabilidade da ata de homologacao (RN-13, HOM-02)

A ata e os arquivos que ela referencia (PDF e CSV) tornam-se somente leitura no banco:
correções extraordinárias só por NOVA ata vinculada (eh_retificacao = true), nunca editando a anterior.

Revision ID: 4db6d2985622
Revises: 88892f5d7d35
Create Date: 2026-11-24 22:38:57.080628-03:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = '4db6d2985622'
down_revision: Union[str, None] = '88892f5d7d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reutiliza fn_bloquear_alteracao() criada na migration inicial.
    op.execute("""
        CREATE TRIGGER trg_ata_imutavel
        BEFORE UPDATE OR DELETE ON atas_homologacao
        FOR EACH ROW EXECUTE FUNCTION fn_bloquear_alteracao();
    """)
    op.execute("""
        CREATE FUNCTION fn_bloquear_arquivo_de_ata() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM atas_homologacao
                       WHERE arquivo_pdf_id = OLD.id OR arquivo_csv_id = OLD.id) THEN
                RAISE EXCEPTION 'Registro imutável em arquivos: arquivo de ata homologada (%)', OLD.id
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_arquivo_de_ata_imutavel
        BEFORE UPDATE OR DELETE ON arquivos
        FOR EACH ROW EXECUTE FUNCTION fn_bloquear_arquivo_de_ata();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_arquivo_de_ata_imutavel ON arquivos")
    op.execute("DROP FUNCTION IF EXISTS fn_bloquear_arquivo_de_ata()")
    op.execute("DROP TRIGGER IF EXISTS trg_ata_imutavel ON atas_homologacao")
