from datetime import date

import pytest

from app.services.gnre_boleto import BoletoInvalidoError, DadosBoleto, codigo_barras_da_linha, gerar_pdf

# 4 blocos de 11 digitos + 1 DV cada (48 digitos) -- valores ficticios
LINHA = "85800000000" + "5" + "38960000000" + "1" + "26000513909" + "2" + "12026102100" + "7"
BARRAS = "85800000000" + "38960000000" + "26000513909" + "12026102100"


def _dados(**kw):
    base = dict(
        linha_digitavel=LINHA, valor_total=38.96, uf_favorecida="RJ", receita="100102",
        descricao_receita="ICMS Consumidor Final Não Contribuinte Outra UF por Operação",
        emitente_nome="MULTI COMERCIAL IMPORTADORA LTDA", emitente_documento="05502390000200",
        destinatario_nome="RAFAEL YABRUDI IRAZABAL", destinatario_documento="15202768770",
        documento_origem="42261005502390000200550010005630651064898199",
        data_vencimento=date(2026, 10, 19), data_limite_pagamento=date(2026, 10, 23),
        valor_difal=34.63, valor_fcp=4.33,
    )
    base.update(kw)
    return DadosBoleto(**base)


def test_codigo_de_barras_deriva_da_linha_digitavel_sem_os_dv():
    assert codigo_barras_da_linha(LINHA) == BARRAS
    assert len(BARRAS) == 44


def test_linha_com_tamanho_errado_e_recusada():
    with pytest.raises(BoletoInvalidoError):
        codigo_barras_da_linha("123")


def test_gera_pdf_valido_com_acentos():
    pdf = gerar_pdf(_dados())
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1500


def test_codigo_de_barras_divergente_da_linha_nao_gera_boleto():
    with pytest.raises(BoletoInvalidoError, match="nao confere"):
        gerar_pdf(_dados(codigo_barras="0" * 44))


def test_codigo_de_barras_igual_ao_derivado_e_aceito():
    assert gerar_pdf(_dados(codigo_barras=BARRAS)).startswith(b"%PDF-")
