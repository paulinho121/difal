from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Guia
from app.routers import guias as guias_router
from app.services import gnre_client, gnre_regras

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


@pytest.fixture()
def cliente(monkeypatch):
    chamadas = []

    def enviar_falso(xml, cert, key):
        chamadas.append(xml)
        return gnre_client.ResultadoEnvioLote(protocolo="26000000000001", resposta_bruta="<ok/>")

    monkeypatch.setattr(guias_router, "_carregar_cert_da_empresa", lambda db: (b"c", b"k"))
    monkeypatch.setattr(gnre_regras, "obter_regras", lambda uf, rec, c, k: (gnre_regras.RegrasReceita(), None))
    monkeypatch.setattr(gnre_client, "enviar_lote", enviar_falso)
    with TestClient(app) as c:
        c.chamadas = chamadas
        yield c


def _nova_guia(cliente, chave_sufixo: str) -> int:
    xml = FIXTURE.read_bytes().replace(b"6780</chNFe>", f"{chave_sufixo}</chNFe>".encode())
    xml = xml.replace(b'Id="NFe35260712345678000199550010000123451123456780"', f'Id="NFe3526071234567800019955001000012345112345{chave_sufixo}"'.encode())
    r = cliente.post("/api/xml/upload", files=[("files", ("n.xml", xml, "text/xml"))]).json()["resultados"][0]
    assert r["sucesso"], r
    return r["guia_id"]


def test_confirmar_uma_vez_envia_e_marca_enviada(cliente):
    gid = _nova_guia(cliente, "6781")
    r = cliente.post(f"/api/guias/{gid}/confirmar").json()
    assert r["status"] == "enviada" and r["protocolo_lote"] == "26000000000001"
    assert len(cliente.chamadas) == 1


def test_duplo_clique_nao_envia_duas_vezes_ao_gnre(cliente):
    gid = _nova_guia(cliente, "6782")
    primeiro = cliente.post(f"/api/guias/{gid}/confirmar")
    segundo = cliente.post(f"/api/guias/{gid}/confirmar")
    assert primeiro.status_code == 200
    assert segundo.status_code == 400  # ja "enviada" com protocolo
    assert len(cliente.chamadas) == 1


def test_guia_em_envio_recusa_novo_envio_com_409(cliente):
    gid = _nova_guia(cliente, "6783")
    db = SessionLocal()
    g = db.get(Guia, gid)
    g.status = "enviando"
    db.commit()
    db.close()
    r = cliente.post(f"/api/guias/{gid}/confirmar")
    assert r.status_code == 409
    assert cliente.chamadas == []


def test_envio_parado_ha_mais_de_5_minutos_pode_ser_retomado(cliente):
    gid = _nova_guia(cliente, "6784")
    db = SessionLocal()
    g = db.get(Guia, gid)
    g.status = "enviando"
    g.atualizado_em = datetime.utcnow() - timedelta(minutes=10)
    db.commit()
    db.close()
    assert cliente.post(f"/api/guias/{gid}/confirmar").json()["status"] == "enviada"


def test_guia_em_erro_com_protocolo_pode_ser_consultada(cliente, monkeypatch):
    gid = _nova_guia(cliente, "6785")
    db = SessionLocal()
    g = db.get(Guia, gid)
    g.status = "erro"
    g.protocolo_lote = "26000000000009"
    db.commit()
    db.close()
    consultas = []

    def consultar_falso(protocolo, cert, key):
        consultas.append(protocolo)
        return gnre_client.ResultadoConsultaLote("400", "processado", [], "<x/>")

    monkeypatch.setattr(gnre_client, "consultar_resultado_lote", consultar_falso)
    r = cliente.post(f"/api/guias/{gid}/atualizar-status")
    assert r.status_code == 200 and consultas == ["26000000000009"]


def test_erro_sem_protocolo_nao_pode_ser_consultado(cliente):
    gid = _nova_guia(cliente, "6786")
    db = SessionLocal()
    g = db.get(Guia, gid)
    g.status = "erro"
    db.commit()
    db.close()
    assert cliente.post(f"/api/guias/{gid}/atualizar-status").status_code == 400
