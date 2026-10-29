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
    # Algumas UFs (ex.: PR) nao oferecem "CHAVE DO DFe": o documento de origem e o
    # NUMERO da nota (tipo 10 "NOTA FISCAL") e a chave vai num campo extra.
    doc_origem_e_numero: bool = False
    convenio_exigido: bool = False
    convenio: str | None = None
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
    nota_fiscal = next((c for c, d in tipos if "NOTA FISCAL" in d and "CONHECIMENTO" not in d), None)
    if escolhido:
        regras.doc_origem_tipo = escolhido
    elif nota_fiscal:
        regras.doc_origem_tipo = nota_fiscal
        regras.doc_origem_e_numero = True
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
    # O GNRE so diz que o convenio e obrigatorio, sem listar valores: o valor vem
    # de convenios_gnre.json (ver aplicar_convenio) e nunca e adivinhado.
    regras.convenio_exigido = _sim(alvo, "exigeConvenio")
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


def _convenios_configurados() -> dict[str, str]:
    import json

    from app.paths import arquivo_editavel

    try:
        with open(arquivo_editavel("convenios_gnre.json"), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return {uf: str(v).strip() for uf, v in dados.items() if not uf.startswith("_") and str(v).strip()}


UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI",
       "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]


def listar_convenios() -> dict[str, str]:
    return _convenios_configurados()


def definir_convenio(uf: str, valor: str) -> None:
    """Grava (ou, com valor vazio, esvazia) o convenio de uma UF no arquivo editavel."""
    import json

    from app.paths import arquivo_editavel

    uf = uf.upper().strip()
    valor = valor.strip()
    if uf not in UFS:
        raise ValueError(f"UF invalida: {uf!r}")
    if len(valor) > 30:
        raise ValueError("O convenio aceita no maximo 30 caracteres (limite do GNRE).")
    caminho = arquivo_editavel("convenios_gnre.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        dados = {}
    dados[uf] = valor
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def aplicar_convenio(regras: RegrasReceita, uf: str) -> RegrasReceita:
    """Preenche o convenio exigido pela UF a partir do arquivo configuravel; se a UF
    exige e nao ha valor configurado, vira pendencia (barra o envio, com instrucao)."""
    import copy

    r = copy.deepcopy(regras)
    if r.convenio_exigido:
        valor = _convenios_configurados().get(uf)
        if valor:
            r.convenio = valor
        else:
            r.pendencias.append(
                f"a UF {uf} exige o campo Convenio e nenhum valor foi configurado "
                f"(informe em Ajustes (cartao Convenios por UF), com o valor confirmado pelo seu contador ou pela SEFAZ de {uf})"
            )
    return r


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
        return aplicar_convenio(em_cache[1], uf), None
    try:
        xml = gnre_client.consultar_config_uf(uf, receita, cert_pem, key_pem)
        regras = interpretar_config_uf(xml, receita)
    except Exception as exc:  # noqa: BLE001
        return RegrasReceita(), f"Nao foi possivel consultar as regras da UF {uf} no GNRE ({exc}); usando regras padrao."
    _CACHE[chave] = (agora, regras)
    return aplicar_convenio(regras, uf), None
