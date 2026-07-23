import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(120))
    ie: Mapped[str | None] = mapped_column(String(16), nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(11), nullable=True)

    certificado: Mapped["Certificado | None"] = relationship(back_populates="empresa", uselist=False)


class Certificado(Base):
    __tablename__ = "certificados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"))
    arquivo_encriptado: Mapped[bytes] = mapped_column(LargeBinary)
    senha_encriptada: Mapped[bytes] = mapped_column(LargeBinary)
    subject_cn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cnpj_certificado: Mapped[str | None] = mapped_column(String(14), nullable=True)
    valido_ate: Mapped[datetime.date | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    empresa: Mapped["Empresa"] = relationship(back_populates="certificado")

    @property
    def status(self) -> str:
        if self.valido_ate is None:
            return "desconhecido"
        return "valido" if self.valido_ate >= datetime.date.today() else "expirado"


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave_acesso: Mapped[str] = mapped_column(String(44), unique=True, index=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    serie: Mapped[str | None] = mapped_column(String(5), nullable=True)
    data_emissao: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    xml_raw: Mapped[str] = mapped_column(Text)

    emitente_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    uf_origem: Mapped[str | None] = mapped_column(String(2), nullable=True)

    destinatario_doc: Mapped[str | None] = mapped_column(String(14), nullable=True)
    destinatario_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uf_destino: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipio_destino_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True)

    valor_total_produtos: Mapped[float] = mapped_column(Float, default=0.0)
    valor_total_nota: Mapped[float] = mapped_column(Float, default=0.0)

    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    itens: Mapped[list["ItemNotaFiscal"]] = relationship(back_populates="nota_fiscal", cascade="all, delete-orphan")
    guia: Mapped["Guia | None"] = relationship(back_populates="nota_fiscal", uselist=False, cascade="all, delete-orphan")


class ItemNotaFiscal(Base):
    __tablename__ = "itens_nota_fiscal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nota_fiscal_id: Mapped[int] = mapped_column(ForeignKey("notas_fiscais.id"))
    numero_item: Mapped[int] = mapped_column(Integer)
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cfop: Mapped[str | None] = mapped_column(String(4), nullable=True)
    v_prod: Mapped[float] = mapped_column(Float, default=0.0)

    # Grupo ICMSUFDest, já declarado pelo emitente na NF-e autorizada
    v_bc_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_bc_fcp_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_fcp_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_icms_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_icms_inter: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_icms_inter_part: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_fcp_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_icms_uf_dest: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_icms_uf_remet: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Recalculo independente feito pelo difal_validator
    aliquota_interna_usada: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_difal_recalculado: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_fcp_recalculado: Mapped[float | None] = mapped_column(Float, nullable=True)
    divergente: Mapped[bool] = mapped_column(Boolean, default=False)
    divergencia_detalhe: Mapped[str | None] = mapped_column(Text, nullable=True)

    nota_fiscal: Mapped["NotaFiscal"] = relationship(back_populates="itens")


class Guia(Base):
    __tablename__ = "guias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nota_fiscal_id: Mapped[int] = mapped_column(ForeignKey("notas_fiscais.id"))

    status: Mapped[str] = mapped_column(String(30), default="calculada")
    # calculada -> aguardando_confirmacao -> enviada -> emitida | erro

    uf_favorecida: Mapped[str | None] = mapped_column(String(2), nullable=True)
    codigo_receita_difal: Mapped[str | None] = mapped_column(String(6), nullable=True)
    codigo_receita_fcp: Mapped[str | None] = mapped_column(String(6), nullable=True)

    valor_difal: Mapped[float] = mapped_column(Float, default=0.0)
    valor_fcp: Mapped[float] = mapped_column(Float, default=0.0)
    valor_total: Mapped[float] = mapped_column(Float, default=0.0)

    numero_guia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    protocolo_lote: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_vencimento: Mapped[datetime.date | None] = mapped_column(nullable=True)
    linha_digitavel: Mapped[str | None] = mapped_column(String(60), nullable=True)
    pdf_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    mensagem_erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    nota_fiscal: Mapped["NotaFiscal"] = relationship(back_populates="guia")
