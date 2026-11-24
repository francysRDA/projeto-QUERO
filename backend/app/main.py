from fastapi import FastAPI

from app.core.errors import registrar_handlers
from app.routers import auth

app = FastAPI(
    title="QUERO API",
    version="0.1.0",
    description="Quadro Universitário de Estágios Remunerados e Oportunidades — API do protótipo.",
)
registrar_handlers(app)

API = "/api/v1"
app.include_router(auth.router, prefix=API)


@app.get(f"{API}/saude", tags=["infra"])
def saude() -> dict[str, str]:
    return {"status": "ok"}
