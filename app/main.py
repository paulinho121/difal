from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routers import certificado, dashboard, guias, xml_upload

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="GNRE.Flow - Automacao de DIFAL", lifespan=lifespan)

app.include_router(dashboard.router)
app.include_router(xml_upload.router)
app.include_router(guias.router)
app.include_router(certificado.router)

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/")
def raiz(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {})


@app.get("/upload")
def pagina_upload(request: Request):
    return templates.TemplateResponse(request, "upload.html", {})


@app.get("/historico")
def pagina_historico(request: Request):
    return templates.TemplateResponse(request, "historico.html", {})


@app.get("/certificado")
def pagina_certificado(request: Request):
    return templates.TemplateResponse(request, "certificado.html", {})
