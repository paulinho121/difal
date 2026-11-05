"""Base dupla (planilha 'Difal base dupla'): numeros conferidos contra a propria planilha
e contra NF-e reais emitidas pelo CE, cujo ERP ja calcula a base dupla."""

from pathlib import Path

import pytest

from app.services import base_dupla
from app.services.difal_validator import validar_nota
from app.services.nfe_parser import parse_nfe_xml

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


@pytest.mark.parametrize(
    "valor_op, inter, aliq_total, esperado",
    [
        (5445.40, 4, 23.0, 1343.67),  # planilha linha 8 (MA)
        (8736.20, 4, 22.0, 2016.05),  # linha 11 (RJ, 20% + FECOP 2%)
        (1494.25, 4, 20.5, 310.13),  # linha 17 (BA/PE)
        (99.01, 4, 20.0, 19.80),  # linha 20
        (710.00, 4, 19.5, 136.71),  # linha 23 (PR/RO)
        (636.95, 12, 19.5, 59.34),  # linha 24
        (100.00, 7, 19.5, 15.53),  # linha 25
        (6416.89, 4, 17.0, 1005.06),  # linha 38 (RS) = vNF da nota 2705 emitida por SP
    ],
)
def test_calculo_bate_com_a_planilha(valor_op, inter, aliq_total, esperado):
    c = base_dupla.calcular(valor_op, inter, aliq_total, 0.0)
    assert c.difal == pytest.approx(esperado, abs=0.011) and c.fcp == 0.0


def test_fcp_e_separado_do_difal_sem_mudar_o_total():
    c = base_dupla.calcular(8736.20, 4, 22.0, 2.0)
    assert c.total == 2016.05 and c.fcp == 215.04 and c.difal == 1801.01


def test_item_real_do_ce_rs_confere_com_o_erp():
    # NF-e 10599 (CE -> RS): produto 95,22 + frete 15,67 + IPI 9,28 = 120,17; ERP declarou 18,82
    c = base_dupla.calcular(95.22 + 15.67 + 9.28, 4, 17.0, 0.0)
    assert c.base_calculo == 138.99 and c.icms_origem == 4.81 and c.difal == 18.82


def _nfe(xml: bytes):
    return parse_nfe_xml(xml)


def _sem_grupo_ufdest(xml: bytes) -> bytes:
    """Como a nota de SP: sem ICMSUFDest, mas marcada como venda a consumidor final."""
    ini, fim = xml.index(b"<ICMSUFDest>"), xml.index(b"</ICMSUFDest>") + len(b"</ICMSUFDest>")
    return (xml[:ini] + xml[fim:]).replace(b"</ide>", b"<indFinal>1</indFinal></ide>", 1)


def test_nota_de_sp_sem_grupo_icmsufdest_e_calculada_pela_base_dupla():
    xml = _sem_grupo_ufdest(FIXTURE.read_bytes())
    xml = xml.replace(b"<vProd>1000.00</vProd>\n        </prod>", b"<vProd>1000.00</vProd><vFrete>50.00</vFrete>\n        </prod>", 1)
    xml = xml.replace(b"<pICMS>12.00</pICMS>", b"<pICMS>4.00</pICMS>")
    r = validar_nota(_nfe(xml))
    esperado = base_dupla.calcular(1050.0, 4, 18.0, 0.0)  # MG: 18%, sem FCP na planilha
    assert r.metodo == "base_dupla" and r.erro_calculo is None
    assert r.valor_difal_total == esperado.difal and r.valor_fcp_total == 0.0


def test_fcp_declarado_na_nfe_maior_que_o_da_planilha_e_somado_por_cima():
    r = validar_nota(_nfe(FIXTURE.read_bytes()))  # emitida por SP -> MG; planilha: 18% sem FCP; NF-e declara pFCP 2
    ref = base_dupla.calcular(1000.0, 12, 20.0, 2.0)
    assert r.metodo == "base_dupla" and r.valor_fcp_total == ref.fcp and r.valor_difal_total == ref.difal
    # a NF-e declarava 80,00 (60 + 20); a planilha da outro valor -> avisa e usa o da planilha
    assert any("a NF-e declara R$ 80.00" in a for a in r.itens[0].avisos)


