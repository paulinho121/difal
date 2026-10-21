from app.services import gnre_client
from app.services.gnre_client import GnreClientError, _traduzir_erro


def test_429_vira_mensagem_clara_com_registro_das_requisicoes():
    exc = Exception("Server returned response (429) with invalid XML: <title>429 Too Many Requests</title>")
    erro = _traduzir_erro(exc, ["GET https://x/GnreLoteRecepcao?wsdl -> 200", "POST https://x/GnreLoteRecepcao -> 429"])
    assert isinstance(erro, GnreClientError)
    assert "429" in str(erro) and "nenhuma guia foi criada" in str(erro)
    assert "GET https://x/GnreLoteRecepcao?wsdl -> 200" in str(erro)
    assert "POST https://x/GnreLoteRecepcao -> 429" in str(erro)


def test_outros_erros_mantem_texto_original_e_registro():
    erro = _traduzir_erro(ValueError("boom"), [])
    assert "boom" in str(erro)
    assert "nenhuma requisicao concluida" in str(erro)


def test_transport_usa_cache_de_wsdl_compartilhado(monkeypatch):
    capturado = {}

    class ClienteFalso:
        def __init__(self, url, transport):
            capturado["transport"] = transport

    monkeypatch.setattr(gnre_client, "Client", ClienteFalso)
    registro = []
    gnre_client._client_mtls("https://x/Servico", "c.pem", "k.pem", registro)
    assert capturado["transport"].cache is gnre_client._CACHE_WSDL
    assert capturado["transport"].session.verify is gnre_client._VERIFICAR_SSL
    assert capturado["transport"].session.hooks["response"], "hook de registro deveria estar ligado"


RESPOSTA_ENVIO_OK = (
    '<ns1:TRetLote_GNRE xmlns:ns1="http://www.gnre.pe.gov.br"><ns1:ambiente>1</ns1:ambiente>'
    "<ns1:situacaoRecepcao><ns1:codigo>100</ns1:codigo><ns1:descricao>Lote recebido com sucesso!"
    "</ns1:descricao></ns1:situacaoRecepcao><ns1:recibo><ns1:numero>2026000123</ns1:numero>"
    "<ns1:dataHoraRecibo>2026-10-21 10:00:00</ns1:dataHoraRecibo>"
    "<ns1:tempoEstimadoProc>1</ns1:tempoEstimadoProc></ns1:recibo></ns1:TRetLote_GNRE>"
)
RESPOSTA_ENVIO_REJEITADO = (
    '<ns1:TRetLote_GNRE xmlns:ns1="http://www.gnre.pe.gov.br"><ns1:ambiente>1</ns1:ambiente>'
    "<ns1:situacaoRecepcao><ns1:codigo>102</ns1:codigo><ns1:descricao>CNPJ 1 nao habilitado"
    "</ns1:descricao></ns1:situacaoRecepcao></ns1:TRetLote_GNRE>"
)


def test_lote_recebido_codigo_100_e_sucesso_com_numero_do_recibo():
    assert gnre_client._extrair_numero_recibo(RESPOSTA_ENVIO_OK) == "2026000123"
    assert gnre_client._extrair_mensagem_rejeicao(RESPOSTA_ENVIO_OK) is None


def test_codigo_diferente_de_100_continua_sendo_rejeicao_sem_recibo():
    assert gnre_client._extrair_numero_recibo(RESPOSTA_ENVIO_REJEITADO) is None
    msg = gnre_client._extrair_mensagem_rejeicao(RESPOSTA_ENVIO_REJEITADO)
    assert "102" in msg and "nao habilitado" in msg


def test_consulta_de_lote_e_xml_valido_com_ambiente_e_recibo():
    from lxml import etree

    el = gnre_client._montar_consulta_lote("2026000123")
    xml = etree.tostring(el).decode()
    assert "TConsLote_GNRE" in xml and "<ambiente>1</ambiente>" in xml.replace("ns0:", "")
    assert "2026000123" in xml
