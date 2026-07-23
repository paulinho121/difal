import base64

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.empresa_singleton import get_or_create_empresa
from app.models import Guia
from app.services import certificado_manager, gnre_client, gnre_xml_builder

router = APIRouter(prefix="/api/guias", tags=["guias"])


def _serializar_guia(guia: Guia) -> dict:
    nota = guia.nota_fiscal
    return {
        "id": guia.id,
        "status": guia.status,
        "uf_favorecida": guia.uf_favorecida,
        "valor_difal": guia.valor_difal,
        "valor_fcp": guia.valor_fcp,
        "valor_total": guia.valor_total,
        "numero_guia": guia.numero_guia,
        "protocolo_lote": guia.protocolo_lote,
        "data_vencimento": guia.data_vencimento.isoformat() if guia.data_vencimento else None,
        "linha_digitavel": guia.linha_digitavel,
        "tem_pdf": bool(guia.pdf_base64),
        "mensagem_erro": guia.mensagem_erro,
        "criado_em": guia.criado_em.isoformat(),
        "atualizado_em": guia.atualizado_em.isoformat(),
        "nota_fiscal": {
            "id": nota.id,
            "chave_acesso": nota.chave_acesso,
            "numero": nota.numero,
            "serie": nota.serie,
            "destinatario_nome": nota.destinatario_nome,
            "destinatario_doc": nota.destinatario_doc,
            "uf_destino": nota.uf_destino,
        },
    }


@router.get("")
def listar_guias(
    uf: str | None = None,
    status: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Guia).join(Guia.nota_fiscal)
    if uf:
        query = query.filter(Guia.uf_favorecida == uf)
    if status:
        query = query.filter(Guia.status == status)
    if busca:
        from app.models import NotaFiscal

        termo = f"%{busca}%"
        query = query.filter(
            (NotaFiscal.destinatario_nome.ilike(termo))
            | (NotaFiscal.chave_acesso.ilike(termo))
            | (Guia.numero_guia.ilike(termo))
        )

    guias = query.order_by(Guia.criado_em.desc()).all()
    return {"guias": [_serializar_guia(g) for g in guias], "total": len(guias)}


@router.get("/{guia_id}")
def detalhe_guia(guia_id: int, db: Session = Depends(get_db)):
    guia = db.get(Guia, guia_id)
    if guia is None:
        raise HTTPException(404, "Guia nao encontrada.")
    return _serializar_guia(guia)


def _carregar_cert_da_empresa(db: Session) -> tuple[bytes, bytes]:
    empresa = get_or_create_empresa(db)
    if empresa.certificado is None:
        raise ValueError("Nenhum certificado digital cadastrado. Configure em Certificado antes de emitir guias.")
    conteudo, senha = certificado_manager.carregar_certificado(empresa.certificado)
    return certificado_manager.pfx_para_pem(conteudo, senha)


