"""
Tela 1 — Painel de Controle do PPCP.
"""
import streamlit as st
import pandas as pd
from modules.database import salvar_dados, importar_csv_externo, excluir_os
from modules.pdf_import import extrair_pneus_pdf, verificar_dependencias


def tela_painel_pcp():
    st.title("📊 Painel de Controle de PPCP")

    df: pd.DataFrame = st.session_state.bd_pneus

    # ── Indicadores rápidos ──────────────────────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Aguardando Entrada", len(df[df['STATUS'] == 'Aguardando']))
    col2.metric("Em Limpeza",         len(df[df['STATUS'] == 'Em Limpeza']))
    col3.metric("Aguard. Produção",   len(df[df['STATUS'] == 'Aguardando Produção']))
    col4.metric("Em Produção",        len(df[df['STATUS'] == 'Em Produção']))
    col5.metric("Expedidos",          len(df[df['STATUS'] == 'Expedido']))
    col6.metric("Total de OS",        len(df))

    st.markdown("---")

    # ── Filtros ──────────────────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=False):
        col_f1, col_f2 = st.columns(2)
        clientes    = ["Todos"] + sorted(df['CLIENTE'].replace('', pd.NA).dropna().unique().tolist())
        status_opts = ["Todos"] + sorted(df['STATUS'].replace('', pd.NA).dropna().unique().tolist())
        filtro_cliente = col_f1.selectbox("Cliente:", clientes,    key="filtro_cliente")
        filtro_status  = col_f2.selectbox("Status:",  status_opts, key="filtro_status")

    df_view = df.copy()
    if filtro_cliente != "Todos":
        df_view = df_view[df_view['CLIENTE'] == filtro_cliente]
    if filtro_status != "Todos":
        df_view = df_view[df_view['STATUS'] == filtro_status]

    # ── Tabela com cores por status ──────────────────────────────────────────
    if df_view.empty:
        st.info("Nenhuma OS encontrada com os filtros aplicados.")
    else:
        st.dataframe(
            df_view.style.apply(_colorir_status, axis=1),
            use_container_width=True
        )
    st.caption(f"{len(df_view)} OS exibidas de {len(df)} total")

    st.markdown("---")

    # ── Importação de CSV ────────────────────────────────────────────────────
    with st.expander("📂 Importar CSV (rel 1 / rel 2)", expanded=False):
        st.caption("Colunas de data aceitas: DATA_ENTRADA, DT_COLETA, DATA_EMISSAO, DATA_SAIDA, DATA_ENTREGA, DT_PREVISTA...")

        modo_import = st.radio(
            "Modo de importação:",
            [
                "➕ Adicionar novas OS (mantém banco atual)",
                "🔄 Substituir banco completo (protege Em Produção e Expedidos)",
            ],
            key="modo_importacao",
        )

        arquivo = st.file_uploader("Selecione o arquivo CSV:", type=["csv"], key="uploader_csv")
        arquivo_id = arquivo.file_id if arquivo else None

        if arquivo and arquivo_id != st.session_state.get("ultimo_arquivo_importado"):
            try:
                import tempfile, os as _os
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                    tmp.write(arquivo.read())
                    tmp_path = tmp.name

                df_novo = importar_csv_externo(tmp_path)
                _os.unlink(tmp_path)

                # Mostra prévia antes de confirmar
                st.write("**Prévia do arquivo:**")
                st.dataframe(df_novo.head(20), use_container_width=True)

                if modo_import.startswith("➕"):
                    # ── Modo ADICIONAR: só insere OS novas ──────────────────
                    novos      = df_novo[~df_novo['NRORDEM'].isin(df['NRORDEM'])].copy()
                    duplicados = len(df_novo) - len(novos)

                    c1, c2 = st.columns(2)
                    c1.metric("Novas OS", len(novos))
                    c2.metric("Já existentes (ignoradas)", duplicados)

                    if not novos.empty:
                        if st.button(f"✅ Confirmar importação de {len(novos)} OS", key="confirmar_csv"):
                            df_concat = pd.concat(
                                [st.session_state.bd_pneus, novos], ignore_index=True
                            )
                            if not salvar_dados(df_concat):
                                st.error("⚠️ Falha ao salvar — verifique a conexão e tente importar novamente.")
                            else:
                                st.session_state.bd_pneus = df_concat
                                st.session_state.ultimo_arquivo_importado = arquivo_id
                                st.success(f"✅ {len(novos)} OS importada(s) com sucesso!")
                                st.rerun()
                    else:
                        st.session_state.ultimo_arquivo_importado = arquivo_id
                        st.info("Todas as OS deste arquivo já estão no sistema.")

                else:
                    # ── Modo SUBSTITUIR: df_novo vira o novo banco, ──────────
                    # mas PRESERVA o progresso já feito no sistema:
                    #  • Em Limpeza / Em Produção / Expedido → mantém status + datas + pallet
                    #  • Aguardando mas já alocado no pátio → mantém pallet +
                    #    data de chegada (não perde o recebimento ao re-importar)
                    df_atual = st.session_state.bd_pneus
                    protegidos = 0       # já bipados (Em Limpeza/Em Produção/Expedido)
                    patio_mantidos = 0   # alocados no pátio aguardando
                    for i, row in df_novo.iterrows():
                        ordem = row['NRORDEM']
                        os_existente = df_atual[df_atual['NRORDEM'] == ordem]
                        if os_existente.empty:
                            continue
                        ex = os_existente.iloc[0]
                        status_banco = ex['STATUS']
                        pallet_banco = str(ex['LOCAL_PALLET']).strip()

                        if status_banco in ['Em Limpeza', 'Aguardando Produção', 'Em Produção', 'Expedido']:
                            df_novo.at[i, 'STATUS']       = status_banco
                            df_novo.at[i, 'DATA_ENTRADA'] = ex['DATA_ENTRADA']
                            df_novo.at[i, 'DATA_SAIDA']   = ex['DATA_SAIDA']
                            df_novo.at[i, 'LOCAL_PALLET'] = ex['LOCAL_PALLET']
                            df_novo.at[i, 'RUA_PRODUCAO'] = ex['RUA_PRODUCAO']
                            protegidos += 1
                        elif pallet_banco:
                            # Aguardando, mas já recebido no pátio: mantém a
                            # alocação e a data de chegada.
                            df_novo.at[i, 'LOCAL_PALLET'] = ex['LOCAL_PALLET']
                            df_novo.at[i, 'DATA_ENTRADA'] = ex['DATA_ENTRADA']
                            patio_mantidos += 1

                    novas_no_arquivo   = len(df_novo[~df_novo['NRORDEM'].isin(df_atual['NRORDEM'])])
                    removidas_do_banco = len(df_atual[~df_atual['NRORDEM'].isin(df_novo['NRORDEM'])])

                    st.warning(
                        f"⚠️ **ATENÇÃO — Modo Substituição:**  \n"
                        f"• **{len(df_novo)}** OS no arquivo novo  \n"
                        f"• **{novas_no_arquivo}** OS serão adicionadas  \n"
                        f"• **{removidas_do_banco}** OS do banco atual não estão no arquivo (serão removidas)  \n"
                        f"• **{protegidos}** OS protegidas (Em Produção / Expedido)  \n"
                        f"• **{patio_mantidos}** OS aguardando com pallet preservado (recebimento)"
                    )

                    if st.button(
                        f"🔄 Confirmar SUBSTITUIÇÃO do banco ({len(df_novo)} OS)",
                        key="confirmar_substituir",
                        type="primary",
                    ):
                        df_substituido = df_novo.reset_index(drop=True)
                        if not salvar_dados(df_substituido):
                            st.error("⚠️ Falha ao salvar — verifique a conexão e tente novamente. Banco NÃO foi substituído.")
                        else:
                            st.session_state.bd_pneus = df_substituido
                            st.session_state.ultimo_arquivo_importado = arquivo_id
                            st.success(
                                f"✅ Banco substituído! {len(df_novo)} OS carregadas. "
                                f"{protegidos} com status preservado, {patio_mantidos} com pallet mantido."
                            )
                            st.rerun()

            except ValueError as e:
                st.error(f"⚠️ Erro na estrutura do CSV:\n\n{e}")
            except Exception as e:
                st.error(f"❌ Erro inesperado ao importar: {e}")

    # ── Importação de PDF ────────────────────────────────────────────────────
    with st.expander("📄 Importar PDF (Pedido de Recapagem)", expanded=False):
        pdf_ok, pdf_msg = verificar_dependencias()

        if not pdf_ok:
            st.warning(f"⚠️ {pdf_msg}")
            if st.button("📦 Instalar pdfplumber agora"):
                import subprocess, sys
                with st.spinner("Instalando..."):
                    r = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "pdfplumber"],
                        capture_output=True, text=True
                    )
                if r.returncode == 0:
                    st.success("✅ Instalado! Recarregue a página.")
                else:
                    st.error(f"Erro:\n{r.stderr}")
        else:
            pdf_arquivo = st.file_uploader(
                "Selecione o PDF do Pedido de Recapagem:",
                type=["pdf"], key="uploader_pdf"
            )
            pdf_id = pdf_arquivo.file_id if pdf_arquivo else None

            if pdf_arquivo and pdf_id != st.session_state.get("ultimo_pdf_importado"):
                try:
                    import tempfile, os as _os
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                        tmp.write(pdf_arquivo.read())
                        tmp_path = tmp.name

                    df_pdf = extrair_pneus_pdf(tmp_path)
                    _os.unlink(tmp_path)

                    # ── Cruzamento PDF × CSV ─────────────────────────────────
                    # Para cada pneu do PDF, busca NRSERIE no sistema:
                    #   ENCONTROU → atualiza o registro existente para
                    #               STATUS=Aguardando + datas do PDF
                    #               (nova coleta chegou, precisa bipar)
                    #   NÃO ENCONTROU → cria registro novo com Nr.Pedido
                    df_atual = st.session_state.bd_pneus.copy()
                    mapa_serie_idx = {
                        str(row['NRSERIE']).strip(): i
                        for i, row in df_atual.iterrows()
                        if str(row['NRSERIE']).strip()
                    }

                    atualizados  = []   # linhas que já existem no CSV
                    novos_lista  = []   # linhas novas (não estão no CSV)

                    for _, row_pdf in df_pdf.iterrows():
                        serie = str(row_pdf['NRSERIE']).strip()
                        if serie in mapa_serie_idx:
                            i = mapa_serie_idx[serie]
                            atualizados.append({
                                'idx':        i,
                                'NRORDEM':    df_atual.at[i, 'NRORDEM'],
                                'NRSERIE':    serie,
                                'CLIENTE':    df_atual.at[i, 'CLIENTE'],
                                'DESENHO':    df_atual.at[i, 'DESENHO'],
                                'STATUS_ANT': df_atual.at[i, 'STATUS'],
                                'DATA_ENTRADA_PDF': row_pdf['DATA_ENTRADA'],
                                'DATA_SAIDA_PDF':   row_pdf['DATA_SAIDA'],
                            })
                        else:
                            novos_lista.append(row_pdf)

                    # Prévia
                    st.write("**Resultado do cruzamento PDF × CSV:**")
                    if atualizados:
                        st.markdown(f"**✅ {len(atualizados)} pneu(s) identificado(s) no CSV — serão marcados como Aguardando:**")
                        df_atualiz_preview = pd.DataFrame([{
                            'NRORDEM':        a['NRORDEM'],
                            'NRSERIE':        a['NRSERIE'],
                            'CLIENTE':        a['CLIENTE'],
                            'DESENHO':        a['DESENHO'],
                            'Status Atual':   a['STATUS_ANT'],
                            'Novo Status':    '🟡 Aguardando',
                            'Data Coleta':    a['DATA_ENTRADA_PDF'],
                            'Entrega Prev.':  a['DATA_SAIDA_PDF'],
                        } for a in atualizados])
                        st.dataframe(df_atualiz_preview, use_container_width=True, hide_index=True)

                    if novos_lista:
                        st.markdown(f"**📄 {len(novos_lista)} pneu(s) novo(s) — não encontrado(s) no CSV:**")
                        df_novos_prev = pd.DataFrame(novos_lista)[['NRORDEM','NRSERIE','DESENHO','DATA_ENTRADA','DATA_SAIDA']]
                        st.dataframe(df_novos_prev, use_container_width=True, hide_index=True)

                    if not atualizados and not novos_lista:
                        st.session_state.ultimo_pdf_importado = pdf_id
                        st.info("Nenhum pneu novo neste PDF.")
                    else:
                        label_btn = f"✅ Confirmar: {len(atualizados)} atualização(ões)"
                        if novos_lista:
                            label_btn += f" + {len(novos_lista)} inserção(ões)"

                        if st.button(label_btn, key="confirmar_pdf", type="primary"):
                            df_base = st.session_state.bd_pneus.copy()

                            # Atualiza registros existentes
                            for a in atualizados:
                                i = a['idx']
                                df_base.at[i, 'STATUS']       = 'Aguardando'
                                df_base.at[i, 'DATA_ENTRADA'] = a['DATA_ENTRADA_PDF']
                                df_base.at[i, 'DATA_SAIDA']   = a['DATA_SAIDA_PDF']

                            # Insere pneus novos
                            if novos_lista:
                                df_base = pd.concat(
                                    [df_base, pd.DataFrame(novos_lista)],
                                    ignore_index=True
                                )

                            if not salvar_dados(df_base):
                                st.error("⚠️ Falha ao salvar — verifique a conexão e tente importar novamente.")
                            else:
                                st.session_state.bd_pneus = df_base
                                st.session_state.ultimo_pdf_importado = pdf_id
                                st.success(
                                    f"✅ {len(atualizados)} OS marcada(s) como Aguardando + "
                                    f"{len(novos_lista)} nova(s) inserida(s). "
                                    f"Acesse a tela 🏭 Entrada para bipar!"
                                )
                                st.rerun()

                except ValueError as e:
                    st.error(f"⚠️ Erro ao ler o PDF:\n\n{e}")
                except Exception as e:
                    st.error(f"❌ Erro inesperado: {e}")

    # ── Excluir OS ───────────────────────────────────────────────────────────
    with st.expander("🗑️ Excluir OS", expanded=False):
        _bloco_exclusao()

    # ── Zerar sistema ────────────────────────────────────────────────────────
    with st.expander("⚠️ Zerar Sistema", expanded=False):
        _bloco_zerar()

    # ── Salvar manual ────────────────────────────────────────────────────────
    if st.button("💾 Salvar dados agora"):
        if salvar_dados(st.session_state.bd_pneus):
            st.success("✅ Dados salvos.")
        else:
            st.error("⚠️ Falha ao salvar — verifique a conexão e tente novamente.")


