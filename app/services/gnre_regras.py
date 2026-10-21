"""Regras de preenchimento da GNRE por UF/receita, lidas do servico oficial
GnreConfigUF (TConfigUf). Cada UF exige coisas diferentes (tipo do documento
de origem, FCP no mesmo item ou em receita propria, campos extras, produto...),
entao o lote e montado conforme o que o GNRE informa, e nao com suposicoes.

Estrutura conferida contra uma resposta real do RJ/receita 100102 (fixture em
tests/fixtures/config_uf_rj_100102.xml) e contra o xsd config_uf_v1.00.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from lxml import etree

from app.services import gnre_client


@dataclass
class CampoExtraExigido:
    codigo: int
    tipo: str  # D = data, T = texto, N = numerico
    titulo: str
    obrigatorio: bool


@dataclass
class RegrasReceita:
    """Defaults = o que o RJ/100102 exige (confirmado ao vivo); usados quando a
    consulta ao GnreConfigUF nao esta disponivel."""

    doc_origem_tipo: str = "24"  # 24 = CHAVE DO DFe
    exige_data_pagamento: bool = True
    fecp_no_mesmo_item: bool = True
    exige_referencia: bool = False
    produto: str | None = None
    detalhamento_receita: str | None = None
    campos_extras: list[CampoExtraExigido] = field(
        default_factory=lambda: [CampoExtraExigido(117, "D", "Data de Emissão", True)]
    )
    # Exigencias que o sistema ainda nao sabe preencher -- o envio e barrado
    # antes, com mensagem clara, em vez de gastar uma recusa do GNRE.
    pendencias: list[str] = field(default_factory=list)


def _filho(el, nome: str):
    achados = el.xpath(f"./*[local-name()='{nome}']")
    return achados[0] if achados else None


def _texto(el, nome: str) -> str | None:
    f = _filho(el, nome)
    return f.text.strip() if f is not None and f.text else None


def _sim(el, nome: str) -> bool:
    return (_texto(el, nome) or "").upper() == "S"


def interpretar_config_uf(xml_texto: str, receita: str) -> RegrasReceita:
    raiz = etree.fromstring(xml_texto.encode("utf-8"))
    alvo = None
    for r in raiz.xpath(".//*[local-name()='receitas']/*[local-name()='receita']"):
        if r.get("codigo") == receita:
            alvo = r
            break
    if alvo is None:
        regras = RegrasReceita()
        regras.pendencias.append(f"a UF nao informou a receita {receita} no GnreConfigUF (nao aceita essa receita)")
        return regras

    regras = RegrasReceita(campos_extras=[])
    regras.exige_data_pagamento = _sim(alvo, "exigeDataPagamento")
    regras.fecp_no_mesmo_item = _sim(alvo, "exigeValorFecp")
    regras.exige_referencia = _sim(alvo, "exigePeriodoReferencia")

    # Tipo do documento de origem: prefere a chave do DF-e / NF-e.
    tipos = [
        (_texto(t, "codigo"), (_texto(t, "descricao") or "").upper())
        for t in alvo.xpath(".//*[local-name()='tipoDocumentoOrigem']")
    ]
    escolhido = next((c for c, d in tipos if "CHAVE" in d and "DFE" in d.replace("-", "")), None) or next(
        (c for c, d in tipos if "NF" in d), None
    )
    if escolhido:
        regras.doc_origem_tipo = escolhido
    elif _sim(alvo, "exigeDocumentoOrigem"):
        regras.pendencias.append("tipo de documento de origem com chave de NF-e nao oferecido pela UF")

    if _sim(alvo, "exigeProduto"):
        produtos = [(_texto(p, "codigo"), (_texto(p, "descricao") or "")) for p in alvo.xpath(".//*[local-name()='produto']")]
        outros = next((c for c, d in produtos if d.strip().lower() == "outros"), None)
        if outros:
            regras.produto = outros
        else:
            regras.pendencias.append("produto obrigatorio sem opcao \"Outros\"")

    if _sim(alvo, "exigeDetalhamentoReceita"):
        det = [_texto(d, "codigo") for d in alvo.xpath(".//*[local-name()='detalhamentoReceita']/*[local-name()='codigo']")]
        det = [d for d in det if d]
        if len(det) == 1:
            regras.detalhamento_receita = det[0]
        else:
            regras.pendencias.append("detalhamento da receita obrigatorio com varias opcoes")
    if _sim(alvo, "exigeConvenio"):
        regras.pendencias.append("convenio obrigatorio")
    if _sim(alvo, "exigeParcela"):
        regras.pendencias.append("parcela obrigatoria")

    for c in alvo.xpath(".//*[local-name()='campoAdicional']"):
        codigo = _texto(c, "codigo")
        regras.campos_extras.append(
            CampoExtraExigido(
                codigo=int(codigo) if codigo and codigo.isdigit() else -1,
                tipo=_texto(c, "tipo") or "T",
                titulo=_texto(c, "titulo") or "",
                obrigatorio=_sim(c, "obrigatorio"),
            )
        )
    return regras


# Cache em memoria por instancia (UF, receita) -> (instante, regras)
_CACHE: dict[tuple[str, str], tuple[float, RegrasReceita]] = {}
_TTL_SEGUNDOS = 3600


def obter_regras(uf: str, receita: str, cert_pem: bytes, key_pem: bytes) -> tuple[RegrasReceita, str | None]:
    """Retorna (regras, aviso). Se o GnreConfigUF falhar, usa os defaults e
    devolve um aviso -- o proprio GNRE valida o lote e recusar nao gera debito."""
    chave = (uf, receita)
    agora = time.time()
    em_cache = _CACHE.get(chave)
    if em_cache and agora - em_cache[0] < _TTL_SEGUNDOS:
        return em_cache[1], None
    try:
        xml = gnre_client.consultar_config_uf(uf, receita, cert_pem, key_pem)
        regras = interpretar_config_uf(xml, receita)
    except Exception as exc:  # noqa: BLE001
        return RegrasReceita(), f"Nao foi possivel consultar as regras da UF {uf} no GNRE ({exc}); usando regras padrao."
    _CACHE[chave] = (agora, regras)
    return regras, None
