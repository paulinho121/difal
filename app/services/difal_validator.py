"""Recalcula DIFAL/FCP de forma independente a partir da tabela de aliquotas
internas (app/data/aliquotas_internas.json) e compara com o que o emitente ja
declarou no grupo ICMSUFDest da NF-e (fonte primaria/autoritativa, pois foi o
valor efetivamente autorizado pela SEFAZ). Diferencas acima da tolerancia sao
sinalizadas para revisao manual antes de qualquer emissao de guia.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.paths import arquivo_editavel
from app.services import base_dupla
from app.services.nfe_parser import ItemICMSUFDest, ParsedNFe

DATA_PATH = arquivo_editavel("aliquotas_internas.json")


@lru_cache(maxsize=1)
def _tabela() -> dict:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Confirmado pelo proprio GNRE (guia real recusada com 201 "Esta UF nao gera GNRE online").
# Fica no codigo (nao no JSON editavel) para valer em toda atualizacao do programa.
UFS_SEM_GNRE_ONLINE = {
    "SP": "O GNRE nao gera guia online para SP (erro 201 do proprio GNRE). "
    "O DIFAL para SP deve ser recolhido pela guia da SEFAZ-SP (GARE-ICMS), fora deste programa.",
    # O GnreConfigUF devolve para o ES a mesma resposta que devolve para SP: codigo 999
    # "UF nao habilitada neste ambiente" (conferido ao vivo, sem receita e com a 100102).
    "ES": "O GNRE informa que o ES nao esta habilitado para gerar guia online (codigo 999 \"UF nao habilitada "
    "neste ambiente\", a mesma resposta dada para SP). O DIFAL para ES deve ser recolhido pela guia da "
    "propria SEFAZ-ES, fora deste programa.",
}


def mensagem_uf_sem_gnre_online(uf: str | None) -> str | None:
    return UFS_SEM_GNRE_ONLINE.get(uf or "")


def uf_suportada_gnre_nacional(uf: str | None) -> bool:
    if not uf:
        return True
    return uf not in _tabela()["ufs_sem_gnre_nacional"]["lista"]


@dataclass
class ValidacaoItem:
    numero_item: int
    aplica_difal: bool
    aliquota_interna_usada: float | None = None
    valor_difal_final: float = 0.0
    valor_fcp_final: float = 0.0
    divergente: bool = False
    avisos: list[str] = field(default_factory=list)


@dataclass
class ValidacaoNota:
    uf_destino: str | None
    uf_suportada: bool
    itens: list[ValidacaoItem]
    valor_difal_total: float
    valor_fcp_total: float
    divergente: bool
    metodo: str = "declarado"  # "declarado" (valor da NF-e) | "base_dupla" (planilha)
    erro_calculo: str | None = None  # com valor, a guia NAO pode ser emitida
    avisos: list[str] = field(default_factory=list)


def _recalcular_item(item: ItemICMSUFDest, aliquota_interna: float | None, fcp_padrao: float | None, tolerancia_pct: float) -> ValidacaoItem:
    if not item.tem_difal_declarado:
        return ValidacaoItem(numero_item=item.numero_item, aplica_difal=False)

    avisos: list[str] = []
    divergente = False

    difal_recalc = None
    if aliquota_interna is not None and item.v_bc_uf_dest is not None and item.p_icms_inter is not None:
        partilha = (item.p_icms_inter_part if item.p_icms_inter_part is not None else 100.0) / 100.0
        difal_recalc = round(item.v_bc_uf_dest * (aliquota_interna / 100 - item.p_icms_inter / 100) * partilha, 2)
    else:
        avisos.append(
            f"Sem aliquota interna cadastrada (ou dados insuficientes) para conferir o DIFAL do item {item.numero_item}."
        )

    valor_difal_final = item.v_icms_uf_dest or 0.0
    if difal_recalc is not None:
        base_compare = max(abs(valor_difal_final), 0.01)
        diff_pct = abs(difal_recalc - valor_difal_final) / base_compare * 100
        if diff_pct > tolerancia_pct:
            divergente = True
            avisos.append(
                f"Item {item.numero_item}: DIFAL declarado na NF-e (R$ {valor_difal_final:.2f}) diverge do "
                f"recalculo interno (R$ {difal_recalc:.2f}, aliquota interna {aliquota_interna:.2f}%) em {diff_pct:.1f}%."
            )

    base_fcp = item.v_bc_fcp_uf_dest if item.v_bc_fcp_uf_dest is not None else item.v_bc_uf_dest
    fcp_recalc = None
    if fcp_padrao is not None and base_fcp is not None:
        fcp_recalc = round(base_fcp * fcp_padrao / 100, 2)

    valor_fcp_final = item.v_fcp_uf_dest or 0.0
    if fcp_recalc is not None:
        base_compare = max(abs(valor_fcp_final), 0.01)
        diff_pct = abs(fcp_recalc - valor_fcp_final) / base_compare * 100
        if diff_pct > tolerancia_pct:
            divergente = True
            avisos.append(
                f"Item {item.numero_item}: FCP declarado (R$ {valor_fcp_final:.2f}) diverge do recalculo "
                f"interno (R$ {fcp_recalc:.2f}, FCP padrao {fcp_padrao:.2f}%) em {diff_pct:.1f}%."
            )

    return ValidacaoItem(
        numero_item=item.numero_item,
        aplica_difal=True,
        aliquota_interna_usada=aliquota_interna,
        valor_difal_final=valor_difal_final,
        valor_fcp_final=valor_fcp_final,
        divergente=divergente,
        avisos=avisos,
    )


def _validar_base_dupla(nfe: ParsedNFe) -> ValidacaoNota:
    """Calculo da planilha de base dupla (notas emitidas por CNPJs de SP e CE). Aqui o valor
    da guia e CALCULADO a partir da nota; o ICMSUFDest da NF-e (se houver) so e comparado."""
    uf = nfe.uf_destino
    params = base_dupla.parametros_uf(uf)
    itens: list[ValidacaoItem] = []
    avisos: list[str] = []
    erros: list[str] = []

    def pronto(erro: str | None = None) -> ValidacaoNota:
        return ValidacaoNota(
            uf_destino=uf,
            uf_suportada=uf_suportada_gnre_nacional(uf),
            itens=itens,
            valor_difal_total=round(sum(i.valor_difal_final for i in itens), 2),
            valor_fcp_total=round(sum(i.valor_fcp_final for i in itens), 2),
            divergente=False,
            metodo="base_dupla",
            erro_calculo=erro,
            avisos=avisos,
        )

    if params is None:
        erros.append(f"a planilha de base dupla (base_dupla.json) nao tem a UF de destino {uf}")
    consumidor_final = nfe.ind_final == "1" or any(i.tem_difal_declarado for i in nfe.itens)
    if not consumidor_final:
        avisos.append("Nota nao marcada como venda a consumidor final (indFinal): a base dupla nao foi aplicada.")
        return pronto()

    for item in nfe.itens:
        if params is None:
            break
        p_inter = base_dupla.aliquota_interestadual(item)
        if p_inter is None:
            erros.append(
                f"item {item.numero_item}: sem aliquota interestadual de 4%, 7% ou 12% no ICMS da nota "
                f"(encontrado: {item.p_icms_origem})"
            )
            continue
        aliq_total, pct_fcp = base_dupla.taxas_do_item(params, uf, item)
        calc = base_dupla.calcular(base_dupla.valor_operacao(item), p_inter, aliq_total, pct_fcp)
        item_avisos = [
            f"Item {item.numero_item}: base dupla (planilha) - operacao R$ {calc.valor_operacao:.2f}, ICMS origem "
            f"{p_inter:g}% = R$ {calc.icms_origem:.2f}, base R$ {calc.base_calculo:.2f}, aliquota interna+FCP "
            f"{calc.aliquota_total:g}% -> DIFAL R$ {calc.difal:.2f} + FCP R$ {calc.fcp:.2f}."
        ]
        if item.tem_difal_declarado:
            declarado = round((item.v_icms_uf_dest or 0.0) + (item.v_fcp_uf_dest or 0.0), 2)
            if abs(declarado - calc.total) > 0.02:
                item_avisos.append(
                    f"Item {item.numero_item}: a NF-e declara R$ {declarado:.2f} (aliquota interna "
                    f"{item.p_icms_uf_dest if item.p_icms_uf_dest is not None else '--'}%); pela planilha de base dupla "
                    f"o valor e R$ {calc.total:.2f}. Foi usado o da planilha."
                )
        itens.append(
            ValidacaoItem(
                numero_item=item.numero_item,
                aplica_difal=True,
                aliquota_interna_usada=calc.aliquota_total,
                valor_difal_final=calc.difal,
                valor_fcp_final=calc.fcp,
                avisos=item_avisos,
            )
        )
    return pronto("Nao foi possivel calcular a base dupla: " + "; ".join(erros) + "." if erros else None)


def validar_nota(nfe: ParsedNFe) -> ValidacaoNota:
    if base_dupla.aplica(nfe.uf_origem, nfe.uf_destino):
        return _validar_base_dupla(nfe)
    tabela = _tabela()
    uf = nfe.uf_destino
    uf_data = tabela["ufs"].get(uf) if uf else None
    aliquota_interna = uf_data["aliquota_padrao"] if uf_data else None
    fcp_padrao = uf_data["fcp_padrao"] if uf_data else None
    tolerancia_pct = tabela["tolerancia_divergencia_percentual"]

    itens_validados = [
        _recalcular_item(item, aliquota_interna, fcp_padrao, tolerancia_pct) for item in nfe.itens
    ]

    return ValidacaoNota(
        uf_destino=uf,
        uf_suportada=uf_suportada_gnre_nacional(uf),
        itens=itens_validados,
        valor_difal_total=round(sum(i.valor_difal_final for i in itens_validados), 2),
        valor_fcp_total=round(sum(i.valor_fcp_final for i in itens_validados), 2),
        divergente=any(i.divergente for i in itens_validados),
    )
