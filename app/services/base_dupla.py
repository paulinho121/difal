"""DIFAL por BASE DUPLA, conforme a planilha 'Difal base dupla' da empresa.

Usado nas notas emitidas por CNPJs das UFs de base_dupla.json (SP e CE). Nessas
notas a base do DIFAL e "por dentro": parte-se do valor da operacao, tira-se o ICMS
da origem e divide-se o resultado por (1 - aliquota interna + FCP):

    ICMS origem = valor da operacao x aliquota interestadual (4%, 7% ou 12%)
    BC destino  = (valor da operacao - ICMS origem) / (1 - aliquota interna + FCP)
    ICMS destino= BC destino x (aliquota interna + FCP)
    DIFAL       = ICMS destino - ICMS origem

Valor da operacao = produto + IPI + frete + seguro + outras despesas - desconto
(na planilha, a linha do RS com R$ 6.416,89 e o vNF da nota 2705).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.paths import arquivo_editavel
from app.services.nfe_parser import ItemICMSUFDest

ALIQUOTAS_INTERESTADUAIS = (4.0, 7.0, 12.0)


def _config() -> dict:
    with open(arquivo_editavel("base_dupla.json"), encoding="utf-8") as f:
        return json.load(f)


def ufs_emitente() -> set[str]:
    return {u.upper() for u in _config().get("ufs_emitente", [])}


def parametros_uf(uf: str | None) -> dict | None:
    return _config()["ufs"].get(uf) if uf else None


def aplica(uf_origem: str | None, uf_destino: str | None) -> bool:
    # "EX" = exportacao: nao ha DIFAL.
    return bool(
        uf_origem and uf_destino and uf_destino != "EX" and uf_origem != uf_destino and uf_origem in ufs_emitente()
    )


def fcp_adicional_por_ncm(uf: str | None, ncm: str | None) -> float:
    """FECOP que a planilha anota para NCMs especificos (ex.: 9405 na PB, +2%)."""
    for prefixo, pct in _config().get("fcp_adicional_por_ncm", {}).get(uf or "", {}).items():
        if ncm and ncm.startswith(prefixo):
            return float(pct)
    return 0.0


def taxas_do_item(params: dict, uf: str, item: ItemICMSUFDest) -> tuple[float, float]:
    """(aliquota total, percentual de FCP) do item. A aliquota_total da planilha ja traz o
    FCP fixo da UF; se a NF-e declara (pFCPUFDest) ou a planilha anota (NCM) um FCP MAIOR,
    a diferenca e somada por cima, como a planilha manda fazer ('incluir na coluna F')."""
    base_fcp = float(params["fcp"])
    declarado = item.p_fcp_uf_dest if item.tem_difal_declarado and item.p_fcp_uf_dest is not None else 0.0
    pct_fcp = max(base_fcp, declarado, fcp_adicional_por_ncm(uf, item.ncm))
    return round(float(params["aliquota_total"]) + (pct_fcp - base_fcp), 4), pct_fcp


def valor_operacao(item: ItemICMSUFDest) -> float:
    return item.v_prod + item.v_ipi + item.v_frete + item.v_seg + item.v_outro - item.v_desc


def aliquota_interestadual(item: ItemICMSUFDest) -> float | None:
    """ICMS destacado na nota (planilha, coluna C); sem ele, a declarada no ICMSUFDest."""
    for candidata in (item.p_icms_origem, item.p_icms_inter):
        if candidata is not None and any(abs(candidata - a) < 0.005 for a in ALIQUOTAS_INTERESTADUAIS):
            return round(candidata, 2)
    return None


@dataclass
class CalculoBaseDupla:
    valor_operacao: float
    aliquota_interestadual: float
    aliquota_total: float
    percentual_fcp: float
    icms_origem: float
    base_calculo: float
    difal: float
    fcp: float

    @property
    def total(self) -> float:
        return round(self.difal + self.fcp, 2)


def calcular(valor_op: float, aliq_interestadual: float, aliq_total: float, pct_fcp: float) -> CalculoBaseDupla:
    origem = valor_op * aliq_interestadual / 100
    base = (valor_op - origem) / (1 - aliq_total / 100)
    total = round(base * aliq_total / 100 - origem, 2)
    fcp = min(round(base * pct_fcp / 100, 2), total)
    return CalculoBaseDupla(
        valor_operacao=round(valor_op, 2),
        aliquota_interestadual=aliq_interestadual,
        aliquota_total=aliq_total,
        percentual_fcp=pct_fcp,
        icms_origem=round(origem, 2),
        base_calculo=round(base, 2),
        difal=round(total - fcp, 2),
        fcp=fcp,
    )
