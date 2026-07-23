from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Guia, NotaFiscal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Estimativa heuristica de tempo economizado por guia emitida automaticamente
# (preenchimento manual + geracao da guia no Portal), so para o card do
# dashboard -- nao e um dado fiscal.
HORAS_ECONOMIZADAS_POR_GUIA = 0.35


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    xmls_processados = db.query(func.count(NotaFiscal.id)).scalar() or 0
    guias_emitidas = db.query(func.count(Guia.id)).filter(Guia.status == "emitida").scalar() or 0
    guias_pendentes = (
        db.query(func.count(Guia.id))
        .filter(Guia.status.in_(["calculada", "aguardando_confirmacao", "enviada"]))
        .scalar()
        or 0
    )
    guias_erro = db.query(func.count(Guia.id)).filter(Guia.status == "erro").scalar() or 0

    emissoes_por_dia = (
        db.query(func.date(Guia.criado_em).label("dia"), func.count(Guia.id))
        .filter(Guia.status == "emitida")
        .group_by("dia")
        .order_by("dia")
        .all()
    )

    return {
        "xmls_processados": xmls_processados,
        "guias_emitidas": guias_emitidas,
        "guias_pendentes": guias_pendentes,
        "guias_erro": guias_erro,
        "tempo_economizado_horas": round(guias_emitidas * HORAS_ECONOMIZADAS_POR_GUIA, 1),
        "emissoes_por_dia": [{"dia": str(dia), "quantidade": qtd} for dia, qtd in emissoes_por_dia],
    }
