from pathlib import Path

from app.services.gnre_regras import interpretar_config_uf

CONFIG_RJ = (Path(__file__).parent / "fixtures" / "config_uf_rj_100102.xml").read_text(encoding="utf-8")


def test_regras_do_rj_100102_lidas_da_resposta_real():
    r = interpretar_config_uf(CONFIG_RJ, "100102")
    assert r.doc_origem_tipo == "24"  # CHAVE DO DFe
    assert r.exige_data_pagamento is True
    assert r.fecp_no_mesmo_item is True
    assert r.exige_referencia is False
    assert r.produto is None
    assert r.pendencias == []
    obrigatorios = [c for c in r.campos_extras if c.obrigatorio]
    assert [(c.codigo, c.tipo) for c in obrigatorios] == [(117, "D")]


def test_receita_que_a_uf_nao_oferece_vira_pendencia():
    # O RJ nao lista a 100129 -- exatamente o erro 205 recebido do GNRE em producao.
    r = interpretar_config_uf(CONFIG_RJ, "100129")
    assert any("100129" in p for p in r.pendencias)


CONFIG_PR = (Path(__file__).parent / "fixtures" / "config_uf_pr_100102.xml").read_text(encoding="utf-8")


def test_regras_do_pr_documento_de_origem_e_o_numero_e_chave_vai_em_campo_extra():
    r = interpretar_config_uf(CONFIG_PR, "100102")
    assert r.doc_origem_tipo == "10"  # NOTA FISCAL (o PR nao oferece "CHAVE DO DFe")
    assert r.doc_origem_e_numero is True
    assert r.convenio_exigido is True
    assert r.pendencias == []  # o convenio so vira pendencia em aplicar_convenio
    assert r.fecp_no_mesmo_item is False  # PR: exigeValorFecp = N
    obrigatorios = [(c.codigo, c.titulo[:5]) for c in r.campos_extras if c.obrigatorio]
    assert obrigatorios == [(107, "Chave")]


def test_convenio_exigido_sem_valor_configurado_barra_com_instrucao(monkeypatch):
    from app.services import gnre_regras

    monkeypatch.setattr(gnre_regras, "_convenios_configurados", lambda: {})
    r = gnre_regras.aplicar_convenio(interpretar_config_uf(CONFIG_PR, "100102"), "PR")
    assert any("Convenio" in p and "convenios_gnre.json" in p for p in r.pendencias)


def test_convenio_configurado_e_aplicado(monkeypatch):
    from app.services import gnre_regras

    monkeypatch.setattr(gnre_regras, "_convenios_configurados", lambda: {"PR": "VALOR-TESTE"})
    r = gnre_regras.aplicar_convenio(interpretar_config_uf(CONFIG_PR, "100102"), "PR")
    assert r.convenio == "VALOR-TESTE" and r.pendencias == []


def test_aplicar_convenio_nao_altera_as_regras_em_cache():
    from app.services import gnre_regras

    base = interpretar_config_uf(CONFIG_PR, "100102")
    gnre_regras.aplicar_convenio(base, "PR")
    assert base.pendencias == [] and base.convenio is None
