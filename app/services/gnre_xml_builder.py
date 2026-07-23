"""Monta o XML de lote da GNRE (TLote_GNRE v2.00) para guias de DIFAL/FCP de
venda interestadual a consumidor final nao contribuinte (EC 87/2015), e valida
o resultado contra o XSD oficial vendorizado em app/schemas/.

Estrutura e enumeracoes conferidas contra o XSD oficial v2.00 (vendorizado a
partir do projeto open-source nfephp-org/sped-gnre, que implementa este mesmo
webservice em producao):
  TLote_GNRE > guias > TDadosGNRE[versao=2.00] > ufFavorecida, tipoGnre,
  contribuinteEmitente{identificacao, razaoSocial, endereco, municipio, uf,
  cep, telefone}, itensGNRE > item[]{receita, documentoOrigem, referencia,
  dataVencimento, valor[tipo=11|12|21|22|31|32|41|42|51|52], convenio,
  contribuinteDestinatario, numeroControle, numeroControleFecp}

Codigos de receita usados (confirmados via pesquisa, nao suposicao):
  100102 = DIFAL por operacao       100110 = DIFAL apuracao mensal
  100129 = FCP por operacao         100137 = FCP apuracao mensal

ATENCAO / suposicao a validar antes de ir para producao: o atributo `tipo` de
`documentoOrigem` (2 digitos) nao veio explicitado no XSD com sua tabela de
valores. Usamos "01" (convencao comum para "chave de NF-e" em varias
integracoes GNRE) — confirme via GnreConfigUF para a UF de destino real antes
do primeiro envio; se estiver errado, a SEFAZ rejeita o lote com uma mensagem
de erro clara (falha segura, nao gera guia com dado errado).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from lxml import etree

GNRE_NS = "http://www.gnre.pe.gov.br"
NSMAP = {None: GNRE_NS}

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

RECEITA_DIFAL_POR_OPERACAO = "100102"
RECEITA_DIFAL_APURACAO_MENSAL = "100110"
RECEITA_FCP_POR_OPERACAO = "100129"
RECEITA_FCP_APURACAO_MENSAL = "100137"

TIPO_DOC_ORIGEM_NFE = "01"  # suposicao a confirmar, ver aviso no docstring do modulo

VALOR_TIPO_PRINCIPAL_ICMS = "11"
VALOR_TIPO_PRINCIPAL_FCP = "12"


class GnreXmlValidationError(Exception):
    pass


@dataclass
class ContribuinteEmitente:
    cnpj: str
    razao_social: str
    endereco: str | None = None
    municipio_ibge: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None


@dataclass
class ContribuinteDestinatario:
    documento: str  # CPF (11 digitos) ou CNPJ (14 digitos)
    nome: str | None = None
    municipio_ibge: str | None = None


@dataclass
class GuiaParaEmitir:
    uf_destino: str
    chave_nfe: str
    valor_difal: float
    valor_fcp: float
    destinatario: ContribuinteDestinatario
    data_vencimento: date
    numero_controle: str | None = None


def _sub(parent, tag, text=None):
    el = etree.SubElement(parent, f"{{{GNRE_NS}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _municipio_gnre(codigo_ibge: str) -> str:
    """O TCodMunIBGE da GNRE usa apenas os 5 digitos especificos do municipio,
    sem o prefixo de 2 digitos da UF que o cMun de 7 digitos da NF-e carrega
    (ex.: NF-e '3550308' -> GNRE '50308'). A UF ja vai em campo separado."""
    if len(codigo_ibge) == 7:
        return codigo_ibge[2:]
    return codigo_ibge


def _identificacao(parent, documento: str):
    ident = _sub(parent, "identificacao")
    if len(documento) == 14:
        _sub(ident, "CNPJ", documento)
    elif len(documento) == 11:
        _sub(ident, "CPF", documento)
    else:
        raise GnreXmlValidationError(f"Documento de identificacao invalido (nem CPF nem CNPJ): '{documento}'")
    return ident


def _montar_item_difal(itens_el, guia: GuiaParaEmitir):
    item = _sub(itens_el, "item")
    _sub(item, "receita", RECEITA_DIFAL_POR_OPERACAO)
    doc_origem = etree.SubElement(item, f"{{{GNRE_NS}}}documentoOrigem")
    doc_origem.set("tipo", TIPO_DOC_ORIGEM_NFE)
    doc_origem.text = guia.chave_nfe
    _sub(item, "dataVencimento", guia.data_vencimento.isoformat())
    valor = etree.SubElement(item, f"{{{GNRE_NS}}}valor")
    valor.set("tipo", VALOR_TIPO_PRINCIPAL_ICMS)
    valor.text = f"{guia.valor_difal:.2f}"

    dest = _sub(item, "contribuinteDestinatario")
    _identificacao(dest, guia.destinatario.documento)
    if guia.destinatario.nome:
        _sub(dest, "razaoSocial", guia.destinatario.nome[:60])
    if guia.destinatario.municipio_ibge:
        _sub(dest, "municipio", _municipio_gnre(guia.destinatario.municipio_ibge))

    if guia.numero_controle:
        _sub(item, "numeroControle", guia.numero_controle)


def _montar_item_fcp(itens_el, guia: GuiaParaEmitir):
    item = _sub(itens_el, "item")
    _sub(item, "receita", RECEITA_FCP_POR_OPERACAO)
    doc_origem = etree.SubElement(item, f"{{{GNRE_NS}}}documentoOrigem")
    doc_origem.set("tipo", TIPO_DOC_ORIGEM_NFE)
    doc_origem.text = guia.chave_nfe
    _sub(item, "dataVencimento", guia.data_vencimento.isoformat())
    valor = etree.SubElement(item, f"{{{GNRE_NS}}}valor")
    valor.set("tipo", VALOR_TIPO_PRINCIPAL_FCP)
    valor.text = f"{guia.valor_fcp:.2f}"

    dest = _sub(item, "contribuinteDestinatario")
    _identificacao(dest, guia.destinatario.documento)
    if guia.destinatario.nome:
        _sub(dest, "razaoSocial", guia.destinatario.nome[:60])
    if guia.destinatario.municipio_ibge:
        _sub(dest, "municipio", _municipio_gnre(guia.destinatario.municipio_ibge))

    if guia.numero_controle:
        _sub(item, "numeroControleFecp", guia.numero_controle)


def montar_dados_gnre(parent_guias, empresa: ContribuinteEmitente, guia: GuiaParaEmitir):
    if len(guia.chave_nfe) != 44:
        raise GnreXmlValidationError(f"Chave de NF-e invalida: '{guia.chave_nfe}' (esperado 44 digitos).")
    if guia.valor_difal <= 0 and guia.valor_fcp <= 0:
        raise GnreXmlValidationError("Guia sem valor de DIFAL nem de FCP -- nada a emitir.")

    tem_fcp = guia.valor_fcp > 0
    tipo_gnre = "2" if tem_fcp else "0"  # 0=simples, 2=multiplas receitas

    dados = etree.SubElement(parent_guias, f"{{{GNRE_NS}}}TDadosGNRE")
    dados.set("versao", "2.00")

    _sub(dados, "ufFavorecida", guia.uf_destino)
    _sub(dados, "tipoGnre", tipo_gnre)

    contrib = _sub(dados, "contribuinteEmitente")
    _identificacao(contrib, empresa.cnpj)
    _sub(contrib, "razaoSocial", empresa.razao_social[:60])
    if empresa.endereco:
        _sub(contrib, "endereco", empresa.endereco[:60])
    if empresa.municipio_ibge:
        _sub(contrib, "municipio", _municipio_gnre(empresa.municipio_ibge))
    if empresa.uf:
        _sub(contrib, "uf", empresa.uf)
    if empresa.cep:
        _sub(contrib, "cep", empresa.cep)
    if empresa.telefone:
        _sub(contrib, "telefone", empresa.telefone)

    itens_el = _sub(dados, "itensGNRE")
    if guia.valor_difal > 0:
        _montar_item_difal(itens_el, guia)
    if tem_fcp:
        _montar_item_fcp(itens_el, guia)

    return dados


def montar_lote_xml(empresa: ContribuinteEmitente, guias: list[GuiaParaEmitir]) -> bytes:
    if not guias:
        raise GnreXmlValidationError("Lote sem nenhuma guia para emitir.")
    if len(guias) > 50:
        raise GnreXmlValidationError(f"Lote com {len(guias)} guias excede o maximo de 50 permitido pelo Portal GNRE.")

    lote = etree.Element(f"{{{GNRE_NS}}}TLote_GNRE", nsmap=NSMAP)
    lote.set("versao", "2.00")
    guias_el = _sub(lote, "guias")

    for guia in guias:
        montar_dados_gnre(guias_el, empresa, guia)

    xml_bytes = etree.tostring(lote, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    validar_contra_xsd(xml_bytes)
    return xml_bytes


@lru_cache(maxsize=1)
def _xsd_schema() -> etree.XMLSchema:
    schema_doc = etree.parse(str(SCHEMAS_DIR / "lote_gnre_v2.00.xsd"))
    return etree.XMLSchema(schema_doc)


def validar_contra_xsd(xml_bytes: bytes) -> None:
    schema = _xsd_schema()
    doc = etree.fromstring(xml_bytes)
    if not schema.validate(doc):
        erros = "; ".join(str(e) for e in schema.error_log)
        raise GnreXmlValidationError(f"XML de lote GNRE nao passou na validacao do XSD: {erros}")
