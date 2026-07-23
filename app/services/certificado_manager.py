"""Valida, armazena (criptografado) e prepara para uso o certificado digital
A1 (.pfx/.p12) usado para autenticacao mTLS nos WebServices da GNRE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from sqlalchemy.orm import Session

from app.models import Certificado, Empresa
from app.services import crypto


class CertificadoInvalidoError(Exception):
    pass


@dataclass
class CertificadoInfo:
    subject_cn: str | None
    cnpj: str | None
    valido_ate: date


def _extrair_cnpj_do_subject(cn: str | None) -> str | None:
    if not cn:
        return None
    # Certificados e-CNPJ A1 tipicamente tem o CN no formato "RAZAO SOCIAL:14DIGITOS".
    match = re.search(r"(\d{14})", cn)
    return match.group(1) if match else None


def validar_pfx(conteudo: bytes, senha: str) -> CertificadoInfo:
    try:
        _, certificate, _ = pkcs12.load_key_and_certificates(conteudo, senha.encode("utf-8"))
    except Exception as exc:
        raise CertificadoInvalidoError(
            "Nao foi possivel abrir o certificado: arquivo corrompido, senha incorreta ou formato invalido."
        ) from exc

    if certificate is None:
        raise CertificadoInvalidoError("O arquivo .pfx nao contem um certificado valido.")

    subject_attrs = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    subject_cn = subject_attrs[0].value if subject_attrs else None

    valido_ate = certificate.not_valid_after_utc.date()

    return CertificadoInfo(
        subject_cn=subject_cn,
        cnpj=_extrair_cnpj_do_subject(subject_cn),
        valido_ate=valido_ate,
    )


def pfx_para_pem(conteudo: bytes, senha: str) -> tuple[bytes, bytes]:
    """Converte o .pfx para (cert_pem, key_pem) -- formato exigido pela lib
    requests/zeep para autenticacao mTLS via arquivos PEM."""
    private_key, certificate, _ = pkcs12.load_key_and_certificates(conteudo, senha.encode("utf-8"))
    if private_key is None or certificate is None:
        raise CertificadoInvalidoError("Certificado sem chave privada ou sem certificado -- nao pode ser usado para mTLS.")

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def salvar_certificado(db: Session, empresa: Empresa, conteudo: bytes, senha: str) -> Certificado:
    info = validar_pfx(conteudo, senha)

    certificado = empresa.certificado
    if certificado is None:
        certificado = Certificado(empresa_id=empresa.id)
        db.add(certificado)

    certificado.arquivo_encriptado = crypto.encriptar(conteudo)
    certificado.senha_encriptada = crypto.encriptar(senha.encode("utf-8"))
    certificado.subject_cn = info.subject_cn
    certificado.cnpj_certificado = info.cnpj
    certificado.valido_ate = info.valido_ate

    db.commit()
    db.refresh(certificado)
    return certificado


def carregar_certificado(certificado: Certificado) -> tuple[bytes, str]:
    conteudo = crypto.decriptar(certificado.arquivo_encriptado)
    senha = crypto.decriptar(certificado.senha_encriptada).decode("utf-8")
    return conteudo, senha
