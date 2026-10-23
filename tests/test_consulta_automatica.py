from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import consulta_automatica as ca
from app.database import SessionLocal
from app.main import app
from app.models import Guia, ItemNotaFiscal, NotaFiscal
from app.routers import guias as guias_router

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


def _guia_com_status(cliente, sufixo: str, status: str, protocolo: str | None) -> int:
    xml = FIXTURE.read_bytes().replace(b"6780</chNFe>", f"{sufixo}</chNFe>".encode())
    xml = xml.replace(
        b'Id="NFe35260712345678000199550010000123451123456780"',
        f'Id="NFe3526071234567800019955001000012345112345{sufixo}"'.encode(),
    )
    r = cliente.post("/api/xml/upload", files=[("files", ("n.xml", xml, "text/xml"))]).json()["resultados"][0]
    db = SessionLocal()
    g = db.get(Guia, r["guia_id"])
    g.status, g.protocolo_lote = status, protocolo
    db.commit()
    db.close()
    return r["guia_id"]


@pytest.fixture()
def cenario(monkeypatch):
    consultas = []
    monkeypatch.setattr(
        guias_router, "consultar_e_atualizar", lambda db, guia: consultas.append(guia.id)
    )
    ca._ultima_tentativa.clear()
    ca._tentativas.clear()
    with TestClient(app) as c:
        db = SessionLocal()  # banco limpo: outros testes deixam guias "enviada" para tras
        for modelo in (Guia, ItemNotaFiscal, NotaFiscal):
            db.query(modelo).delete()
        db.commit()
        db.close()
        yield c, consultas


def test_consulta_so_guias_enviadas_com_protocolo(cenario):
    c, consultas = cenario
    enviada = _guia_com_status(c, "7001", "enviada", "26000000000101")
    _guia_com_status(c, "7002", "erro", "26000000000102")  # rejeitada: nao consulta
    _guia_com_status(c, "7003", "enviada", None)  # sem protocolo
    _guia_com_status(c, "7004", "emitida", "26000000000104")
    assert ca.consultar_pendentes(agora=1000.0) == 1
    assert consultas == [enviada]


def test_respeita_intervalo_entre_consultas_da_mesma_guia(cenario):
    c, consultas = cenario
    gid = _guia_com_status(c, "7005", "enviada", "26000000000105")
    assert ca.consultar_pendentes(agora=1000.0) == 1
    assert ca.consultar_pendentes(agora=1000.0 + ca.INTERVALO_SEGUNDOS - 1) == 0  # cedo demais
    assert ca.consultar_pendentes(agora=1000.0 + ca.INTERVALO_SEGUNDOS) == 1
    assert consultas == [gid, gid]


def test_para_depois_do_maximo_de_tentativas(cenario):
    c, consultas = cenario
    gid = _guia_com_status(c, "7006", "enviada", "26000000000106")
    ca._tentativas[gid] = ca.MAX_TENTATIVAS
    assert ca.consultar_pendentes(agora=10_000_000.0) == 0
    assert consultas == []


def test_uma_consulta_por_vez_mesmo_com_varias_pendentes(cenario):
    c, consultas = cenario
    a = _guia_com_status(c, "7007", "enviada", "26000000000107")
    b = _guia_com_status(c, "7008", "enviada", "26000000000108")
    assert ca.consultar_pendentes(agora=1000.0) == 1
    assert ca.consultar_pendentes(agora=1001.0) == 1  # a proxima guia, nao a mesma
    assert sorted(consultas) == sorted([a, b])


def test_so_liga_com_variavel_de_ambiente(monkeypatch):
    monkeypatch.delenv("GNRE_AUTO_CONSULTA", raising=False)
    assert ca.ativa() is False
    monkeypatch.setenv("GNRE_AUTO_CONSULTA", "1")
    assert ca.ativa() is True
