import http.server
import threading
from pathlib import Path

from fastapi.testclient import TestClient

import launcher
from app.database import SessionLocal
from app.main import app
from app.models import Guia, ItemNotaFiscal, NotaFiscal

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


def test_dashboard_funciona_com_guia_emitida_no_sqlite():
    """Regressao: cast(criado_em, Date) devolvia so o ano no SQLite e o dashboard
    dava 500 assim que existia uma guia emitida (derrubou a abertura do programa)."""
    with TestClient(app) as c:
        db = SessionLocal()
        for modelo in (Guia, ItemNotaFiscal, NotaFiscal):
            db.query(modelo).delete()
        db.commit()
        db.close()
        r = c.post("/api/xml/upload", files=[("files", ("n.xml", FIXTURE.read_bytes(), "text/xml"))]).json()["resultados"][0]
        db = SessionLocal()
        db.get(Guia, r["guia_id"]).status = "emitida"
        db.commit()
        db.close()

        resp = c.get("/api/dashboard/stats")
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["guias_emitidas"] == 1
        assert len(dados["emissoes_por_dia"]) == 1
        dia = dados["emissoes_por_dia"][0]["dia"]
        assert len(dia) == 10 and dia[4] == "-" and dia[7] == "-"  # AAAA-MM-DD


def _servidor(status: int):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_launcher_considera_servidor_no_ar_mesmo_com_erro_500():
    srv = _servidor(500)
    try:
        assert launcher._aguardar_servidor(f"http://127.0.0.1:{srv.server_address[1]}", tentativas=3) is True
    finally:
        srv.shutdown()


def test_launcher_desiste_quando_nada_responde():
    # porta onde ninguem escuta
    assert launcher._aguardar_servidor("http://127.0.0.1:9", tentativas=2) is False
