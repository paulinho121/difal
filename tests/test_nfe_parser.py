from pathlib import Path

import pytest

from app.services.nfe_parser import NFeParseError, parse_nfe_xml

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


def _carregar(xml_bytes=None):
    if xml_bytes is None:
        xml_bytes = FIXTURE.read_bytes()
    return parse_nfe_xml(xml_bytes)


def test_extrai_dados_basicos_da_nota():
    nfe = _carregar()
    assert nfe.chave_acesso == "35260712345678000199550010000123451123456780"
    assert len(nfe.chave_acesso) == 44
    assert nfe.numero == "12345"
    assert nfe.serie == "1"
    assert nfe.emitente_cnpj == "12345678000199"
    assert nfe.uf_origem == "SP"


def test_extrai_destinatario_consumidor_final():
    nfe = _carregar()
    assert nfe.destinatario_doc == "12345678909"
    assert nfe.destinatario_nome == "CONSUMIDOR FINAL EXEMPLO"
    assert nfe.uf_destino == "MG"
    assert nfe.municipio_destino_ibge == "3106200"


def test_extrai_grupo_icmsufdest_do_item():
    nfe = _carregar()
    assert len(nfe.itens) == 1
    item = nfe.itens[0]
    assert item.tem_difal_declarado
    assert item.ncm == "61091000"
    assert item.cfop == "6108"
    assert item.v_prod == 1000.0
    assert item.v_bc_uf_dest == 1000.0
    assert item.p_icms_uf_dest == 18.0
    assert item.p_icms_inter == 12.0
    assert item.p_icms_inter_part == 100.0
    assert item.v_icms_uf_dest == 60.0
    assert item.v_fcp_uf_dest == 20.0


def test_item_sem_icmsufdest_nao_aplica_difal():
    xml = FIXTURE.read_bytes().replace(
        b"<ICMSUFDest>", b"<ICMSUFDestRENOMEADO>"
    ).replace(b"</ICMSUFDest>", b"</ICMSUFDestRENOMEADO>")
    nfe = _carregar(xml)
    assert nfe.itens[0].tem_difal_declarado is False


def test_xml_invalido_levanta_erro():
    with pytest.raises(NFeParseError):
        _carregar(b"isto nao e xml")


def test_sem_infnfe_levanta_erro():
    with pytest.raises(NFeParseError):
        _carregar(b"<root><outraCoisa/></root>")
