"""Cliente SOAP para os WebServices da GNRE, autenticado por mTLS com o
certificado A1 (e-CNPJ) do contribuinte.

ATENCAO - unico ponto do projeto que depende de algo que so pode ser
confirmado com acesso real ao ambiente (o WSDL exige o certificado mTLS para
ser sequer baixado, entao nao foi possivel inspeciona-lo durante o
planejamento): o nome exato da operacao SOAP e do parametro de cada servico.
Este modulo tenta uma lista de nomes de operacao comuns em integracoes GNRE/
NFe e, se nenhum bater, orienta a rodar `listar_operacoes_disponiveis()` (uma
chamada somente-leitura, sem efeitos colaterais) para descobrir o nome real
com o certificado do usuario antes do primeiro envio de producao.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass

import requests
from lxml import etree
from zeep import Client
from zeep.transports import Transport

GNRE_LOTE_RECEPCAO_URL = os.getenv(
    "GNRE_LOTE_RECEPCAO_URL", "https://www.gnre.pe.gov.br/gnreWS/services/GnreLoteRecepcao"
)
GNRE_RESULTADO_LOTE_URL = os.getenv(
    "GNRE_RESULTADO_LOTE_URL", "https://www.gnre.pe.gov.br/gnreWS/services/GnreResultadoLote"
)
GNRE_CONFIG_UF_URL = os.getenv("GNRE_CONFIG_UF_URL", "https://www.gnre.pe.gov.br/gnreWS/services/GnreConfigUF")

# Nomes candidatos, na ordem em que serao tentados. "processar" confirmado
# como o nome real da operacao do GnreLoteRecepcao ao consultar o WSDL de
# producao com um certificado real (listar_operacoes_disponiveis() via
# /api/certificado/testar) -- os demais eram convencoes chutadas antes disso.
# GnreResultadoLote nao foi confirmado ainda; mantido como suposicao pela
# mesma convencao ate ser validado com uma consulta real.
OPERACOES_ENVIO_CANDIDATAS = ["processar", "gnreRecepcaoLote", "GnreRecepcaoLote", "recepcaoLote", "RecepcaoLote"]
OPERACOES_RESULTADO_CANDIDATAS = [
    "processar",
    "gnreResultadoLote",
    "GnreResultadoLote",
    "resultadoLote",
    "ResultadoLote",
]


class GnreClientError(Exception):
    pass


class OperacaoSoapNaoEncontradaError(GnreClientError):
    def __init__(self, tentadas: list[str], disponiveis: list[str]):
        self.tentadas = tentadas
        self.disponiveis = disponiveis
        super().__init__(
            f"Nenhuma das operacoes esperadas ({', '.join(tentadas)}) foi encontrada no WSDL. "
            f"Operacoes realmente disponiveis: {', '.join(disponiveis) or '(nao foi possivel listar)'}. "
            "Ajuste OPERACOES_ENVIO_CANDIDATAS / OPERACOES_RESULTADO_CANDIDATAS em gnre_client.py."
        )


# situacaoGuia (confirmado no XSD lote_gnre_result_v2.00.xsd):
SITUACAO_GUIA_PROCESSADA = "0"
SITUACAO_GUIA_INVALIDADA_PORTAL = "1"
SITUACAO_GUIA_INVALIDADA_UF = "2"
SITUACAO_GUIA_ERRO_COMUNICACAO = "3"


@dataclass
class ResultadoEnvioLote:
    protocolo: str | None
    resposta_bruta: str


@dataclass
class GuiaResultado:
    situacao: str | None
    valor_gnre: float | None
    linha_digitavel: str | None
    codigo_barras: str | None
    motivos_rejeicao: list[dict]


@dataclass
class ResultadoConsultaLote:
    situacao_processo_codigo: str | None
    situacao_processo_descricao: str | None
    guias: list[GuiaResultado]
    resposta_bruta: str


@contextmanager
def _arquivos_cert_temporarios(cert_pem: bytes, key_pem: bytes):
    cert_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    key_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    try:
        cert_file.write(cert_pem)
        cert_file.close()
        key_file.write(key_pem)
        key_file.close()
        yield cert_file.name, key_file.name
    finally:
        os.unlink(cert_file.name)
        os.unlink(key_file.name)


def _client_mtls(wsdl_url: str, cert_path: str, key_path: str) -> Client:
    session = requests.Session()
    session.cert = (cert_path, key_path)
    transport = Transport(session=session, timeout=30, operation_timeout=60)
    return Client(f"{wsdl_url}?wsdl", transport=transport)


def _operacoes_do_client(client: Client) -> dict:
    operacoes = {}
    for service in client.wsdl.services.values():
        for port in service.ports.values():
            operacoes.update(port.binding._operations)
    return operacoes


def _resolver_operacao(client: Client, candidatas: list[str]):
    disponiveis = _operacoes_do_client(client)
    for nome in candidatas:
        if nome in disponiveis:
            return getattr(client.service, nome)
    raise OperacaoSoapNaoEncontradaError(candidatas, list(disponiveis.keys()))


def listar_operacoes_disponiveis(wsdl_url: str, cert_pem: bytes, key_pem: bytes) -> list[str]:
    """Diagnostico somente-leitura: lista as operacoes SOAP reais do WSDL
    usando o certificado do usuario. Rode isto uma vez (via /api/certificado/
    testar ou um script avulso) para confirmar os nomes antes do primeiro
    envio real."""
    with _arquivos_cert_temporarios(cert_pem, key_pem) as (cert_path, key_path):
        client = _client_mtls(wsdl_url, cert_path, key_path)
        return list(_operacoes_do_client(client).keys())


def testar_conectividade(cert_pem: bytes, key_pem: bytes) -> dict:
    """Chamada leve e sem efeitos colaterais (GnreConfigUF) so para confirmar
    que o mTLS com o certificado do usuario esta funcionando."""
    with _arquivos_cert_temporarios(cert_pem, key_pem) as (cert_path, key_path):
        client = _client_mtls(GNRE_CONFIG_UF_URL, cert_path, key_path)
        operacoes = list(_operacoes_do_client(client).keys())
        return {"ok": True, "operacoes_disponiveis": operacoes}


# Nomes de parametro candidatos, para quando a operacao exige um argumento
# nomeado em vez de posicional -- outro detalhe que so da pra confirmar com
# uma chamada real (o WSDL exige mTLS pra ser inspecionado).
_NOMES_PARAMETRO_CANDIDATOS = ("arquivoXML", "nfeDadosMsg", "xml", "arquivo", "dadosMsg", "mensagemXML")


def _chamar_operacao(operacao, xml_elemento):
    """xml_elemento deve ser um lxml.etree._Element -- o parametro de entrada
    e um xsd:any no WSDL, que o zeep so aceita como Element/dict/AnyObject,
    nunca como string (confirmado por erro real: "Any element received
    object of type 'str'...")."""
    try:
        return operacao(xml_elemento)
    except TypeError:
        for nome_param in _NOMES_PARAMETRO_CANDIDATOS:
            try:
                return operacao(**{nome_param: xml_elemento})
            except TypeError:
                continue
        raise


def enviar_lote(xml_lote: bytes, cert_pem: bytes, key_pem: bytes) -> ResultadoEnvioLote:
    with _arquivos_cert_temporarios(cert_pem, key_pem) as (cert_path, key_path):
        client = _client_mtls(GNRE_LOTE_RECEPCAO_URL, cert_path, key_path)
        operacao = _resolver_operacao(client, OPERACOES_ENVIO_CANDIDATAS)
        elemento_xml = etree.fromstring(xml_lote)
        resposta = _chamar_operacao(operacao, elemento_xml)
        resposta_texto = str(resposta)
        return ResultadoEnvioLote(protocolo=_extrair_numero_recibo(resposta_texto), resposta_bruta=resposta_texto)


def _extrair_numero_recibo(resposta_texto: str) -> str | None:
    try:
        root = etree.fromstring(resposta_texto.encode("utf-8"))
    except etree.XMLSyntaxError:
        return None
    found = root.xpath(".//*[local-name()='numeroRecibo']")
    return found[0].text if found else None


def consultar_resultado_lote(protocolo: str, cert_pem: bytes, key_pem: bytes) -> ResultadoConsultaLote:
    with _arquivos_cert_temporarios(cert_pem, key_pem) as (cert_path, key_path):
        client = _client_mtls(GNRE_RESULTADO_LOTE_URL, cert_path, key_path)
        operacao = _resolver_operacao(client, OPERACOES_RESULTADO_CANDIDATAS)
        resposta = _chamar_operacao_protocolo(operacao, protocolo)
        resposta_texto = str(resposta)
        return _parsear_resultado_lote(resposta_texto)


_NOMES_PARAMETRO_PROTOCOLO_CANDIDATOS = ("numeroRecibo", "protocolo", "recibo", "nfeRecibo")


def _chamar_operacao_protocolo(operacao, protocolo: str):
    """Ainda nao testado contra o servico real -- se a operacao "processar"
    do GnreResultadoLote tambem exigir um xsd:any (como a do GnreLoteRecepcao
    exigiu), o protocolo provavelmente precisa ir dentro de um XML de
    consulta em vez de string solta. Ajustar aqui igual foi feito em
    enviar_lote() se o erro "Any element received object of type 'str'"
    aparecer tambem nesta chamada."""
    try:
        return operacao(protocolo)
    except TypeError:
        for nome_param in _NOMES_PARAMETRO_PROTOCOLO_CANDIDATOS:
            try:
                return operacao(**{nome_param: protocolo})
            except TypeError:
                continue
        raise


def _parsear_resultado_lote(resposta_texto: str) -> ResultadoConsultaLote:
    """Estrutura conferida contra o XSD oficial TResultLote_GNRE
    (app/schemas/lote_gnre_result_v2.00.xsd). Usa xpath por local-name() para
    ser tolerante ao namespace/wrapper exato que o zeep devolver."""
    situacao_codigo = None
    situacao_descricao = None
    guias: list[GuiaResultado] = []

    try:
        root = etree.fromstring(resposta_texto.encode("utf-8"))
    except etree.XMLSyntaxError:
        return ResultadoConsultaLote(None, None, [], resposta_texto)

    def first(el, local_name):
        found = el.xpath(f"./*[local-name()='{local_name}']")
        return found[0] if found else None

    proc_matches = root.xpath(".//*[local-name()='situacaoProcess']")
    proc = proc_matches[0] if proc_matches else None
    if proc is not None:
        codigo_el = first(proc, "codigo")
        desc_el = first(proc, "descricao")
        situacao_codigo = codigo_el.text if codigo_el is not None else None
        situacao_descricao = desc_el.text if desc_el is not None else None

    for guia_el in root.xpath(".//*[local-name()='guia']"):
        situacao_el = first(guia_el, "situacaoGuia")
        valor_el = first(guia_el, "valorGNRE")
        linha_el = first(guia_el, "linhaDigitavel")
        cod_barras_el = first(guia_el, "codigoBarras")

        motivos = []
        for motivo_el in guia_el.xpath(".//*[local-name()='motivo']"):
            cod_el = first(motivo_el, "codigo")
            desc_el = first(motivo_el, "descricao")
            motivos.append(
                {
                    "codigo": cod_el.text if cod_el is not None else None,
                    "descricao": desc_el.text if desc_el is not None else None,
                }
            )

        guias.append(
            GuiaResultado(
                situacao=situacao_el.text if situacao_el is not None else None,
                valor_gnre=float(valor_el.text) if valor_el is not None and valor_el.text else None,
                linha_digitavel=linha_el.text if linha_el is not None else None,
                codigo_barras=cod_barras_el.text if cod_barras_el is not None else None,
                motivos_rejeicao=motivos,
            )
        )

    return ResultadoConsultaLote(
        situacao_processo_codigo=situacao_codigo,
        situacao_processo_descricao=situacao_descricao,
        guias=guias,
        resposta_bruta=resposta_texto,
    )
