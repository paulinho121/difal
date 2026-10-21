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

As exigencias que variam por UF/receita (tipo do documento de origem -- 24 =
CHAVE DO DFe no RJ --, FCP no mesmo item ou em receita propria, data prevista
de pagamento, campos extras, produto) vem do GnreConfigUF via
app/services/gnre_regras.py; sem a consulta, usa os defaults do RJ/100102,
confirmados ao vivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from lxml import etree

from app.services.gnre_regras import RegrasReceita
from app.services.nfe_parser import ParsedNFe

GNRE_NS = "http://www.gnre.pe.gov.br"
NSMAP = {None: GNRE_NS}

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

RECEITA_DIFAL_POR_OPERACAO = "100102"
RECEITA_DIFAL_APURACAO_MENSAL = "100110"
RECEITA_FCP_POR_OPERACAO = "100129"
RECEITA_FCP_APURACAO_MENSAL = "100137"

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
    data_emissao: date | None = None  # da NF-e; alguns campos extras exigem
    data_pagamento: date | None = None  # data prevista de pagamento (GNRE calcula juros/multa)
    regras: RegrasReceita = field(default_factory=RegrasReceita)


def contribuinte_emitente_da_nfe(nfe: ParsedNFe) -> ContribuinteEmitente | None:
    """O debito do DIFAL e de quem fez a venda -- a filial que emitiu a NF-e,
    nao necessariamente o CNPJ do certificado digital (que pode ser o da
    matriz, usado para autenticar todas as filiais). Retorna None se a nota
    nao trouxer CNPJ/nome do emitente (o chamador usa a empresa cadastrada)."""
    if not nfe.emitente_cnpj or not nfe.emitente_nome:
        return None

    endereco = " ".join(p for p in (nfe.emitente_logradouro, nfe.emitente_numero) if p) or None
    telefone = "".join(c for c in (nfe.emitente_telefone or "") if c.isdigit())
    cep = "".join(c for c in (nfe.emitente_cep or "") if c.isdigit())
    return ContribuinteEmitente(
        cnpj=nfe.emitente_cnpj,
        razao_social=" ".join(nfe.emitente_nome.split()),
        endereco=endereco,
        municipio_ibge=nfe.emitente_municipio_ibge,
        uf=nfe.uf_origem,
        cep=cep if len(cep) == 8 else None,
        telefone=telefone if 6 <= len(telefone) <= 11 else None,
    )


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


def _valor_campo_extra(campo, guia: GuiaParaEmitir) -> str:
    titulo = campo.titulo.lower()
    if "emiss" in titulo:  # "Data de Emissao" (tolera acento corrompido)
        if guia.data_emissao is None:
            raise GnreXmlValidationError("A UF exige a data de emissao da NF-e, mas ela nao foi informada.")
        return guia.data_emissao.isoformat()
    if "complementares" in titulo:
        return f"NF-e {guia.numero_controle or ''}".strip()[:100]
    raise GnreXmlValidationError(
        f"A UF exige o campo extra {campo.codigo} (\"{campo.titulo}\"), que o sistema ainda nao sabe preencher."
    )


def _montar_item(itens_el, guia: GuiaParaEmitir, receita: str, valores: list[tuple[str, float]], tag_controle: str):
    regras = guia.regras
    item = _sub(itens_el, "item")
    _sub(item, "receita", receita)
    if regras.detalhamento_receita:
        _sub(item, "detalhamentoReceita", regras.detalhamento_receita)
    doc_origem = etree.SubElement(item, f"{{{GNRE_NS}}}documentoOrigem")
    doc_origem.set("tipo", regras.doc_origem_tipo)
    doc_origem.text = guia.chave_nfe
    if regras.produto:
        _sub(item, "produto", regras.produto)
    if regras.exige_referencia:
        if guia.data_emissao is None:
            raise GnreXmlValidationError("A UF exige periodo de referencia, mas a data de emissao nao foi informada.")
        ref = _sub(item, "referencia")
        _sub(ref, "periodo", "0")
        _sub(ref, "mes", f"{guia.data_emissao.month:02d}")
        _sub(ref, "ano", str(guia.data_emissao.year))
    _sub(item, "dataVencimento", guia.data_vencimento.isoformat())
    for tipo, valor in valores:
        el = etree.SubElement(item, f"{{{GNRE_NS}}}valor")
        el.set("tipo", tipo)
        el.text = f"{valor:.2f}"

    dest = _sub(item, "contribuinteDestinatario")
    _identificacao(dest, guia.destinatario.documento)
    if guia.destinatario.nome:
        _sub(dest, "razaoSocial", guia.destinatario.nome[:60].strip())
    if guia.destinatario.municipio_ibge:
        _sub(dest, "municipio", _municipio_gnre(guia.destinatario.municipio_ibge))

    obrigatorios = [c for c in regras.campos_extras if c.obrigatorio]
    if obrigatorios:
        extras = _sub(item, "camposExtras")
        for campo in obrigatorios[:3]:
            ce = _sub(extras, "campoExtra")
            _sub(ce, "codigo", str(campo.codigo))
            _sub(ce, "valor", _valor_campo_extra(campo, guia))

    if guia.numero_controle:
        _sub(item, tag_controle, guia.numero_controle)


