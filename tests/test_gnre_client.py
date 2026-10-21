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
