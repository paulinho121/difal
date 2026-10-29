import os
import shutil
import time
from pathlib import Path

import pytest

from app.paths import data_dir
from app.services import gnre_regras
from app.services.gnre_regras import RegrasIndisponiveisError, obter_regras

CONFIG_PR = (Path(__file__).parent / "fixtures" / "config_uf_pr_100102.xml").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    gnre_regras._CACHE.clear()
    shutil.rmtree(data_dir() / "regras_gnre", ignore_errors=True)
    monkeypatch.setattr(gnre_regras, "_convenios_configurados", lambda: {"PR": "X"})
    yield
    gnre_regras._CACHE.clear()
    shutil.rmtree(data_dir() / "regras_gnre", ignore_errors=True)


def _consulta_que_falha(monkeypatch):
    chamadas = []

    def falha(uf, receita, c, k):
        chamadas.append(uf)
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(gnre_regras.gnre_client, "consultar_config_uf", falha)
    return chamadas


def test_sem_copia_e_sem_gnre_bloqueia_em_vez_de_usar_regras_padrao(monkeypatch):
    _consulta_que_falha(monkeypatch)
    with pytest.raises(RegrasIndisponiveisError, match="Nada foi enviado"):
        obter_regras("AM", "100102", b"c", b"k")  # UF sem regras guardadas nem semente


def test_gnre_fora_do_ar_usa_a_semente_embutida_do_pr_com_as_regras_do_pr(monkeypatch):
    _consulta_que_falha(monkeypatch)
    regras, aviso = obter_regras("PR", "100102", b"c", b"k")
    assert aviso and "ultima copia conhecida" in aviso
    assert regras.doc_origem_tipo == "10" and regras.doc_origem_e_numero is True  # NAO as regras do RJ
    assert regras.convenio == "X"


def test_resposta_boa_e_guardada_em_disco_e_evita_nova_consulta(monkeypatch):
    chamadas = []

    def boa(uf, receita, c, k):
        chamadas.append(uf)
        return CONFIG_PR

    monkeypatch.setattr(gnre_regras.gnre_client, "consultar_config_uf", boa)
    obter_regras("PR", "100102", b"c", b"k")
    assert (data_dir() / "regras_gnre" / "PR_100102.xml").exists()
    gnre_regras._CACHE.clear()  # simula reabrir o programa
    obter_regras("PR", "100102", b"c", b"k")
    assert chamadas == ["PR"]  # a segunda veio do disco, sem tocar no GNRE


def test_copia_em_disco_velha_e_usada_quando_o_gnre_falha(monkeypatch):
    arquivo = data_dir() / "regras_gnre" / "PR_100102.xml"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(CONFIG_PR, encoding="utf-8")
    antigo = time.time() - 3 * 24 * 3600
    os.utime(arquivo, (antigo, antigo))
    chamadas = _consulta_que_falha(monkeypatch)
    regras, aviso = obter_regras("PR", "100102", b"c", b"k")
    assert chamadas == ["PR"] and aviso  # tentou atualizar, falhou, usou a copia
    assert regras.doc_origem_tipo == "10"
