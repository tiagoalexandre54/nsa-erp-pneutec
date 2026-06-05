"""
Tela de Recebimento, Alocação de Pallets e Gestão FIFO.
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados


def tela_recebimento():
    st.title("📥 Recebimento e Gestão de Pátio (FIFO)")

    df = st.session_state.bd_pneus

    if df.empty:
        st.warning("Nenhuma OS cadastrada no sistema. Importe o CSV pelo Painel PPCP.")
        return

    aba1, aba2, aba3, aba4 = st.tabs([
        "📦 1. Alocar no Pallet (Bipe)",
        "🔄 2. Movimentar/Transferir",
        "🗺️ 3. Mapa de Capacidade",
        "📋 4. Mapa FIFO (Puxar Produção)",
    ])

    with aba1:
        _aba_alocar_pallet(df)
    with aba2:
        _aba_movimentar_pallet(df)
    with aba3:
        _aba_mapa_capacidade(df)
    with aba4:
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
                        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        st.session_state.bd_pneus.at[i, 'LOCAL_PALLET']  = pallet_destino
                        # Carimba a data de CHEGADA/recebimento no pátio
                        st.session_state.bd_pneus.at[i, 'DATA_ENTRADA'] = agora
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


# ── 3. Mapa de Capacidade (Visualização por Pallet) ──────────────────────────
def _aba_mapa_capacidade(df: pd.DataFrame):
    st.subheader("Mapa de Capacidade dos Pallets")

    aguardando = df[df['STATUS'] == 'Aguardando'].copy()
    com_pallet = aguardando[aguardando['LOCAL_PALLET'] != '']
    sem_pallet = aguardando[aguardando['LOCAL_PALLET'] == '']

    col_resumo1, col_resumo2, col_resumo3 = st.columns(3)
    col_resumo1.metric("Pallets Ativos", com_pallet['LOCAL_PALLET'].nunique())
    col_resumo2.metric("Pneus Alocados", len(com_pallet))
    col_resumo3.metric("Pneus Sem Pallet", len(sem_pallet))

    st.markdown("---")

    if com_pallet.empty:
        st.info("Nenhum pallet com pneus alocados no momento.")
        return

    # Filtro por cliente
    clientes_disponiveis = sorted(com_pallet['CLIENTE'].unique().tolist())
    filtro_cliente = st.selectbox(
        "Filtrar por Cliente (opcional):",
        ["Todos"] + clientes_disponiveis,
        key="mapa_cap_cliente",
    )

    if filtro_cliente != "Todos":
        com_pallet = com_pallet[com_pallet['CLIENTE'] == filtro_cliente]

    pallets = sorted(com_pallet['LOCAL_PALLET'].unique().tolist())

    # Renderiza 3 pallets por linha
    cols_por_linha = 3
    for i in range(0, len(pallets), cols_por_linha):
        cols = st.columns(cols_por_linha)
        for j, pallet in enumerate(pallets[i:i + cols_por_linha]):
            pneus_pallet = com_pallet[com_pallet['LOCAL_PALLET'] == pallet]
            qtd = len(pneus_pallet)
            clientes_no_pallet = pneus_pallet['CLIENTE'].unique().tolist()

            # Cor do card baseada na quantidade
            if qtd >= 8:
                cor_borda = "#e74c3c"  # vermelho — cheio
                cor_header = "#c0392b"
                label_status = "🔴 CHEIO"
            elif qtd >= 5:
                cor_borda = "#f39c12"  # laranja — quase cheio
                cor_header = "#d68910"
                label_status = "🟡 ATENÇÃO"
            else:
                cor_borda = "#27ae60"  # verde — disponível
                cor_header = "#1e8449"
                label_status = "🟢 OK"

            # Linhas de pneus no card
            linhas_pneus = ""
            for _, row in pneus_pallet.iterrows():
                nrordem  = row.get('NRORDEM', '')
                cliente  = str(row.get('CLIENTE', '')).split()[0]  # primeira palavra do cliente
                desenho  = row.get('DESENHO', '')
                linhas_pneus += (
                    f"<div style='padding:3px 0;border-bottom:1px solid #ddd;font-size:12px;'>"
                    f"<b>OS {nrordem}</b> &nbsp;·&nbsp; {cliente} &nbsp;·&nbsp; {desenho}"
                    f"</div>"
                )

            clientes_str = "<br>".join(clientes_no_pallet)

            cols[j].markdown(
                f"""
                <div style="border:2px solid {cor_borda};border-radius:10px;
                            margin-bottom:16px;overflow:hidden;">
                  <div style="background:{cor_header};padding:8px 12px;">
                    <span style="color:#fff;font-size:15px;font-weight:bold;">
                      📦 {pallet}
                    </span>
                    <span style="float:right;color:#fff;font-size:12px;">{label_status}</span>
                  </div>
                  <div style="padding:8px 12px;background:#1a1a2e;">
                    <div style="font-size:13px;color:#aaa;margin-bottom:6px;">
                      <b style="color:#fff;">{qtd} pneu(s)</b> &nbsp;|&nbsp; {clientes_str}
                    </div>
                    {linhas_pneus}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Pneus sem pallet ao final
    if not sem_pallet.empty:
        st.markdown("---")
        st.warning(f"⚠️ **{len(sem_pallet)} pneus sem pallet definido:**")
        st.dataframe(
            sem_pallet[['NRORDEM', 'IDPEDIDOPNEU', 'CLIENTE', 'DESENHO']],
            use_container_width=True,
            hide_index=True,
        )


# ── 4. Mapa FIFO (Visualização de Prioridade) ────────────────────────────────
def _aba_mapa_fifo(df: pd.DataFrame):
    st.subheader("Mapa FIFO (First In, First Out)")
    st.info("Puxe para a Produção sempre os pallets do TOPO desta lista (os mais antigos na fábrica).")

    aguardando = df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] != '')].copy()

    if aguardando.empty:
        st.success("O pátio está vazio! Nenhum pneu aguardando.")
        return

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
        pallet      = row['LOCAL_PALLET']
        qtd         = row['Qtd_Pneus']
        data_antiga = row['Data do Pneu + Antigo']
        clientes    = row['Clientes']

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
