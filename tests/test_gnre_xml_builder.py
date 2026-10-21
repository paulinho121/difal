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
        data_emissao=date(2026, 7, 20),
        data_pagamento=date(2026, 7, 22),
    )
    base.update(overrides)
    return GuiaParaEmitir(**base)


def test_lote_padrao_segue_regras_do_rj_fcp_no_mesmo_item_e_valida_no_xsd():
    xml_bytes = montar_lote_xml(EMPRESA, [_guia()])
    xml_texto = xml_bytes.decode("utf-8")

    assert xml_texto.count("<receita>") == 1
    assert f"<receita>{RECEITA_DIFAL_POR_OPERACAO}</receita>" in xml_texto
    assert RECEITA_FCP_POR_OPERACAO not in xml_texto
    assert "<tipoGnre>0</tipoGnre>" in xml_texto
    assert '<valor tipo="11">60.00</valor>' in xml_texto
    assert '<valor tipo="12">20.00</valor>' in xml_texto  # FCP no mesmo item
    assert '<valor tipo="21">60.00</valor>' in xml_texto  # total do ICMS
    assert '<valor tipo="22">20.00</valor>' in xml_texto  # total do FCP
    assert "<valorGNRE>80.00</valorGNRE>" in xml_texto  # soma dos itens (GNRE confere: erro 290)
    assert '<documentoOrigem tipo="24">' in xml_texto  # CHAVE DO DFe
    assert "<dataPagamento>2026-07-22</dataPagamento>" in xml_texto
    compacto = "".join(xml_texto.split())
    assert "<codigo>117</codigo><valor>2026-07-20</valor>" in compacto
    validar_contra_xsd(xml_bytes)  # nao levanta == valido no XSD oficial


def test_fcp_em_receita_propria_quando_a_uf_exige_item_separado():
    from app.services.gnre_regras import RegrasReceita

    guia = _guia(regras=RegrasReceita(fecp_no_mesmo_item=False))
    xml_texto = montar_lote_xml(EMPRESA, [guia]).decode("utf-8")
    assert f"<receita>{RECEITA_DIFAL_POR_OPERACAO}</receita>" in xml_texto
    assert f"<receita>{RECEITA_FCP_POR_OPERACAO}</receita>" in xml_texto
    assert "<tipoGnre>2</tipoGnre>" in xml_texto


def test_monta_lote_somente_difal_usa_tipo_gnre_simples():
    xml_texto = montar_lote_xml(EMPRESA, [_guia(valor_fcp=0.0)]).decode("utf-8")
    assert "<tipoGnre>0</tipoGnre>" in xml_texto
    assert 'tipo="12"' not in xml_texto


def test_exigencia_nao_suportada_barra_o_envio_antes_do_gnre():
    from app.services.gnre_regras import RegrasReceita

    guia = _guia(regras=RegrasReceita(pendencias=["convenio obrigatorio"]))
    with pytest.raises(GnreXmlValidationError, match="convenio obrigatorio"):
        montar_lote_xml(EMPRESA, [guia])


def test_data_de_pagamento_obrigatoria_sem_data_levanta_erro():
    with pytest.raises(GnreXmlValidationError, match="data prevista de pagamento"):
        montar_lote_xml(EMPRESA, [_guia(data_pagamento=None)])


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


def _nfe_exemplo():
    from pathlib import Path

    from app.services.nfe_parser import parse_nfe_xml

    return parse_nfe_xml((Path(__file__).parent / "fixtures" / "nfe_exemplo_difal.xml").read_bytes())


def test_contribuinte_emitente_vem_do_emitente_da_nfe_e_nao_do_certificado():
    from app.services.gnre_xml_builder import contribuinte_emitente_da_nfe

    emitente = contribuinte_emitente_da_nfe(_nfe_exemplo())
    assert emitente.cnpj == "12345678000199"
    assert emitente.razao_social == "LOGISTICA AVANCADA BRASIL LTDA"
    assert emitente.uf == "SP"
    assert emitente.municipio_ibge == "3550308"
    assert emitente.cep == "01000000"
    assert emitente.endereco == "Rua das Industrias 100"


def test_emitente_da_nfe_gera_lote_valido_no_xsd():
    from app.services.gnre_xml_builder import contribuinte_emitente_da_nfe

    emitente = contribuinte_emitente_da_nfe(_nfe_exemplo())
    xml_texto = montar_lote_xml(emitente, [_guia()]).decode("utf-8")
    assert "<CNPJ>12345678000199</CNPJ>" in xml_texto


def test_emitente_sem_cnpj_retorna_none_para_usar_fallback():
    from app.services.gnre_xml_builder import contribuinte_emitente_da_nfe

    nfe = _nfe_exemplo()
    nfe.emitente_cnpj = None
    assert contribuinte_emitente_da_nfe(nfe) is None
