from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import consulta_automatica as ca
from app.database import SessionLocal
from app.main import app
from app.models import Guia, ItemNotaFiscal, NotaFiscal
from app.routers import guias as guias_router
from app.services import gnre_client, gnre_regras

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


@pytest.fixture()
def cenario(monkeypatch):
    envios = []
    comportamento = {"modo": "429"}

    def enviar(xml, cert, key):
        envios.append(1)
        if comportamento["modo"] == "429":
            raise gnre_client.GnreLimiteRequisicoesError("O GNRE limitou as requisicoes (429 Too Many Requests).")
        return gnre_client.ResultadoEnvioLote(protocolo="26000000000777", resposta_bruta="<ok/>")

    monkeypatch.setattr(guias_router, "_carregar_cert_da_empresa", lambda db: (b"c", b"k"))
    monkeypatch.setattr(gnre_regras, "obter_regras", lambda uf, rec, c, k: (gnre_regras.RegrasReceita(), None))
    monkeypatch.setattr(gnre_client, "enviar_lote", enviar)
    ca._ultimo_reenvio.clear()
    ca._reenvios.clear()
    with TestClient(app) as c:
        db = SessionLocal()
        for modelo in (Guia, ItemNotaFiscal, NotaFiscal):
            db.query(modelo).delete()
        db.commit()
        db.close()
        c.envios, c.comportamento = envios, comportamento
        yield c


def _nova_guia(c, sufixo="8001", uf="MG") -> int:
    xml = FIXTURE.read_bytes().replace(b"6780</chNFe>", f"{sufixo}</chNFe>".encode())
    xml = xml.replace(
        b'Id="NFe35260712345678000199550010000123451123456780"',
        f'Id="NFe3526071234567800019955001000012345112345{sufixo}"'.encode(),
    )
    if uf != "MG":
        xml = xml.replace(b"<UF>MG</UF>", f"<UF>{uf}</UF>".encode())
    r = c.post("/api/xml/upload", files=[("files", ("n.xml", xml, "text/xml"))]).json()["resultados"][0]
    assert r["sucesso"], r
    return r["guia_id"]


def _status(gid):
    db = SessionLocal()
    g = db.get(Guia, gid)
    s = (g.status, g.protocolo_lote)
    db.close()
    return s


def test_429_no_programa_instalado_vira_aguardando_reenvio(cenario, monkeypatch):
    monkeypatch.setenv("GNRE_AUTO_CONSULTA", "1")
    gid = _nova_guia(cenario)
    r = cenario.post(f"/api/guias/{gid}/confirmar").json()
    assert r["status"] == "aguardando_reenvio" and "sozinho" in r["mensagem_erro"]


def test_429_fora_do_programa_instalado_continua_sendo_erro(cenario, monkeypatch):
    monkeypatch.delenv("GNRE_AUTO_CONSULTA", raising=False)
    gid = _nova_guia(cenario, "8002")
    assert cenario.post(f"/api/guias/{gid}/confirmar").json()["status"] == "erro"


def test_reenvio_automatico_respeita_intervalo_e_conclui_quando_o_gnre_aceita(cenario, monkeypatch):
    monkeypatch.setenv("GNRE_AUTO_CONSULTA", "1")
    gid = _nova_guia(cenario, "8003")
    cenario.post(f"/api/guias/{gid}/confirmar")  # 429 -> aguardando_reenvio (marca o instante)
    t0 = ca._ultimo_reenvio[gid]
    assert ca.reenviar_pendentes(agora=t0 + ca.INTERVALO_REENVIO_SEGUNDOS - 1) == 0  # cedo demais
    assert len(cenario.envios) == 1

    assert ca.reenviar_pendentes(agora=t0 + ca.INTERVALO_REENVIO_SEGUNDOS) == 1  # ainda 429
    assert _status(gid)[0] == "aguardando_reenvio" and len(cenario.envios) == 2

    cenario.comportamento["modo"] = "ok"
    assert ca.reenviar_pendentes(agora=t0 + 2 * ca.INTERVALO_REENVIO_SEGUNDOS) == 1
    assert _status(gid) == ("enviada", "26000000000777")
    assert ca.reenviar_pendentes(agora=t0 + 10 * ca.INTERVALO_REENVIO_SEGUNDOS) == 0  # nada mais a reenviar


def test_para_depois_do_maximo_de_tentativas_e_volta_para_erro(cenario, monkeypatch):
    monkeypatch.setenv("GNRE_AUTO_CONSULTA", "1")
    gid = _nova_guia(cenario, "8004")
    cenario.post(f"/api/guias/{gid}/confirmar")
    ca._reenvios[gid] = ca.MAX_REENVIOS
    ca.reenviar_pendentes(agora=ca._ultimo_reenvio[gid] + 10_000)
    status, _ = _status(gid)
    assert status == "erro"
    assert len(cenario.envios) == 1  # nao enviou mais


def test_so_reenvia_guias_em_aguardando_reenvio(cenario):
    gid = _nova_guia(cenario, "8005")  # aguardando_confirmacao: o usuario ainda nao confirmou
    assert ca.reenviar_pendentes(agora=10_000_000.0) == 0
    assert cenario.envios == [] and _status(gid)[0] == "aguardando_confirmacao"


def test_sp_e_bloqueada_ja_no_upload_e_no_envio(cenario):
    gid = _nova_guia(cenario, "8006", uf="SP")
    db = SessionLocal()
    g = db.get(Guia, gid)
    assert g.status == "erro" and "GARE" in g.mensagem_erro
    db.close()
    r = cenario.post(f"/api/guias/{gid}/confirmar")
    assert r.status_code == 400 and "SP" in r.json()["detail"]
    assert cenario.envios == []
