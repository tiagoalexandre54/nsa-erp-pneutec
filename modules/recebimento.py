"""
Tela de Recebimento, Alocação de Pallets e Gestão FIFO.
"""
import streamlit as st
import pandas as pd
from modules.database import salvar_dados


def tela_recebimento():
    st.title("📥 Recebimento e Gestão de Pátio (FIFO)")

    df = st.session_state.bd_pneus

    if df.empty:
        st.warning("Nenhuma OS cadastrada no sistema. Importe o CSV pelo Painel PPCP.")
        return

    aba1, aba2, aba3 = st.tabs([
        "📦 1. Alocar no Pallet (Bipe)",
        "🔄 2. Movimentar/Transferir",
        "📋 3. Mapa FIFO (Puxar Produção)",
    ])

    with aba1:
        _aba_alocar_pallet(df)
    with aba2:
        _aba_movimentar_pallet(df)
    with aba3:
        _aba_mapa_fifo(df)


# ── 1. Alocação (Bipe para colocar no Pallet) ────────────────────────────────
def _aba_alocar_pallet(df: pd.DataFrame):
    st.subheader("Alocação Inicial no Pátio")
    st.info("Bipe os pneus recém-chegados para informar em qual Pallet eles estão sendo guardados.")

    sem_pallet = df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] == '')]

    col1, col2 = st.columns([1, 2])

    with col1:
        pallet_destino = st.text_input(
            "📍 Nome/Número do Pallet:",
            placeholder="Ex: P-01, GAIOLA-A...",
        ).strip().upper()

        if 'recebimento_key' not in st.session_state:
            st.session_state.recebimento_key = 0

        os_bipada = st.text_input(
            "📷 Bipe a OS (NRORDEM):",
            key=f"bipe_receb_{st.session_state.recebimento_key}",
            placeholder="Aguardando leitor...",
        ).strip()

        if os_bipada:
            if not pallet_destino:
                st.error("⚠️ Digite o nome do Pallet ANTES de bipar o pneu!")
            else:
                idx = df.index[df['NRORDEM'] == os_bipada].tolist()
                if idx:
                    i = idx[0]
                    status_atual = str(df.at[i, 'STATUS']).strip()
                    pallet_atual = str(df.at[i, 'LOCAL_PALLET']).strip()

                    if status_atual != 'Aguardando':
                        st.error(f"🛑 A OS {os_bipada} já está **{status_atual}**. Não pode ser recebida.")
                    elif pallet_atual == pallet_destino:
                        st.warning(f"⚠️ A OS {os_bipada} já está no pallet **{pallet_destino}**.")
                    else:
                        st.session_state.bd_pneus.at[i, 'LOCAL_PALLET'] = pallet_destino
                        salvar_dados(st.session_state.bd_pneus)
                        st.session_state.msg_receb = f"✅ OS {os_bipada} guardada no **{pallet_destino}**!"
                        st.session_state.recebimento_key += 1
                        st.rerun()
                else:
                    st.error("❌ OS não encontrada no sistema.")

        if st.session_state.get('msg_receb'):
            st.success(st.session_state.msg_receb)
            st.session_state.msg_receb = None

    with col2:
        st.markdown(f"**Pneus aguardando alocação: {len(sem_pallet)}**")
        if not sem_pallet.empty:
            st.dataframe(
                sem_pallet[['IDPEDIDOPNEU', 'CLIENTE', 'NRORDEM', 'DESENHO']],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("🎉 Todos os pneus 'Aguardando' já estão alocados em pallets!")


# ── 2. Movimentação (Transferir de um Pallet para outro) ─────────────────────
def _aba_movimentar_pallet(df: pd.DataFrame):
    st.subheader("Transferência de Pallets")
    st.write("Mova pneus de um pallet para outro para organizar o espaço (consolidar cargas).")

    pallets_ativos = sorted(
        df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] != '')]['LOCAL_PALLET']
        .unique().tolist()
    )

    if not pallets_ativos:
        st.info("Não há pallets com pneus aguardando no momento.")
        return

    c1, c2 = st.columns(2)
    pallet_origem  = c1.selectbox("De qual Pallet deseja retirar?", pallets_ativos, key="mov_origem")
    pallet_destino = c2.text_input(
        "Para qual Pallet vai? (Digite o nome):", placeholder="Ex: P-02"
    ).strip().upper()

    pneus_origem = df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] == pallet_origem)]

    st.markdown(f"**Pneus atualmente no {pallet_origem}: {len(pneus_origem)}**")

    tipo_mov = st.radio(
        "O que deseja mover?",
        ["Mover Pallet Inteiro", "Mover Pneus Específicos"],
        horizontal=True,
    )

    if tipo_mov == "Mover Pallet Inteiro":
        st.dataframe(
            pneus_origem[['NRORDEM', 'CLIENTE', 'DESENHO', 'NRSERIE']],
            use_container_width=True, hide_index=True,
        )
        if st.button(
            f"🔄 Transferir TODOS para {pallet_destino or '...'}?", type="primary"
        ):
            if not pallet_destino:
                st.error("Digite o nome do Pallet de destino.")
            elif pallet_origem == pallet_destino:
                st.warning("A origem e o destino são iguais.")
            else:
                st.session_state.bd_pneus.loc[pneus_origem.index, 'LOCAL_PALLET'] = pallet_destino
                salvar_dados(st.session_state.bd_pneus)
                st.success(f"✅ Todos os pneus de **{pallet_origem}** movidos para **{pallet_destino}**!")
                st.rerun()
    else:
        os_selecionadas = st.multiselect(
            "Selecione as OS que serão movidas:",
            pneus_origem['NRORDEM'].tolist(),
            format_func=lambda x: (
                f"OS: {x} | {df[df['NRORDEM'] == x]['CLIENTE'].values[0]}"
            ),
        )
        if st.button(
            f"🔄 Transferir Selecionados para {pallet_destino or '...'}?", type="primary"
        ):
            if not pallet_destino:
                st.error("Digite o nome do Pallet de destino.")
            elif not os_selecionadas:
                st.warning("Selecione pelo menos um pneu para mover.")
            else:
                idx_mover = df[df['NRORDEM'].isin(os_selecionadas)].index
                st.session_state.bd_pneus.loc[idx_mover, 'LOCAL_PALLET'] = pallet_destino
                salvar_dados(st.session_state.bd_pneus)
                st.success(f"✅ {len(os_selecionadas)} pneu(s) movidos para **{pallet_destino}**!")
                st.rerun()


