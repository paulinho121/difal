from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Guia, ItemNotaFiscal, NotaFiscal
from app.services import gnre_xml_builder
from app.services.difal_validator import validar_nota
from app.services.nfe_parser import NFeParseError, parse_nfe_xml

router = APIRouter(prefix="/api/xml", tags=["xml"])


def _persistir_nota(db: Session, nfe, validacao) -> NotaFiscal:
    nota = NotaFiscal(
        chave_acesso=nfe.chave_acesso,
        numero=nfe.numero,
        serie=nfe.serie,
        data_emissao=nfe.data_emissao.replace(tzinfo=None) if nfe.data_emissao else None,
        xml_raw="",  # preenchido pelo chamador antes do commit
        emitente_cnpj=nfe.emitente_cnpj,
        uf_origem=nfe.uf_origem,
        destinatario_doc=nfe.destinatario_doc,
        destinatario_nome=nfe.destinatario_nome,
        uf_destino=nfe.uf_destino,
        municipio_destino_ibge=nfe.municipio_destino_ibge,
        valor_total_produtos=nfe.valor_total_produtos,
        valor_total_nota=nfe.valor_total_nota,
    )
    db.add(nota)
    db.flush()

    validacao_por_numero = {v.numero_item: v for v in validacao.itens}
    for item in nfe.itens:
        v = validacao_por_numero.get(item.numero_item)
        db.add(
            ItemNotaFiscal(
                nota_fiscal_id=nota.id,
                numero_item=item.numero_item,
                ncm=item.ncm,
                cfop=item.cfop,
                v_prod=item.v_prod,
                v_bc_uf_dest=item.v_bc_uf_dest,
                v_bc_fcp_uf_dest=item.v_bc_fcp_uf_dest,
                p_fcp_uf_dest=item.p_fcp_uf_dest,
                p_icms_uf_dest=item.p_icms_uf_dest,
                p_icms_inter=item.p_icms_inter,
                p_icms_inter_part=item.p_icms_inter_part,
                v_fcp_uf_dest=item.v_fcp_uf_dest,
                v_icms_uf_dest=item.v_icms_uf_dest,
                v_icms_uf_remet=item.v_icms_uf_remet,
                aliquota_interna_usada=v.aliquota_interna_usada if v else None,
                valor_difal_recalculado=v.valor_difal_final if v else None,
                valor_fcp_recalculado=v.valor_fcp_final if v else None,
                divergente=v.divergente if v else False,
                divergencia_detalhe="; ".join(v.avisos) if v and v.avisos else None,
            )
        )

    data_vencimento = nfe.data_emissao.date() if nfe.data_emissao else None
    numero_controle = f"{nfe.numero or ''}{nfe.serie or ''}"[:20] or None

    guia = Guia(
        nota_fiscal_id=nota.id,
        status="aguardando_confirmacao" if validacao.uf_suportada else "erro",
        uf_favorecida=nfe.uf_destino,
        codigo_receita_difal=gnre_xml_builder.RECEITA_DIFAL_POR_OPERACAO if validacao.valor_difal_total > 0 else None,
        codigo_receita_fcp=gnre_xml_builder.RECEITA_FCP_POR_OPERACAO if validacao.valor_fcp_total > 0 else None,
        valor_difal=validacao.valor_difal_total,
        valor_fcp=validacao.valor_fcp_total,
        valor_total=round(validacao.valor_difal_total + validacao.valor_fcp_total, 2),
        data_vencimento=data_vencimento,
        mensagem_erro=(
            f"UF de destino {nfe.uf_destino} nao e suportada pelo Portal Nacional GNRE "
            "(usa guia estadual propria)."
            if not validacao.uf_suportada
            else None
        ),
    )
    db.add(guia)
    return nota


@router.post("/upload")
async def upload_xmls(files: list[UploadFile], db: Session = Depends(get_db)):
    resultados = []
    for upload in files:
        conteudo = await upload.read()
        try:
            nfe = parse_nfe_xml(conteudo)
        except NFeParseError as exc:
            resultados.append({"arquivo": upload.filename, "sucesso": False, "erro": str(exc)})
            continue

        existente = db.query(NotaFiscal).filter(NotaFiscal.chave_acesso == nfe.chave_acesso).first()
        if existente:
            resultados.append(
                {
                    "arquivo": upload.filename,
                    "sucesso": False,
                    "erro": f"NF-e {nfe.chave_acesso} ja foi processada anteriormente (guia #{existente.guia.id if existente.guia else '?'}).",
                }
            )
            continue

        validacao = validar_nota(nfe)
        nota = _persistir_nota(db, nfe, validacao)
        nota.xml_raw = conteudo.decode("utf-8", errors="replace")
        db.commit()
        db.refresh(nota)

        resultados.append(
            {
                "arquivo": upload.filename,
                "sucesso": True,
                "nota_fiscal_id": nota.id,
                "guia_id": nota.guia.id,
                "chave_acesso": nota.chave_acesso,
                "uf_destino": nota.uf_destino,
                "uf_suportada": validacao.uf_suportada,
                "valor_difal": validacao.valor_difal_total,
                "valor_fcp": validacao.valor_fcp_total,
                "valor_total": round(validacao.valor_difal_total + validacao.valor_fcp_total, 2),
                "divergente": validacao.divergente,
                "avisos": [aviso for item in validacao.itens for aviso in item.avisos],
            }
        )

    return {"resultados": resultados}