def _bloco_exclusao():
    df: pd.DataFrame = st.session_state.bd_pneus

    if df.empty:
        st.info("Nenhuma OS cadastrada.")
        return

    st.warning("⚠️ A exclusão é permanente. Use somente para corrigir importações erradas.")

    # Monta lista legível: "17399 — AUTO VIAÇÃO TRANSCAP LTDA (Aguardando)"
    opcoes = {
        f"{row['NRORDEM']} — {row['CLIENTE']} ({row['STATUS']})": row['NRORDEM']
        for _, row in df.iterrows()
    }

    selecao = st.selectbox(
        "Selecione a OS para excluir:",
        options=list(opcoes.keys()),
        key="excluir_os_select"
    )

    if selecao:
        nrordem_alvo = opcoes[selecao]
        idx = df.index[df['NRORDEM'] == nrordem_alvo].tolist()

        if idx:
            i = idx[0]
            c1, c2, c3 = st.columns(3)
            c1.write(f"**OS:** {df.at[i, 'NRORDEM']}")
            c2.write(f"**Cliente:** {df.at[i, 'CLIENTE']}")
            c3.write(f"**Status:** {df.at[i, 'STATUS']}")
            c1.write(f"**Série:** {df.at[i, 'NRSERIE']}")
            c2.write(f"**Desenho:** {df.at[i, 'DESENHO']}")

        confirmar = st.checkbox(
            f"✅ Confirmo que desejo excluir a OS **{nrordem_alvo}** permanentemente",
            key="check_confirmar_exclusao"
        )

        if confirmar:
            if st.button("🗑️ Excluir agora", type="primary", key="btn_excluir"):
                ok, msg = excluir_os(nrordem_alvo)
                if ok:
                    # Limpa seleção e flags
                    for k in ["check_confirmar_exclusao", "excluir_os_select"]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")


