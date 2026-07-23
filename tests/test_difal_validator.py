from pathlib import Path

from app.services.difal_validator import uf_suportada_gnre_nacional, validar_nota
from app.services.nfe_parser import parse_nfe_xml

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml"


def _validar(xml_bytes=None):
    if xml_bytes is None:
        xml_bytes = FIXTURE.read_bytes()
    return validar_nota(parse_nfe_xml(xml_bytes))


def test_valores_batem_nao_ha_divergencia():
    resultado = _validar()
    assert resultado.uf_destino == "MG"
    assert resultado.uf_suportada is True
    assert resultado.valor_difal_total == 60.0
    assert resultado.valor_fcp_total == 20.0
    assert resultado.divergente is False
    assert resultado.itens[0].avisos == []


def test_detecta_divergencia_quando_valor_declarado_esta_errado():
    xml = FIXTURE.read_bytes().replace(b"<vICMSUFDest>60.00</vICMSUFDest>", b"<vICMSUFDest>10.00</vICMSUFDest>")
    resultado = _validar(xml)
    assert resultado.divergente is True
    assert any("diverge" in aviso for aviso in resultado.itens[0].avisos)


def test_uf_sem_gnre_nacional_e_sinalizada():
    xml = FIXTURE.read_bytes().replace(b"<UF>MG</UF>", b"<UF>SP</UF>")
    resultado = _validar(xml)
    assert resultado.uf_destino == "SP"
    assert resultado.uf_suportada is False


def test_uf_suportada_gnre_nacional_helper():
    assert uf_suportada_gnre_nacional("MG") is True
    assert uf_suportada_gnre_nacional("SP") is False
    assert uf_suportada_gnre_nacional("RJ") is False
    assert uf_suportada_gnre_nacional(None) is True
