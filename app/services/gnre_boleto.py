"""Gera o boleto (guia de arrecadacao) em PDF a partir dos dados que o GNRE
devolve na consulta do lote: linha digitavel, codigo de barras, valor, data
limite de pagamento e dados da guia.

O PDF e uma representacao feita pelo app, nao o PDF oficial do portal GNRE;
o pagamento no banco e feito pela linha digitavel / codigo de barras, que vem
direto do GNRE. Por isso o codigo de barras e conferido contra a linha
digitavel antes de desenhar.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

from reportlab.graphics.barcode.common import I2of5
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


class BoletoInvalidoError(Exception):
    pass


@dataclass
class DadosBoleto:
    linha_digitavel: str
    valor_total: float
    uf_favorecida: str
    receita: str
    descricao_receita: str
    emitente_nome: str
    emitente_documento: str
    destinatario_nome: str
    destinatario_documento: str
    documento_origem: str  # chave da NF-e
    data_vencimento: date | None = None
    data_limite_pagamento: date | None = None
    valor_difal: float = 0.0
    valor_fcp: float = 0.0
    codigo_barras: str | None = None
    nosso_numero: str | None = None
    informacoes: list[str] = field(default_factory=list)


def _digitos(texto: str | None) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def codigo_barras_da_linha(linha: str) -> str:
    """Linha digitavel de arrecadacao = 4 blocos de 11 digitos + 1 DV cada
    (48 digitos). O codigo de barras (44) e a concatenacao dos 4 blocos sem os DVs."""
    d = _digitos(linha)
    if len(d) != 48:
        raise BoletoInvalidoError(f"Linha digitavel invalida: esperado 48 digitos, veio {len(d)}.")
    return "".join(d[i : i + 11] for i in range(0, 48, 12))


def _formatar_linha(linha: str) -> str:
    d = _digitos(linha)
    return "  ".join(f"{d[i:i+11]}-{d[i+11]}" for i in range(0, 48, 12))


def _moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "--"


def _doc(d: str) -> str:
    n = _digitos(d)
    if len(n) == 14:
        return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
    if len(n) == 11:
        return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"
    return d


def gerar_pdf(dados: DadosBoleto) -> bytes:
    derivado = codigo_barras_da_linha(dados.linha_digitavel)
    barras = _digitos(dados.codigo_barras) or derivado
    if barras != derivado:
        raise BoletoInvalidoError("O codigo de barras informado nao confere com a linha digitavel.")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    largura, altura = A4
    m = 15 * mm
    y = altura - m

    c.setTitle(f"GNRE {dados.uf_favorecida} - {_moeda(dados.valor_total)}")
    c.setFont("Helvetica-Bold", 15)
    c.drawString(m, y - 5 * mm, "GNRE - Guia Nacional de Recolhimento de Tributos Estaduais")
    c.setFont("Helvetica", 9)
    c.drawString(m, y - 11 * mm, f"UF favorecida: {dados.uf_favorecida}")
    c.drawRightString(largura - m, y - 11 * mm, f"Receita {dados.receita}")
    c.setLineWidth(0.8)
    c.line(m, y - 14 * mm, largura - m, y - 14 * mm)
    y -= 20 * mm

    def campo(rotulo: str, valor: str, x: float, yy: float, negrito: bool = False):
        c.setFont("Helvetica", 7)
        c.setFillGray(0.35)
        c.drawString(x, yy, rotulo.upper())
        c.setFillGray(0)
        c.setFont("Helvetica-Bold" if negrito else "Helvetica", 10)
        c.drawString(x, yy - 4.5 * mm, valor[:62])

    campo("Receita", dados.descricao_receita, m, y)
    y -= 11 * mm
    campo("Contribuinte emitente", dados.emitente_nome, m, y)
    campo("CNPJ", _doc(dados.emitente_documento), largura - m - 55 * mm, y)
    y -= 11 * mm
    campo("Destinatario da mercadoria", dados.destinatario_nome, m, y)
    campo("CPF/CNPJ", _doc(dados.destinatario_documento), largura - m - 55 * mm, y)
    y -= 11 * mm
    campo("Documento de origem (chave da NF-e)", dados.documento_origem, m, y)
    y -= 11 * mm
    campo("Vencimento", _data(dados.data_vencimento), m, y)
    campo("Pagar ate", _data(dados.data_limite_pagamento), m + 50 * mm, y, negrito=True)
    if dados.nosso_numero:
        campo("Nosso numero", dados.nosso_numero, m + 100 * mm, y)
    y -= 13 * mm

    c.setLineWidth(0.4)
    c.line(m, y + 3 * mm, largura - m, y + 3 * mm)
    campo("ICMS DIFAL", _moeda(dados.valor_difal), m, y)
    campo("FCP", _moeda(dados.valor_fcp), m + 50 * mm, y)
    campo("TOTAL A PAGAR", _moeda(dados.valor_total), largura - m - 55 * mm, y, negrito=True)
    y -= 24 * mm

    c.setLineWidth(0.8)
    c.rect(m, y - 30 * mm, largura - 2 * m, 40 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(m + 3 * mm, y + 6 * mm, "LINHA DIGITAVEL")
    c.setFont("Courier-Bold", 10.5)
    c.drawString(m + 3 * mm, y - 1 * mm, _formatar_linha(dados.linha_digitavel))

    barra = I2of5(barras, barWidth=0.30 * mm, barHeight=16 * mm, checksum=0, bearers=0, quiet=0)
    barra.drawOn(c, m + 3 * mm, y - 24 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(m + 3 * mm, y - 28 * mm, barras)
    y -= 38 * mm

    if dados.informacoes:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(m, y, "Informacoes complementares")
        c.setFont("Helvetica", 8)
        for linha in dados.informacoes[:6]:
            y -= 4.5 * mm
            c.drawString(m, y, linha[:120])
        y -= 6 * mm

    c.setFont("Helvetica-Oblique", 7)
    c.setFillGray(0.4)
    c.drawString(m, 12 * mm, "Boleto gerado pelo GNRE.Flow a partir dos dados retornados pelo GNRE. Confira a linha digitavel no seu banco antes de pagar.")
    c.showPage()
    c.save()
    return buf.getvalue()
