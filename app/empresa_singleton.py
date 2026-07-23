"""Sistema single-tenant: uma unica Empresa. Helper para obter (ou criar, na
primeira execucao) essa linha unica."""

from sqlalchemy.orm import Session

from app.models import Empresa


def get_or_create_empresa(db: Session) -> Empresa:
    empresa = db.query(Empresa).first()
    if empresa is None:
        empresa = Empresa(cnpj="", razao_social="Empresa nao configurada")
        db.add(empresa)
        db.commit()
        db.refresh(empresa)
    return empresa
