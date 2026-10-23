import base64
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.empresa_singleton import get_or_create_empresa
from app.models import Guia
from app.services import certificado_manager, gnre_boleto, gnre_client, gnre_regras, gnre_xml_builder
from app.services.nfe_parser import parse_nfe_xml

router = APIRouter(prefix="/api/guias", tags=["guias"])

_ENVIANDO_PARADO_SEGUNDOS = 300

_BRASILIA = timezone(timedelta(hours=-3))  # sem horario de verao desde 2019


def _hoje_brasilia():
    return datetime.now(_BRASILIA).date()


DESCRICAO_RECEITA = {
    "100102": "ICMS Consumidor Final Não Contribuinte Outra UF por Operação",
}


def _dados_boleto(guia: Guia, limite=None, nosso_numero=None, informacoes=None) -> gnre_boleto.DadosBoleto:
    nota = guia.nota_fiscal
    emitente = gnre_xml_builder.contribuinte_emitente_da_nfe(parse_nfe_xml(nota.xml_raw.encode("utf-8")))
    receita = gnre_xml_builder.RECEITA_DIFAL_POR_OPERACAO
    return gnre_boleto.DadosBoleto(
        linha_digitavel=guia.linha_digitavel,
        valor_total=guia.valor_total,
        uf_favorecida=guia.uf_favorecida or "",
        receita=receita,
        descricao_receita=DESCRICAO_RECEITA.get(receita, "ICMS DIFAL"),
        emitente_nome=emitente.razao_social if emitente else "",
        emitente_documento=emitente.cnpj if emitente else "",
        destinatario_nome=nota.destinatario_nome or "",
        destinatario_documento=nota.destinatario_doc or "",
        documento_origem=nota.chave_acesso,
        data_vencimento=guia.data_vencimento,
        data_limite_pagamento=limite,
        valor_difal=guia.valor_difal,
        valor_fcp=guia.valor_fcp,
        nosso_numero=nosso_numero or guia.numero_guia,
        informacoes=informacoes or [],
    )


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
        "tem_pdf": bool(guia.pdf_base64 or guia.linha_digitavel),
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
    # "enviando" que ficou parado (programa fechado no meio do envio) pode ser retomado.
    enviando_parado = (
        guia.status == "enviando" and (datetime.utcnow() - guia.atualizado_em).total_seconds() > _ENVIANDO_PARADO_SEGUNDOS
    )
    if guia.status not in ("aguardando_confirmacao", "erro") and not preso_sem_protocolo and not enviando_parado:
        if guia.status == "enviando":
            raise HTTPException(409, "Esta guia ja esta sendo enviada ao GNRE. Aguarde.")
        raise HTTPException(400, f"Guia em status '{guia.status}' nao pode ser confirmada/reenviada.")

    # Reserva atomica: so UMA requisicao consegue passar de status X para "enviando".
    # Sem isso, um duplo clique envia o lote duas vezes ao GNRE (aconteceu de verdade).
    reservada = db.execute(
        update(Guia).where(Guia.id == guia_id, Guia.status == guia.status).values(status="enviando", protocolo_lote=None)
    )
    db.commit()
    if reservada.rowcount != 1:
        raise HTTPException(409, "Esta guia ja esta sendo enviada ao GNRE. Aguarde.")
    db.refresh(guia)

    empresa = get_or_create_empresa(db)
    nota = guia.nota_fiscal

    try:
        cert_pem, key_pem = _carregar_cert_da_empresa(db)

        # A guia sai em nome de quem emitiu a NF-e (a filial), nao do CNPJ do
        # certificado. Se a nota nao trouxer os dados, cai na empresa cadastrada.
        empresa_builder = gnre_xml_builder.contribuinte_emitente_da_nfe(
            parse_nfe_xml(nota.xml_raw.encode("utf-8"))
        ) or gnre_xml_builder.ContribuinteEmitente(
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
            data_emissao=nota.data_emissao.date() if nota.data_emissao else None,
            # Vencimento = data da operacao; a data prevista de pagamento (hoje)
            # permite ao GNRE calcular juros/multa de guia paga em atraso.
            data_pagamento=_hoje_brasilia(),
            regras=gnre_regras.obter_regras(
                guia.uf_favorecida, gnre_xml_builder.RECEITA_DIFAL_POR_OPERACAO, cert_pem, key_pem
            )[0],
        )

        xml_lote = gnre_xml_builder.montar_lote_xml(empresa_builder, [guia_builder])
        resultado = gnre_client.enviar_lote(xml_lote, cert_pem, key_pem)

        if resultado.protocolo:
            guia.status = "enviada"
            guia.protocolo_lote = resultado.protocolo
            guia.mensagem_erro = None
        elif resultado.mensagem_rejeicao:
            # GNRE respondeu e recusou o lote (ex.: CNPJ do certificado nao
            # habilitado para o servico) -- nao foi aceito, entao "erro" (nao
            # "enviada") e mais correto; da pra tentar de novo via Reemitir.
            guia.status = "erro"
            guia.mensagem_erro = resultado.mensagem_rejeicao
        else:
            # O envio nao levantou excecao e nao veio nem numeroRecibo nem
            # mensagem de rejeicao reconhecida -- guarda a resposta bruta em
            # vez de descartar, senao fica impossivel diagnosticar o formato
            # real sem acesso ao ambiente de producao.
            guia.status = "enviada"
            guia.protocolo_lote = None
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
    # Tambem permite consultar guia em "erro" que tem protocolo: o lote pode ter
    # sido aceito pelo GNRE mesmo que a tela tenha ficado em erro (ex.: timeout na consulta).
    if guia.status not in ("enviada", "erro") or not guia.protocolo_lote:
        raise HTTPException(400, "Guia ainda nao foi enviada ao GNRE (sem protocolo de lote).")

    try:
        cert_pem, key_pem = _carregar_cert_da_empresa(db)
        resultado = gnre_client.consultar_resultado_lote(guia.protocolo_lote, cert_pem, key_pem)

        if not resultado.guias:
            if resultado.situacao_processo_descricao:
                guia.mensagem_erro = (
                    f"Sem guia no retorno ainda (codigo {resultado.situacao_processo_codigo}: "
                    f"{resultado.situacao_processo_descricao})."
                )
            else:
                # Formato de resposta nao reconhecido -- mostra o bruto pra diagnosticar.
                guia.mensagem_erro = f"Resposta da consulta nao reconhecida. Resposta bruta: {resultado.resposta_bruta[:1200]}"
        else:
            guia_result = resultado.guias[0]
            if guia_result.situacao == gnre_client.SITUACAO_GUIA_PROCESSADA:
                guia.status = "emitida"
                guia.linha_digitavel = guia_result.linha_digitavel
                guia.mensagem_erro = None
                if guia_result.valor_gnre:
                    guia.valor_total = guia_result.valor_gnre  # inclui juros/multa se houver
                if guia_result.nosso_numero:
                    guia.numero_guia = guia_result.nosso_numero
                try:
                    limite = date.fromisoformat(guia_result.data_limite_pagamento) if guia_result.data_limite_pagamento else None
                    pdf = gnre_boleto.gerar_pdf(
                        _dados_boleto(guia, limite, guia_result.nosso_numero, guia_result.informacoes)
                    )
                    guia.pdf_base64 = base64.b64encode(pdf).decode("ascii")
                except Exception as exc_pdf:  # noqa: BLE001 -- a guia ja esta emitida; o PDF pode ser refeito depois
                    guia.mensagem_erro = f"Guia emitida, mas nao foi possivel montar o PDF: {exc_pdf}"
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
    if guia is None:
        raise HTTPException(404, "Guia nao encontrada.")
    if guia.pdf_base64:
        conteudo = base64.b64decode(guia.pdf_base64)
    elif guia.linha_digitavel:
        try:
            conteudo = gnre_boleto.gerar_pdf(_dados_boleto(guia))
        except gnre_boleto.BoletoInvalidoError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        raise HTTPException(404, "Boleto ainda nao disponivel: a guia ainda nao foi emitida pelo GNRE.")
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="gnre-{guia.uf_favorecida}-{guia.id}.pdf"'},
    )
