"""Consulta automatica e CALMA do resultado dos lotes enviados ao GNRE.

O GNRE responde 429 quando recebe consultas demais, entao o programa nao deve
exigir que o usuario fique clicando em "Atualizar Status". Aqui: no maximo UMA
consulta por vez, cada guia no maximo a cada INTERVALO_SEGUNDOS, e para depois de
MAX_TENTATIVAS por guia (o usuario ainda pode consultar manualmente). So roda no
programa instalado (GNRE_AUTO_CONSULTA=1, definido pelo launcher).
"""

from __future__ import annotations

import logging
import os
import threading
import time

from app.database import SessionLocal
from app.models import Guia

INTERVALO_SEGUNDOS = 600  # 10 minutos entre consultas da mesma guia
MAX_TENTATIVAS = 24  # ~4 horas
VERIFICAR_A_CADA_SEGUNDOS = 30

_ultima_tentativa: dict[int, float] = {}
_tentativas: dict[int, int] = {}
_parar = threading.Event()


def ativa() -> bool:
    return os.getenv("GNRE_AUTO_CONSULTA") == "1"


def consultar_pendentes(agora: float | None = None) -> int:
    """Consulta, no maximo, UMA guia "enviada" que ja esteja no ponto de nova
    tentativa. Retorna quantas consultas fez (0 ou 1)."""
    from app.routers.guias import consultar_e_atualizar  # evita import circular

    agora = time.time() if agora is None else agora
    db = SessionLocal()
    try:
        pendentes = (
            db.query(Guia)
            .filter(Guia.status == "enviada", Guia.protocolo_lote.isnot(None))
            .order_by(Guia.id)
            .all()
        )
        for guia in pendentes:
            if _tentativas.get(guia.id, 0) >= MAX_TENTATIVAS:
                continue
            if agora - _ultima_tentativa.get(guia.id, 0) < INTERVALO_SEGUNDOS:
                continue
            _ultima_tentativa[guia.id] = agora
            _tentativas[guia.id] = _tentativas.get(guia.id, 0) + 1
            consultar_e_atualizar(db, guia)
            logging.info(
                "Consulta automatica da guia %s (tentativa %s): status=%s",
                guia.id, _tentativas[guia.id], guia.status,
            )
            return 1
        return 0
    finally:
        db.close()


def _laco() -> None:
    while not _parar.wait(VERIFICAR_A_CADA_SEGUNDOS):
        try:
            consultar_pendentes()
        except Exception:  # noqa: BLE001 -- nunca derrubar o programa por causa da consulta
            logging.exception("Falha na consulta automatica")


def iniciar() -> None:
    if ativa():
        _parar.clear()
        threading.Thread(target=_laco, daemon=True, name="consulta-automatica").start()


def parar() -> None:
    _parar.set()
