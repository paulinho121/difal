"""Ponto de entrada do programa instalado no Windows (GNRE.Flow).

Sobe o servidor do app em 127.0.0.1 numa porta livre e abre a interface numa
janela propria (WebView2). Fechar a janela encerra o servidor. Se a janela
propria nao puder ser aberta, abre no navegador padrao e espera o usuario
encerrar.
"""

from __future__ import annotations

import ctypes
import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from app.paths import data_dir

TITULO = "GNRE.Flow"


def _redirecionar_saida_para_log() -> None:
    """Programa sem console (--windowed): sys.stdout/stderr sao None e o
    uvicorn/logging quebram. Manda tudo para um arquivo na pasta de dados."""
    log = open(data_dir() / "gnre_flow.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    logging.basicConfig(stream=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _caixa_de_mensagem(texto: str, titulo: str = TITULO) -> None:
    ctypes.windll.user32.MessageBoxW(0, texto, titulo, 0x40)


def _ja_esta_aberto() -> bool:
    """Instancia unica: dois programas sobre o mesmo banco SQLite seriam um problema."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "GNRE.Flow.Instancia.Unica")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aguardar_servidor(url: str, tentativas: int = 80) -> bool:
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(f"{url}/api/dashboard/stats", timeout=1):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    return False


def _autoteste() -> int:
    """`GNRE.Flow.exe --selftest`: confere dentro do pacote instalado que os
    recursos embutidos (XSDs, tabela de aliquotas) e as bibliotecas (lxml,
    reportlab com codigo de barras, zeep) funcionam. Resultado no log; codigo
    de saida 0 = tudo certo."""
    from datetime import date

    from app.services import difal_validator, gnre_boleto, gnre_regras, gnre_xml_builder as b

    emitente = b.ContribuinteEmitente(cnpj="05502390000200", razao_social="TESTE LTDA", uf="SC")
    guia = b.GuiaParaEmitir(
        uf_destino="RJ", chave_nfe="4" * 44, valor_difal=34.63, valor_fcp=4.33,
        destinatario=b.ContribuinteDestinatario(documento="15202768770", nome="TESTE"),
        data_vencimento=date(2026, 10, 19), data_emissao=date(2026, 10, 19), data_pagamento=date(2026, 10, 21),
    )
    xml = b.montar_lote_xml(emitente, [guia])  # valida contra o XSD embutido
    linha = "85800000000" + "5" + "38960000000" + "1" + "26000513909" + "2" + "12026102100" + "7"
    pdf = gnre_boleto.gerar_pdf(gnre_boleto.DadosBoleto(
        linha_digitavel=linha, valor_total=38.96, uf_favorecida="RJ", receita="100102", descricao_receita="Teste",
        emitente_nome="TESTE", emitente_documento="05502390000200", destinatario_nome="TESTE",
        destinatario_documento="15202768770", documento_origem="4" * 44))
    assert xml.startswith(b"<?xml") and pdf.startswith(b"%PDF-")
    assert difal_validator.uf_suportada_gnre_nacional("MG") is True
    assert gnre_regras.RegrasReceita().doc_origem_tipo == "24"
    logging.info("AUTOTESTE OK: lote validado no XSD (%d bytes), boleto PDF (%d bytes), tabela de aliquotas carregada", len(xml), len(pdf))
    return 0


def main() -> int:
    _redirecionar_saida_para_log()

    if "--selftest" in sys.argv:
        try:
            return _autoteste()
        except Exception:  # noqa: BLE001
            logging.exception("AUTOTESTE FALHOU")
            return 2

    if _ja_esta_aberto():
        _caixa_de_mensagem("O GNRE.Flow ja esta aberto. Procure a janela na barra de tarefas.")
        return 0

    import os

    os.environ["GNRE_AUTO_CONSULTA"] = "1"  # consulta o resultado dos lotes sozinho, com calma

    import uvicorn

    from app.main import app

    porta = _porta_livre()
    url = f"http://127.0.0.1:{porta}"
    # log_config=None: o logging padrao do uvicorn exige console.
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_config=None, http="h11", loop="asyncio", ws="none")
    )
    threading.Thread(target=servidor.run, daemon=True).start()

    if not _aguardar_servidor(url):
        _caixa_de_mensagem("Nao foi possivel iniciar o servidor interno. Veja o arquivo gnre_flow.log em %APPDATA%\\GNRE.Flow.", "GNRE.Flow - erro")
        servidor.should_exit = True
        return 1

    try:
        import webview

        webview.create_window(TITULO, url, width=1280, height=860, min_size=(900, 600))
        webview.start()  # bloqueia ate a janela fechar
    except Exception:  # noqa: BLE001 -- WebView2 ausente etc.
        logging.exception("Janela propria indisponivel; abrindo no navegador")
        webbrowser.open(url)
        _caixa_de_mensagem("O GNRE.Flow esta aberto no seu navegador.\n\nClique em OK para ENCERRAR o programa.")

    servidor.should_exit = True
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