def montar_dados_gnre(parent_guias, empresa: ContribuinteEmitente, guia: GuiaParaEmitir):
    if len(guia.chave_nfe) != 44:
        raise GnreXmlValidationError(f"Chave de NF-e invalida: '{guia.chave_nfe}' (esperado 44 digitos).")
    if guia.valor_difal <= 0 and guia.valor_fcp <= 0:
        raise GnreXmlValidationError("Guia sem valor de DIFAL nem de FCP -- nada a emitir.")
    regras = guia.regras
    if regras.pendencias:
        raise GnreXmlValidationError(
            f"A UF {guia.uf_destino} exige algo que o sistema ainda nao sabe preencher: " + "; ".join(regras.pendencias)
        )
    if regras.exige_data_pagamento and guia.data_pagamento is None:
        raise GnreXmlValidationError("A UF exige a data prevista de pagamento, mas ela nao foi informada.")

    tem_fcp = guia.valor_fcp > 0
    fcp_separado = tem_fcp and not regras.fecp_no_mesmo_item
    tipo_gnre = "2" if fcp_separado else "0"  # 0=simples, 2=multiplas receitas

    dados = etree.SubElement(parent_guias, f"{{{GNRE_NS}}}TDadosGNRE")
    dados.set("versao", "2.00")

    _sub(dados, "ufFavorecida", guia.uf_destino)
    _sub(dados, "tipoGnre", tipo_gnre)

    contrib = _sub(dados, "contribuinteEmitente")
    _identificacao(contrib, empresa.cnpj)
    _sub(contrib, "razaoSocial", empresa.razao_social[:60].strip())
    if empresa.endereco:
        _sub(contrib, "endereco", empresa.endereco[:60].strip())
    if empresa.municipio_ibge:
        _sub(contrib, "municipio", _municipio_gnre(empresa.municipio_ibge))
    if empresa.uf:
        _sub(contrib, "uf", empresa.uf)
    if empresa.cep:
        _sub(contrib, "cep", empresa.cep)
    if empresa.telefone:
        _sub(contrib, "telefone", empresa.telefone)

    itens_el = _sub(dados, "itensGNRE")
    valores_icms = [(VALOR_TIPO_PRINCIPAL_ICMS, guia.valor_difal)] if guia.valor_difal > 0 else []
    if fcp_separado:
        # UF com receita propria para o FCP (ex.: 100129): item separado.
        if valores_icms:
            _montar_item(itens_el, guia, RECEITA_DIFAL_POR_OPERACAO, valores_icms, "numeroControle")
        _montar_item(
            itens_el, guia, RECEITA_FCP_POR_OPERACAO, [(VALOR_TIPO_PRINCIPAL_FCP, guia.valor_fcp)], "numeroControleFecp"
        )
    else:
        # FCP no mesmo item da receita do DIFAL (valor tipo 12), como o RJ exige.
        valores = valores_icms + ([(VALOR_TIPO_PRINCIPAL_FCP, guia.valor_fcp)] if tem_fcp else [])
        _montar_item(itens_el, guia, RECEITA_DIFAL_POR_OPERACAO, valores, "numeroControle")

    if regras.exige_data_pagamento:
        _sub(dados, "dataPagamento", guia.data_pagamento.isoformat())

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