def _bloco_zerar():
    """Apaga todas as OS do sistema após dupla confirmação."""
    from modules.database import COLUNAS, salvar_dados as _salvar

    st.error(
        "🚨 **ATENÇÃO:** Esta ação apaga **TODAS** as Ordens de Serviço do sistema.\n\n"
        "Não é possível desfazer. Use somente para iniciar um novo ciclo."
    )

    total = len(st.session_state.bd_pneus)
    st.metric("OS que serão apagadas", total)

    c1, c2 = st.columns(2)
    conf1 = c1.checkbox("Entendo que todos os dados serão perdidos", key="zerar_check1")
    conf2 = c2.checkbox("Confirmo o zeramento do sistema",           key="zerar_check2")

    if conf1 and conf2:
        if st.button("🔴 ZERAR TUDO AGORA", type="primary", key="btn_zerar"):
            # Substitui por DataFrame vazio com as colunas corretas
            df_vazio = pd.DataFrame(columns=COLUNAS)
            if not _salvar(df_vazio):
                st.error("⚠️ Falha ao salvar — verifique a conexão e tente novamente. Sistema NÃO foi zerado.")
            else:
                st.session_state.bd_pneus = df_vazio
                # Limpa todos os flags de importação para permitir reimportar os mesmos arquivos
                for k in ["ultimo_arquivo_importado", "ultimo_pdf_importado",
                          "zerar_check1", "zerar_check2"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.success("✅ Sistema zerado com sucesso. Todas as OS foram removidas.")
                st.rerun()


def _colorir_status(row: pd.Series):
    """Aplica cor de fundo conforme o STATUS de cada linha."""
    cores = {
        'Aguardando':          'background-color: #fff3cd; color: #856404',
        'Em Limpeza':          'background-color: #e8eaf6; color: #1a237e',
        'Aguardando Produção': 'background-color: #fde8d8; color: #8a4b08',
        'Em Produção':         'background-color: #cce5ff; color: #004085',
        'Expedido':            'background-color: #d4edda; color: #155724',
    }
    status = str(row.get('STATUS', '')).strip()
    return [cores.get(status, '')] * len(row)