# ── 3. Mapa FIFO (Visualização de Prioridade) ────────────────────────────────
def _aba_mapa_fifo(df: pd.DataFrame):
    st.subheader("Mapa FIFO (First In, First Out)")
    st.info("Puxe para a Produção sempre os pallets do TOPO desta lista (os mais antigos na fábrica).")

    aguardando = df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] != '')].copy()

    if aguardando.empty:
        st.success("O pátio está vazio! Nenhum pneu aguardando.")
        return

    # Converte DATA_ENTRADA para datetime (tenta com hora e sem hora)
    aguardando['DATA_CALCULO'] = pd.to_datetime(
        aguardando['DATA_ENTRADA'], format="%d/%m/%Y %H:%M:%S", errors='coerce'
    )
    mask_nat = aguardando['DATA_CALCULO'].isna()
    aguardando.loc[mask_nat, 'DATA_CALCULO'] = pd.to_datetime(
        aguardando.loc[mask_nat, 'DATA_ENTRADA'], format="%d/%m/%Y", errors='coerce'
    )

    resumo = (
        aguardando.groupby('LOCAL_PALLET')
        .agg(
            Qtd_Pneus        =('NRORDEM',       'count'),
            Data_Mais_Antiga =('DATA_CALCULO',  'min'),
            Clientes         =('CLIENTE',        lambda x: ', '.join(x.unique())),
        )
        .reset_index()
        .sort_values('Data_Mais_Antiga', ascending=True, na_position='last')
    )

    resumo['Data do Pneu + Antigo'] = (
        resumo['Data_Mais_Antiga'].dt.strftime('%d/%m/%Y').fillna('Sem data')
    )

    st.markdown("---")

    for pos, (_, row) in enumerate(resumo.iterrows()):
        pallet     = row['LOCAL_PALLET']
        qtd        = row['Qtd_Pneus']
        data_antiga = row['Data do Pneu + Antigo']
        clientes   = row['Clientes']

        if pos == 0:
            cor_bg  = "#f8d7da"
            cor_txt = "#721c24"
            icone   = "🚨 PRIORIDADE 1"
        else:
            cor_bg  = "#e2e3e5"
            cor_txt = "#383d41"
            icone   = "📦"

        st.markdown(
            f"""
            <div style="background:{cor_bg};color:{cor_txt};border-radius:8px;
                        padding:12px;margin-bottom:10px;border:1px solid #ccc;">
              <h4 style="margin:0 0 5px 0;">{icone} — Pallet: <b>{pallet}</b></h4>
              <p style="margin:0;font-size:14px;">
                <b>Qtd:</b> {qtd} pneus &nbsp;&nbsp;|&nbsp;&nbsp;
                <b>Pneu mais antigo:</b> {data_antiga} &nbsp;&nbsp;|&nbsp;&nbsp;
                <b>Clientes:</b> {clientes}
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