def test_fcp_ja_embutido_na_aliquota_da_planilha_nao_e_somado_de_novo():
    params = base_dupla.parametros_uf("RJ")  # 22% = 20% + FECOP 2%
    item = parse_nfe_xml(FIXTURE.read_bytes()).itens[0]  # NF-e declara pFCP 2
    assert base_dupla.taxas_do_item(params, "RJ", item) == (22.0, 2.0)


def test_pb_ncm_9405_tem_fecop_de_2_por_cima_dos_20():
    params = base_dupla.parametros_uf("PB")
    item = parse_nfe_xml(_sem_grupo_ufdest(FIXTURE.read_bytes()).replace(b"<NCM>61091000</NCM>", b"<NCM>94051000</NCM>")).itens[0]
    assert base_dupla.taxas_do_item(params, "PB", item) == (22.0, 2.0)
    outro = parse_nfe_xml(_sem_grupo_ufdest(FIXTURE.read_bytes())).itens[0]
    assert base_dupla.taxas_do_item(params, "PB", outro) == (20.0, 0.0)


def test_exportacao_nao_entra_na_base_dupla():
    assert not base_dupla.aplica("SP", "EX")


def test_emitente_de_outra_uf_continua_usando_o_valor_declarado():
    xml = FIXTURE.read_bytes().replace(b"<UF>SP</UF>", b"<UF>SC</UF>", 1)
    r = validar_nota(_nfe(xml))
    assert r.metodo == "declarado" and r.valor_difal_total == 60.0 and r.valor_fcp_total == 20.0


def test_sem_aliquota_interestadual_o_calculo_e_barrado_nao_chuta():
    xml = _sem_grupo_ufdest(FIXTURE.read_bytes()).replace(b"<pICMS>12.00</pICMS>", b"")
    r = validar_nota(_nfe(xml))
    assert r.erro_calculo and "item 1" in r.erro_calculo and r.valor_difal_total == 0.0


def test_ufs_de_origem_da_planilha_sao_sp_e_ce():
    assert base_dupla.ufs_emitente() == {"SP", "CE"}
    assert base_dupla.aplica("CE", "RS") and base_dupla.aplica("SP", "MG")
    assert not base_dupla.aplica("SC", "RS") and not base_dupla.aplica("SP", "SP")


def test_upload_e_recalculo_de_guia_antiga_pela_base_dupla():
    from fastapi.testclient import TestClient

    from app.database import SessionLocal
    from app.main import app
    from app.models import Guia

    xml = _sem_grupo_ufdest(FIXTURE.read_bytes()).replace(b"<pICMS>12.00</pICMS>", b"<pICMS>4.00</pICMS>")
    xml = xml.replace(b"6780</chNFe>", b"9901</chNFe>").replace(
        b'Id="NFe35260712345678000199550010000123451123456780"', b'Id="NFe35260712345678000199550010000123451123459901"'
    )
    esperado = base_dupla.calcular(1000.0, 4, 18.0, 0.0)
    with TestClient(app) as c:
        r = c.post("/api/xml/upload", files=[("files", ("n.xml", xml, "text/xml"))]).json()["resultados"][0]
        assert r["sucesso"] and r["metodo_calculo"] == "base_dupla" and r["valor_total"] == esperado.difal
        gid = r["guia_id"]
        # simula guia criada antes da regra (valor zerado) e recalcula
        db = SessionLocal()
        g = db.get(Guia, gid)
        g.valor_difal = g.valor_total = 0.0
        db.commit()
        db.close()
        rec = c.post(f"/api/guias/{gid}/recalcular").json()
        assert rec["valor_total"] == esperado.difal and rec["status"] == "aguardando_confirmacao"
        assert rec["metodo_calculo"] == "base_dupla" and rec["pode_recalcular"] is True
        # guia que o GNRE ja aceitou (tem protocolo) nao pode ser recalculada
        db = SessionLocal()
        g = db.get(Guia, gid)
        g.status, g.protocolo_lote = "enviada", "26000000000001"
        db.commit()
        db.close()
        assert c.post(f"/api/guias/{gid}/recalcular").status_code == 400
