"""
Tela 3 — Expedição e Montagem de Carga.
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados


def tela_expedicao():
    st.title("🚚 Expedição e Montagem de Carga")

    df = st.session_state.bd_pneus

    clientes_disponiveis = sorted(
        df['CLIENTE'].replace('', pd.NA).dropna().unique().tolist()
    )

    if not clientes_disponiveis:
        st.warning("Nenhum cliente cadastrado. Importe as OS pelo Painel PPCP.")
        return

    # ── 1. Seleção do cliente ────────────────────────────────────────────────
    st.subheader("1. Selecione o cliente que está sendo carregado:")
    cliente_selecionado = st.selectbox("Cliente Destino:", clientes_disponiveis)

    prontos   = df[(df['CLIENTE'] == cliente_selecionado) & (df['STATUS'].isin(['Aguardando', 'Em Produção']))]
    expedidos = df[(df['CLIENTE'] == cliente_selecionado) & (df['STATUS'] == 'Expedido')]
    total_cli = df[df['CLIENTE'] == cliente_selecionado]

    col1, col2, col3 = st.columns(3)
    col1.metric("Prontos para Expedir", len(prontos))
    col2.metric("Já Expedidos",         len(expedidos))
    col3.metric("Total do Cliente",     len(total_cli))

    st.markdown("---")

    # ── 2. Painel de pneus prontos para bipar ────────────────────────────────
    _painel_prontos_expedir(cliente_selecionado)

    # ── 3. Campo de bipe ─────────────────────────────────────────────────────
    if 'expedicao_key' not in st.session_state:
        st.session_state.expedicao_key = 0

    st.subheader("3. Bipe os pneus que estão subindo no caminhão:")
    os_expedicao = st.text_input(
        "Bipe a OS (NRORDEM):",
        key=f"bipe_saida_{st.session_state.expedicao_key}",
        placeholder="Aguardando leitura do código de barras..."
    )

    if os_expedicao:
        os_expedicao = os_expedicao.strip()
        df = st.session_state.bd_pneus
        idx = df.index[df['NRORDEM'] == os_expedicao].tolist()

        if idx:
            i = idx[0]
            cliente_da_os = str(df.at[i, 'CLIENTE']).strip()
            status_atual  = str(df.at[i, 'STATUS']).strip()

            # ── TRAVA DE SEGURANÇA ───────────────────────────────────────────
            if cliente_da_os != cliente_selecionado:
                st.error(
                    f"🛑 **ALERTA CRÍTICO — PNEU TROCADO!**\n\n"
                    f"Esta OS pertence a **{cliente_da_os}**, "
                    f"mas o carregamento selecionado é para **{cliente_selecionado}**!\n\n"
                    f"**NÃO EMBARQUE ESTE PNEU.**"
                )

            elif status_atual == 'Expedido':
                st.warning(
                    f"⚠️ Este pneu já foi expedido "
                    f"em {df.at[i, 'DATA_SAIDA'] or '(data não registrada)'}. "
                    f"Verifique duplicidade."
                )

            elif status_atual in ('Aguardando', 'Em Produção'):
                df.at[i, 'STATUS']     = 'Expedido'
                df.at[i, 'DATA_SAIDA'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                salvar_dados(df)
                st.session_state.msg_expedicao = {
                    'tipo': 'sucesso',
                    'texto': (
                        f"📦 **LIBERADO!** Pneu **{df.at[i, 'DESENHO']}** "
                        f"(Série **{df.at[i, 'NRSERIE']}**) adicionado à carga de "
                        f"**{cliente_selecionado}**."
                    )
                }
                st.session_state.expedicao_key += 1
                st.rerun()

            else:
                st.warning(
                    f"⚠️ Status inesperado: **'{status_atual}'**. Verifique o cadastro."
                )
        else:
            st.error(
                f"❌ OS **{os_expedicao}** não encontrada! "
                f"Verifique se a importação do PPCP está atualizada."
            )

    # ── Feedback do último bipe ──────────────────────────────────────────────
    if st.session_state.get('msg_expedicao'):
        msg = st.session_state.msg_expedicao
        if msg['tipo'] == 'sucesso':
            st.success(msg['texto'])
        st.session_state.msg_expedicao = None

    st.markdown("---")

    # ── 4. Romaneio de Carga ─────────────────────────────────────────────────
    st.subheader(f"📋 Romaneio de Carga — {cliente_selecionado}")
    df = st.session_state.bd_pneus
    carga = df[(df['CLIENTE'] == cliente_selecionado) & (df['STATUS'] == 'Expedido')].copy()

    if carga.empty:
        st.info("Nenhum pneu expedido para este cliente ainda.")
    else:
        carga_exibir = carga[['NRORDEM', 'DESENHO', 'NRSERIE', 'DATA_SAIDA']].copy()
        carga_exibir.index = range(1, len(carga_exibir) + 1)
        st.dataframe(carga_exibir, use_container_width=True)
        st.success(f"✅ Total de pneus na carga: **{len(carga)}**")


def _painel_prontos_expedir(cliente: str):
    """
    Exibe painel com todos os pneus prontos para subir no caminhão
    do cliente selecionado (STATUS Aguardando ou Em Produção).
    Some automaticamente quando todos forem bipados.
    """
    df = st.session_state.bd_pneus
    prontos = df[
        (df['CLIENTE'] == cliente) &
        (df['STATUS'].isin(['Aguardando', 'Em Produção']))
    ].copy()

    if prontos.empty:
        st.success(f"✅ Todos os pneus de **{cliente}** já foram expedidos!")
        return

    total = len(prontos)
    entrega = prontos['DATA_SAIDA'].iloc[0].strip() if prontos['DATA_SAIDA'].iloc[0].strip() else ''

    st.markdown(
        f"""
        <div style="background:#cce5ff;border:2px solid #004085;border-radius:8px;
                    padding:16px;margin-bottom:16px;">
          <h4 style="color:#004085;margin:0 0 8px 0;">
            📦 {total} PNEU(S) PRONTOS PARA EMBARQUE — {cliente}
            {"&nbsp;&nbsp;|&nbsp;&nbsp;Entrega prevista: " + entrega if entrega else ""}
          </h4>
          <p style="color:#004085;margin:0;">
            Bipe os NROROEMs abaixo no campo de leitura para registrar a saída no caminhão.
          </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Tabela com os NROROEMs a bipar
    exibir = prontos[['NRORDEM', 'NRSERIE', 'DESENHO', 'STATUS', 'DATA_SAIDA']].copy()
    exibir = exibir.rename(columns={'DATA_SAIDA': 'Entrega Prevista'})
    exibir = exibir.reset_index(drop=True)
    exibir.index = range(1, len(exibir) + 1)

    st.dataframe(
        exibir.style.apply(_colorir_status_expedicao, axis=1),
        use_container_width=True
    )

    st.markdown("---")


def _colorir_status_expedicao(row: pd.Series):
    cores = {
        'Aguardando':  'background-color: #fff3cd; color: #856404',
        'Em Produção': 'background-color: #cce5ff; color: #004085',
    }
    return [cores.get(str(row.get('STATUS', '')).strip(), '')] * len(row)
