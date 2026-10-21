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