@router.post("/{guia_id}/confirmar")
def confirmar_e_emitir(guia_id: int, db: Session = Depends(get_db)):
    """Gate de seguranca do fluxo: so a partir daqui um debito fiscal real e
    registrado perante a SEFAZ. O usuario ja viu o valor calculado na tela de
    revisao antes de chegar aqui."""
    guia = db.get(Guia, guia_id)
    if guia is None:
        raise HTTPException(404, "Guia nao encontrada.")
    # "enviada" sem protocolo_lote e um estado travado: o envio anterior nao
    # levantou excecao mas nao conseguimos extrair o numeroRecibo da resposta
    # -- permite tentar de novo nesse caso especifico.
    preso_sem_protocolo = guia.status == "enviada" and not guia.protocolo_lote
    if guia.status not in ("aguardando_confirmacao", "erro") and not preso_sem_protocolo:
        raise HTTPException(400, f"Guia em status '{guia.status}' nao pode ser confirmada/reenviada.")

    empresa = get_or_create_empresa(db)
    nota = guia.nota_fiscal

    try:
        cert_pem, key_pem = _carregar_cert_da_empresa(db)

        empresa_builder = gnre_xml_builder.ContribuinteEmitente(
            cnpj=empresa.cnpj,
            razao_social=empresa.razao_social,
            endereco=empresa.endereco,
            municipio_ibge=empresa.municipio_ibge,
            uf=empresa.uf,
            cep=empresa.cep,
            telefone=empresa.telefone,
        )
        guia_builder = gnre_xml_builder.GuiaParaEmitir(
            uf_destino=guia.uf_favorecida,
            chave_nfe=nota.chave_acesso,
            valor_difal=guia.valor_difal,
            valor_fcp=guia.valor_fcp,
            destinatario=gnre_xml_builder.ContribuinteDestinatario(
                documento=nota.destinatario_doc,
                nome=nota.destinatario_nome,
                municipio_ibge=nota.municipio_destino_ibge,
            ),
            data_vencimento=guia.data_vencimento,
            numero_controle=f"{nota.numero or ''}{nota.serie or ''}"[:20] or None,
        )

        xml_lote = gnre_xml_builder.montar_lote_xml(empresa_builder, [guia_builder])
        resultado = gnre_client.enviar_lote(xml_lote, cert_pem, key_pem)

        guia.status = "enviada"
        guia.protocolo_lote = resultado.protocolo
        if resultado.protocolo:
            guia.mensagem_erro = None
        else:
            # O envio nao levantou excecao (o GNRE aceitou a chamada), mas nao
            # conseguimos extrair o numeroRecibo da resposta -- guarda a
            # resposta bruta em vez de descartar, senao fica impossivel
            # diagnosticar o formato real sem acesso ao ambiente de producao.
            guia.mensagem_erro = f"Enviado, mas sem numeroRecibo na resposta. Resposta bruta: {resultado.resposta_bruta[:1500]}"
    except Exception as exc:  # noqa: BLE001 -- superficie de erro fiscal, precisa chegar ate o usuario
        guia.status = "erro"
        guia.mensagem_erro = str(exc)

    db.commit()
    db.refresh(guia)
    return _serializar_guia(guia)


@router.post("/{guia_id}/atualizar-status")
def atualizar_status(guia_id: int, db: Session = Depends(get_db)):
    guia = db.get(Guia, guia_id)
    if guia is None:
        raise HTTPException(404, "Guia nao encontrada.")
    if guia.status != "enviada" or not guia.protocolo_lote:
        raise HTTPException(400, "Guia ainda nao foi enviada ao GNRE (sem protocolo de lote).")

    try:
        cert_pem, key_pem = _carregar_cert_da_empresa(db)
        resultado = gnre_client.consultar_resultado_lote(guia.protocolo_lote, cert_pem, key_pem)

        if not resultado.guias:
            guia.mensagem_erro = f"Sem retorno de guia ainda ({resultado.situacao_processo_descricao or 'processando'})."
        else:
            guia_result = resultado.guias[0]
            if guia_result.situacao == gnre_client.SITUACAO_GUIA_PROCESSADA:
                guia.status = "emitida"
                guia.linha_digitavel = guia_result.linha_digitavel
                guia.mensagem_erro = None
            else:
                guia.status = "erro"
                motivos = "; ".join(f"{m['codigo']}: {m['descricao']}" for m in guia_result.motivos_rejeicao)
                guia.mensagem_erro = motivos or "Guia invalidada pelo Portal/UF ou erro de comunicacao."
    except Exception as exc:  # noqa: BLE001
        guia.mensagem_erro = str(exc)

    db.commit()
    db.refresh(guia)
    return _serializar_guia(guia)


@router.post("/{guia_id}/reemitir")
def reemitir(guia_id: int, db: Session = Depends(get_db)):
    guia = db.get(Guia, guia_id)
    if guia is None:
        raise HTTPException(404, "Guia nao encontrada.")
    if guia.status != "erro":
        raise HTTPException(400, "So e possivel reemitir guias em status de erro.")
    guia.status = "aguardando_confirmacao"
    guia.mensagem_erro = None
    db.commit()
    db.refresh(guia)
    return _serializar_guia(guia)


@router.get("/{guia_id}/pdf")
def baixar_pdf(guia_id: int, db: Session = Depends(get_db)):
    guia = db.get(Guia, guia_id)
    if guia is None or not guia.pdf_base64:
        raise HTTPException(404, "PDF da guia ainda nao disponivel.")
    conteudo = base64.b64decode(guia.pdf_base64)
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="guia-{guia.id}.pdf"'},
    )
