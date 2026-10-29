from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import gnre_regras
from app.services.gnre_regras import interpretar_config_uf

CONFIG_PR = (Path(__file__).parent / "fixtures" / "config_uf_pr_100102.xml").read_text(encoding="utf-8")


def test_convenio_salvo_pela_api_e_usado_nas_regras():
    with TestClient(app) as c:
        assert c.put("/api/certificado/convenios", json={"uf": "pr", "valor": "  VALOR-X  "}).status_code == 200
        assert c.get("/api/certificado/convenios").json()["convenios"]["PR"] == "VALOR-X"
        r = gnre_regras.aplicar_convenio(interpretar_config_uf(CONFIG_PR, "100102"), "PR")
        assert r.convenio == "VALOR-X" and r.pendencias == []
        assert c.put("/api/certificado/convenios", json={"uf": "PR", "valor": ""}).status_code == 200  # limpar
        assert "PR" not in c.get("/api/certificado/convenios").json()["convenios"]


def test_convenio_valida_uf_e_tamanho():
    with TestClient(app) as c:
        assert c.put("/api/certificado/convenios", json={"uf": "XX", "valor": "a"}).status_code == 400
        assert c.put("/api/certificado/convenios", json={"uf": "PR", "valor": "a" * 31}).status_code == 400


def test_mensagem_de_pendencia_do_convenio_nao_tem_colchetes_angulares(monkeypatch):
    monkeypatch.setattr(gnre_regras, "_convenios_configurados", lambda: {})
    r = gnre_regras.aplicar_convenio(interpretar_config_uf(CONFIG_PR, "100102"), "PR")
    texto = " ".join(r.pendencias)
    assert "<" not in texto and ">" not in texto and "Ajustes" in texto
