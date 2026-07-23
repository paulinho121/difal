"""Extrai os dados relevantes de uma NF-e (venda interestadual a consumidor final
não contribuinte) necessários para o DIFAL: emitente, destinatário e, por item,
o grupo ICMSUFDest já declarado pelo emitente na nota autorizada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
NS = {"nfe": NFE_NS}


class NFeParseError(Exception):
    pass


@dataclass
class ItemICMSUFDest:
    numero_item: int
    ncm: str | None
    cfop: str | None
    v_prod: float
    v_bc_uf_dest: float | None = None
    v_bc_fcp_uf_dest: float | None = None
    p_fcp_uf_dest: float | None = None
    p_icms_uf_dest: float | None = None
    p_icms_inter: float | None = None
    p_icms_inter_part: float | None = None
    v_fcp_uf_dest: float | None = None
    v_icms_uf_dest: float | None = None
    v_icms_uf_remet: float | None = None

    @property
    def tem_difal_declarado(self) -> bool:
        return self.v_icms_uf_dest is not None


@dataclass
class ParsedNFe:
    chave_acesso: str
    numero: str | None
    serie: str | None
    data_emissao: datetime | None
    emitente_cnpj: str | None
    uf_origem: str | None
    destinatario_doc: str | None
    destinatario_nome: str | None
    uf_destino: str | None
    municipio_destino_ibge: str | None
    valor_total_produtos: float
    valor_total_nota: float
    itens: list[ItemICMSUFDest] = field(default_factory=list)


def _text(el, path: str) -> str | None:
    found = el.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def _float(el, path: str) -> float | None:
    txt = _text(el, path)
    if txt is None:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def parse_nfe_xml(xml_bytes: bytes) -> ParsedNFe:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise NFeParseError(f"XML inválido: {exc}") from exc

    inf_nfe = root.find(".//nfe:infNFe", NS)
    if inf_nfe is None:
        raise NFeParseError("Elemento <infNFe> não encontrado — este arquivo não parece ser uma NF-e.")

    chave_attr = inf_nfe.get("Id", "")
    chave_acesso = chave_attr.replace("NFe", "").strip()
    if not chave_acesso:
        prot = root.find(".//nfe:protNFe/nfe:infProt/nfe:chNFe", NS)
        chave_acesso = prot.text.strip() if prot is not None and prot.text else ""
    if len(chave_acesso) != 44:
        raise NFeParseError(f"Chave de acesso inválida ou ausente (encontrado: '{chave_acesso}').")

    ide = inf_nfe.find("nfe:ide", NS)
    emit = inf_nfe.find("nfe:emit", NS)
    dest = inf_nfe.find("nfe:dest", NS)
    total = inf_nfe.find("nfe:total/nfe:ICMSTot", NS)

    numero = _text(ide, "nfe:nNF") if ide is not None else None
    serie = _text(ide, "nfe:serie") if ide is not None else None
    dh_emi = _text(ide, "nfe:dhEmi") if ide is not None else None
    data_emissao = None
    if dh_emi:
        try:
            data_emissao = datetime.fromisoformat(dh_emi)
        except ValueError:
            data_emissao = None

    emitente_cnpj = _text(emit, "nfe:CNPJ") if emit is not None else None
    uf_origem = _text(emit, "nfe:enderEmit/nfe:UF") if emit is not None else None

    destinatario_doc = None
    destinatario_nome = None
    uf_destino = None
    municipio_destino_ibge = None
    if dest is not None:
        destinatario_doc = _text(dest, "nfe:CPF") or _text(dest, "nfe:CNPJ")
        destinatario_nome = _text(dest, "nfe:xNome")
        uf_destino = _text(dest, "nfe:enderDest/nfe:UF")
        municipio_destino_ibge = _text(dest, "nfe:enderDest/nfe:cMun")

    valor_total_produtos = _float(total, "nfe:vProd") or 0.0 if total is not None else 0.0
    valor_total_nota = _float(total, "nfe:vNF") or 0.0 if total is not None else 0.0

    itens: list[ItemICMSUFDest] = []
    for det in inf_nfe.findall("nfe:det", NS):
        numero_item = int(det.get("nItem", "0"))
        prod = det.find("nfe:prod", NS)
        ncm = _text(prod, "nfe:NCM") if prod is not None else None
        cfop = _text(prod, "nfe:CFOP") if prod is not None else None
        v_prod = _float(prod, "nfe:vProd") or 0.0 if prod is not None else 0.0

        # ICMSUFDest é filho direto de <imposto>, irmão de <ICMS> (que por sua
        # vez contém o grupo do CST: ICMS00, ICMS10, ICMSSN102...). Confirmado
        # contra uma NF-e real autorizada pela SEFAZ (nao fica aninhado dentro
        # de <ICMS> como uma fonte secundaria consultada anteriormente indicava).
        icms_uf_dest = det.find("nfe:imposto/nfe:ICMSUFDest", NS)

        item = ItemICMSUFDest(
            numero_item=numero_item,
            ncm=ncm,
            cfop=cfop,
            v_prod=v_prod,
        )
        if icms_uf_dest is not None:
            item.v_bc_uf_dest = _float(icms_uf_dest, "nfe:vBCUFDest")
            item.v_bc_fcp_uf_dest = _float(icms_uf_dest, "nfe:vBCFCPUFDest")
            item.p_fcp_uf_dest = _float(icms_uf_dest, "nfe:pFCPUFDest")
            item.p_icms_uf_dest = _float(icms_uf_dest, "nfe:pICMSUFDest")
            item.p_icms_inter = _float(icms_uf_dest, "nfe:pICMSInter")
            item.p_icms_inter_part = _float(icms_uf_dest, "nfe:pICMSInterPart")
            item.v_fcp_uf_dest = _float(icms_uf_dest, "nfe:vFCPUFDest")
            item.v_icms_uf_dest = _float(icms_uf_dest, "nfe:vICMSUFDest")
            item.v_icms_uf_remet = _float(icms_uf_dest, "nfe:vICMSUFRemet")
        itens.append(item)

    return ParsedNFe(
        chave_acesso=chave_acesso,
        numero=numero,
        serie=serie,
        data_emissao=data_emissao,
        emitente_cnpj=emitente_cnpj,
        uf_origem=uf_origem,
        destinatario_doc=destinatario_doc,
        destinatario_nome=destinatario_nome,
        uf_destino=uf_destino,
        municipio_destino_ibge=municipio_destino_ibge,
        valor_total_produtos=valor_total_produtos,
        valor_total_nota=valor_total_nota,
        itens=itens,
    )
