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

# Reenvio apos 429 (o GNRE barrou o pedido ANTES de processar: nenhum lote foi criado, entao
# repetir e seguro). Um pedido a cada 10 min por guia, no maximo 12 vezes (~2 horas).
INTERVALO_REENVIO_SEGUNDOS = 600
MAX_REENVIOS = 12
_ultimo_reenvio: dict[int, float] = {}
_reenvios: dict[int, int] = {}
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


def marcar_envio_barrado(guia_id: int, agora: float | None = None) -> None:
    """Chamado quando um envio levou 429: a proxima tentativa automatica so ocorre
    depois do intervalo."""
    _ultimo_reenvio[guia_id] = time.time() if agora is None else agora
    _reenvios[guia_id] = _reenvios.get(guia_id, 0) + 1


def reenviar_pendentes(agora: float | None = None) -> int:
    """Reenvia, no maximo, UMA guia em "aguardando_reenvio" que ja esteja no ponto de
    nova tentativa. Retorna quantos envios fez (0 ou 1)."""
    from fastapi import HTTPException

    from app.routers.guias import confirmar_e_emitir  # evita import circular

    agora = time.time() if agora is None else agora
    db = SessionLocal()
    try:
        for guia in db.query(Guia).filter(Guia.status == "aguardando_reenvio").order_by(Guia.id).all():
            if _reenvios.get(guia.id, 0) >= MAX_REENVIOS:
                guia.status = "erro"
                guia.mensagem_erro = (
                    "O GNRE continuou limitando as requisicoes depois de varias tentativas automaticas. "
                    'Tente de novo mais tarde com "Reemitir".'
                )
                db.commit()
                continue
            if agora - _ultimo_reenvio.get(guia.id, 0) < INTERVALO_REENVIO_SEGUNDOS:
                continue
            _ultimo_reenvio[guia.id] = agora
            _reenvios[guia.id] = _reenvios.get(guia.id, 0) + 1
            try:
                confirmar_e_emitir(guia.id, db)
            except HTTPException as exc:
                logging.warning("Reenvio automatico da guia %s nao feito: %s", guia.id, exc.detail)
            db.refresh(guia)
            logging.info("Reenvio automatico da guia %s (tentativa %s): status=%s", guia.id, _reenvios[guia.id], guia.status)
            return 1
        return 0
    finally:
        db.close()


def _laco() -> None:
    while not _parar.wait(VERIFICAR_A_CADA_SEGUNDOS):
        try:
            if consultar_pendentes() == 0:
                reenviar_pendentes()
        except Exception:  # noqa: BLE001 -- nunca derrubar o programa por causa da consulta
            logging.exception("Falha na consulta automatica")


def iniciar() -> None:
    if ativa():
        _parar.clear()
        threading.Thread(target=_laco, daemon=True, name="consulta-automatica").start()


def parar() -> None:
    _parar.set()
