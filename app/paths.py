"""Onde ficam os arquivos do app.

- Recursos que acompanham o programa (telas, XSDs, tabela de aliquotas padrao):
  ficam ao lado do codigo; no programa instalado (PyInstaller) o codigo e
  extraido para sys._MEIPASS mantendo a mesma estrutura.
- Dados do usuario (banco, chave de criptografia, tabela de aliquotas editavel):
  precisam ficar fora da pasta de instalacao (somente leitura em Program Files e
  substituida a cada atualizacao). No programa instalado vao para
  %APPDATA%\GNRE.Flow; em desenvolvimento/servidor continuam em app/data.
  GNRE_DATA_DIR sobrescreve em qualquer caso.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
RECURSOS_DATA = APP_DIR / "data"  # tabela de aliquotas padrao (somente leitura)


def instalado() -> bool:
    """True quando rodando como programa empacotado (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    override = os.getenv("GNRE_DATA_DIR")
    if override:
        pasta = Path(override)
    elif instalado():
        pasta = Path(os.getenv("APPDATA") or Path.home()) / "GNRE.Flow"
    else:
        pasta = RECURSOS_DATA
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def arquivo_editavel(nome: str) -> Path:
    """Arquivo que o usuario pode editar. No programa instalado, copia o padrao
    embutido para a pasta de dados na primeira vez (e nunca sobrescreve depois,
    para que atualizacoes do programa nao apaguem as edicoes)."""
    destino = data_dir() / nome
    padrao = RECURSOS_DATA / nome
    if not destino.exists() and padrao.exists() and destino.resolve() != padrao.resolve():
        shutil.copyfile(padrao, destino)
    return destino if destino.exists() else padrao
