from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routers import certificado, dashboard, guias, xml_upload

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="GNRE.Flow - Automacao de DIFAL")

app.include_router(dashboard.router)
app.include_router(xml_upload.router)
app.include_router(guias.router)
app.include_router(certificado.router)

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.on_event("startup")
def on_startup():
    init_db()


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
