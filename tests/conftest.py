"""Isola os testes num banco/chave temporarios ANTES de qualquer import do app,
para que nenhum teste grave no banco de desenvolvimento."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="gnreflow_testes_")
os.environ["GNRE_DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/testes.db".replace("\\", "/")
os.environ.pop("SECRET_KEY", None)
