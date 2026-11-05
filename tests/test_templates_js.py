"""Um erro de sintaxe no JavaScript de uma tela trava a pagina inteira (aconteceu no
Historico: ficava eternamente em 'Carregando...'). Valida a sintaxe de todos os scripts inline."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).parent.parent / "app" / "templates").glob("*.html"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_javascript_inline_tem_sintaxe_valida(template, tmp_path):
    html = template.read_text(encoding="utf-8")
    for n, codigo in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)):
        if not codigo.strip() or "tailwind.config" in codigo[:60]:
            continue
        arq = tmp_path / f"{template.stem}_{n}.js"
        arq.write_text(codigo, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, f"{template.name} (script {n}): {r.stderr[:400]}"
