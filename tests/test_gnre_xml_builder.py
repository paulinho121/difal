from datetime import date

import pytest

from app.services.gnre_xml_builder import (
    ContribuinteDestinatario,
    ContribuinteEmitente,
    GnreXmlValidationError,
    GuiaParaEmitir,
    RECEITA_DIFAL_POR_OPERACAO,
    RECEITA_FCP_POR_OPERACAO,
    _municipio_gnre,
    montar_lote_xml,
    validar_contra_xsd,
)

EMPRESA = ContribuinteEmitente(
    cnpj="12345678000199",
    razao_social="LOGISTICA AVANCADA BRASIL LTDA",
    endereco="Rua das Industrias, 100",
    municipio_ibge="3550308",
    uf="SP",
    cep="01000000",
    telefone="1130000000",
)


def _guia(**overrides):
    base = dict(
        uf_destino="MG",
        chave_nfe="35260712345678000199550010000123451123456780",
        valor_difal=60.00,
        valor_fcp=20.00,
        destinatario=ContribuinteDestinatario(
            documento="12345678909", nome="CONSUMIDOR FINAL EXEMPLO", municipio_ibge="3106200"
        ),
        data_vencimento=date(2026, 7, 20),
        numero_controle="000123451",
    )
    base.update(overrides)
    return GuiaParaEmitir(**base)


def test_monta_lote_com_difal_e_fcp_e_valida_contra_xsd():
    xml_bytes = montar_lote_xml(EMPRESA, [_guia()])
    xml_texto = xml_bytes.decode("utf-8")

    assert f"<receita>{RECEITA_DIFAL_POR_OPERACAO}</receita>" in xml_texto
    assert f"<receita>{RECEITA_FCP_POR_OPERACAO}</receita>" in xml_texto
    assert "<tipoGnre>2</tipoGnre>" in xml_texto  # multiplas receitas: DIFAL + FCP
    assert '<valor tipo="11">60.00</valor>' in xml_texto
    assert '<valor tipo="12">20.00</valor>' in xml_texto
    # nao levanta excecao == validou contra o XSD oficial
    validar_contra_xsd(xml_bytes)


def test_monta_lote_somente_difal_usa_tipo_gnre_simples():
    xml_bytes = montar_lote_xml(EMPRESA, [_guia(valor_fcp=0.0)])
    xml_texto = xml_bytes.decode("utf-8")
    assert "<tipoGnre>0</tipoGnre>" in xml_texto
    assert RECEITA_FCP_POR_OPERACAO not in xml_texto


def test_municipio_gnre_remove_prefixo_de_uf():
    assert _municipio_gnre("3550308") == "50308"
    assert _municipio_gnre("3106200") == "06200"
    assert _municipio_gnre("50308") == "50308"  # ja no formato de 5 digitos


def test_chave_nfe_invalida_levanta_erro():
    with pytest.raises(GnreXmlValidationError):
        montar_lote_xml(EMPRESA, [_guia(chave_nfe="123")])


def test_guia_sem_valores_levanta_erro():
    with pytest.raises(GnreXmlValidationError):
        montar_lote_xml(EMPRESA, [_guia(valor_difal=0.0, valor_fcp=0.0)])


def test_lote_vazio_levanta_erro():
    with pytest.raises(GnreXmlValidationError):
        montar_lote_xml(EMPRESA, [])


def test_lote_acima_de_50_guias_levanta_erro():
    guias = [_guia(chave_nfe=f"{i:044d}") for i in range(51)]
    with pytest.raises(GnreXmlValidationError):
        montar_lote_xml(EMPRESA, guias)
