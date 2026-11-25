from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import registrar_handlers
from app.routers import auth, editais, inscricoes, usuarios

app = FastAPI(
    title="QUERO API",
    version="0.3.0",
    description="Quadro Universitário de Estágios Remunerados e Oportunidades — API do protótipo.",
)
registrar_handlers(app)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(editais.router, prefix=API)
app.include_router(inscricoes.router, prefix=API)
app.include_router(usuarios.router, prefix=API)

if get_settings().is_dev:
    from app.routers import dev

    app.include_router(dev.router, prefix=API)


@app.get(f"{API}/saude", tags=["infra"])
def saude() -> dict[str, str]:
    return {"status": "ok"}
