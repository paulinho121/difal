from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.empresa_singleton import get_or_create_empresa
from app.services import certificado_manager, gnre_client

router = APIRouter(prefix="/api/certificado", tags=["certificado"])


def _serializar(empresa) -> dict:
    cert = empresa.certificado
    if cert is None:
        return {"configurado": False}
    return {
        "configurado": True,
        "subject_cn": cert.subject_cn,
        "cnpj_certificado": cert.cnpj_certificado,
        "valido_ate": cert.valido_ate.isoformat() if cert.valido_ate else None,
        "status": cert.status,
        "empresa": {
            "cnpj": empresa.cnpj,
            "razao_social": empresa.razao_social,
        },
    }


@router.get("")
def obter_certificado(db: Session = Depends(get_db)):
    empresa = get_or_create_empresa(db)
    return _serializar(empresa)


@router.post("")
async def salvar_certificado(
    arquivo: UploadFile,
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    empresa = get_or_create_empresa(db)
    conteudo = await arquivo.read()

    try:
        info = certificado_manager.validar_pfx(conteudo, senha)
    except certificado_manager.CertificadoInvalidoError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Extrai razao social/CNPJ do proprio certificado para preencher o
    # cadastro da (unica) empresa automaticamente, evitando um formulario
    # manual redundante.
    if info.subject_cn and ":" in info.subject_cn:
        razao_social = info.subject_cn.rsplit(":", 1)[0].strip()
        empresa.razao_social = razao_social or empresa.razao_social
    if info.cnpj:
        empresa.cnpj = info.cnpj

    certificado_manager.salvar_certificado(db, empresa, conteudo, senha)
    db.commit()
    db.refresh(empresa)
    return _serializar(empresa)


@router.post("/testar")
def testar_certificado(db: Session = Depends(get_db)):
    empresa = get_or_create_empresa(db)
    if empresa.certificado is None:
        raise HTTPException(400, "Nenhum certificado cadastrado ainda.")

    conteudo, senha = certificado_manager.carregar_certificado(empresa.certificado)
    cert_pem, key_pem = certificado_manager.pfx_para_pem(conteudo, senha)

    try:
        resultado = gnre_client.testar_conectividade(cert_pem, key_pem)
        return {"ok": True, **resultado}
    except Exception as exc:  # noqa: BLE001 -- resultado de teste de conectividade real, precisa aparecer pro usuario
        return {"ok": False, "erro": str(exc)}
