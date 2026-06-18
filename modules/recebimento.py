"""
Tela de Recebimento, Alocação de Pallets e Gestão FIFO.
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados

# ── Mapa físico do pátio: Rua (A–H) x Vaga (1–5) ─────────────────────────────
_RUAS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
_VAGAS_POR_RUA = 5
_POSICOES_VALIDAS = {f"{rua}{n}" for rua in _RUAS for n in range(1, _VAGAS_POR_RUA + 1)}

# ── Ruas de pré-produção (pós-limpeza): P1–P8, capacidade 18 pneus cada ──────
_RUAS_PRODUCAO = [f"P{n}" for n in range(1, 9)]
_CAP_RUA_PRODUCAO = 18

_NAV_ABAS = [
    "📦 1. Alocar (Bipe)",
    "🔄 2. Movimentar",
    "🗺️ 3. Capacidade",
    "📋 4. FIFO",
    "🧼 5. Limpeza (Bipe)",
    "🏭 6. Rua Pré-Produção (Bipe)",
]


def tela_recebimento():
    st.title("📥 Recebimento e Gestão de Pátio (FIFO)")

    df = st.session_state.bd_pneus

    if df.empty:
        st.warning("Nenhuma OS cadastrada no sistema. Importe o CSV pelo Painel PPCP.")
        return

    if 'receb_aba_ativa' not in st.session_state:
        st.session_state.receb_aba_ativa = _NAV_ABAS[0]

    # Aplica redirecionamento pendente (ex.: limpeza → rua de pré-produção)
    # ANTES de instanciar o widget — não dá pra mudar a chave de um widget
    # já instanciado na mesma execução.
    if st.session_state.get('receb_redirect'):
        st.session_state.receb_aba_ativa = st.session_state.pop('receb_redirect')

    aba_sel = st.radio(
        "Navegação:",
        _NAV_ABAS,
        horizontal=True,
        key='receb_aba_ativa',
        label_visibility='collapsed',
    )

    # Mensagem de sucesso da etapa anterior (ex.: limpeza redirecionando p/
    # rua de pré-produção) — exibida aqui pra aparecer em qualquer aba.
    if st.session_state.get('msg_limpeza'):
        st.success(st.session_state.msg_limpeza)
        st.session_state.msg_limpeza = None

    st.markdown("---")

    if aba_sel == _NAV_ABAS[0]:
        _aba_alocar_pallet(df)
    elif aba_sel == _NAV_ABAS[1]:
        _aba_movimentar_pallet(df)
    elif aba_sel == _NAV_ABAS[2]:
        _aba_mapa_capacidade(df)
    elif aba_sel == _NAV_ABAS[3]:
        _aba_mapa_fifo(df)
    elif aba_sel == _NAV_ABAS[4]:
        _aba_enviar_limpeza(df)
    elif aba_sel == _NAV_ABAS[5]:
        _aba_alocar_rua_producao(df)


# ── 1. Alocação (Bipe da Posição na Parede + Bipe dos Pneus) ─────────────────
def _aba_alocar_pallet(df: pd.DataFrame):
    st.subheader("Alocação Inicial no Pátio")
    st.info(
        "1️⃣ Bipe o código da posição fixado na parede (Rua A–H, Vaga 1–5). "
        "2️⃣ Bipe os pneus que estão sendo guardados ali."
    )

    sem_pallet = df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] == '')]

    if 'posicao_ativa' not in st.session_state:
        st.session_state.posicao_ativa = ''
    if 'posicao_key' not in st.session_state:
        st.session_state.posicao_key = 0
    if 'recebimento_key' not in st.session_state:
        st.session_state.recebimento_key = 0

    col1, col2 = st.columns([1, 2])

    with col1:
        posicao_bipada = st.text_input(
            "🧱 Bipe a Posição (parede):",
            key=f"bipe_posicao_{st.session_state.posicao_key}",
            placeholder="Ex: A1, C4, H5...",
        ).strip().upper()

        if posicao_bipada:
            if posicao_bipada not in _POSICOES_VALIDAS:
                st.error(
                    f"❌ Posição '{posicao_bipada}' inválida. "
                    f"Use Rua A–H + Vaga 1–{_VAGAS_POR_RUA} (ex: C4)."
                )
            else:
                st.session_state.posicao_ativa = posicao_bipada
                st.session_state.posicao_key += 1
                st.rerun()

        if st.session_state.posicao_ativa:
            pos = st.session_state.posicao_ativa
            rua, vaga = pos[0], pos[1:]
            ocupacao_atual = len(
                df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] == pos)]
            )
            st.success(
                f"📍 Posição ativa: **{pos}** (Rua {rua}, Vaga {vaga}) "
                f"— {ocupacao_atual} pneu(s) já guardado(s) aqui"
            )

            os_bipada = st.text_input(
                "📷 Bipe a OS (NRORDEM):",
                key=f"bipe_receb_{st.session_state.recebimento_key}",
                placeholder="Aguardando leitor...",
            ).strip()

            if os_bipada:
                idx = df.index[df['NRORDEM'] == os_bipada].tolist()
                if idx:
                    i = idx[0]
                    status_atual = str(df.at[i, 'STATUS']).strip()
                    pallet_atual = str(df.at[i, 'LOCAL_PALLET']).strip()

                    if status_atual != 'Aguardando':
                        st.error(f"🛑 A OS {os_bipada} já está **{status_atual}**. Não pode ser recebida.")
                    elif pallet_atual == pos:
                        st.warning(f"⚠️ A OS {os_bipada} já está na posição **{pos}**.")
                    else:
                        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        st.session_state.bd_pneus.at[i, 'LOCAL_PALLET']  = pos
                        # Carimba a data de CHEGADA/recebimento no pátio
                        st.session_state.bd_pneus.at[i, 'DATA_ENTRADA'] = agora
                        salvar_dados(st.session_state.bd_pneus)
                        st.session_state.msg_receb = f"✅ OS {os_bipada} guardada na posição **{pos}**!"
                        st.session_state.recebimento_key += 1
                        st.rerun()
                else:
                    st.error("❌ OS não encontrada no sistema.")

            if st.button("🔄 Trocar de posição"):
                st.session_state.posicao_ativa = ''
                st.rerun()

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
            st.success("🎉 Todos os pneus 'Aguardando' já estão alocados em posições!")


# ── 2. Movimentação (Transferir de uma Posição para outra) ───────────────────
def _aba_movimentar_pallet(df: pd.DataFrame):
    st.subheader("Transferência entre Posições")
    st.write("Mova pneus de uma posição para outra para organizar o espaço (consolidar cargas).")

    pallets_ativos = sorted(
        df[(df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] != '')]['LOCAL_PALLET']
        .unique().tolist()
    )

    if not pallets_ativos:
        st.info("Não há posições com pneus aguardando no momento.")
        return

    c1, c2 = st.columns(2)
    pallet_origem  = c1.selectbox("De qual Posição deseja retirar?", pallets_ativos, key="mov_origem")
    pallet_destino = c2.text_input(
        "🧱 Bipe a Posição de destino (parede):", placeholder="Ex: C4"
    ).strip().upper()

    if pallet_destino and pallet_destino not in _POSICOES_VALIDAS:
        c2.error(f"❌ Posição '{pallet_destino}' inválida. Use Rua A–H + Vaga 1–{_VAGAS_POR_RUA}.")
        pallet_destino = ''

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


# ── 3. Mapa de Capacidade (Grade física: Rua x Vaga) ──────────────────────────
def _aba_mapa_capacidade(df: pd.DataFrame):
    st.subheader("Mapa de Capacidade do Pátio (Rua x Vaga)")

    aguardando = df[df['STATUS'] == 'Aguardando'].copy()
    com_pallet = aguardando[aguardando['LOCAL_PALLET'] != '']
    sem_pallet = aguardando[aguardando['LOCAL_PALLET'] == '']

    # Posições válidas (padrão A1–H5) ocupadas vs. legado (nomes antigos de pallet)
    ocupadas_validas = com_pallet[com_pallet['LOCAL_PALLET'].isin(_POSICOES_VALIDAS)]
    legado = com_pallet[~com_pallet['LOCAL_PALLET'].isin(_POSICOES_VALIDAS)]

    col_resumo1, col_resumo2, col_resumo3, col_resumo4 = st.columns(4)
    col_resumo1.metric("Posições Ocupadas", f"{ocupadas_validas['LOCAL_PALLET'].nunique()}/{len(_POSICOES_VALIDAS)}")
    col_resumo2.metric("Posições Livres", len(_POSICOES_VALIDAS) - ocupadas_validas['LOCAL_PALLET'].nunique())
    col_resumo3.metric("Pneus Alocados", len(com_pallet))
    col_resumo4.metric("Pneus Sem Posição", len(sem_pallet))

    st.markdown("---")

    # Filtro por cliente
    clientes_disponiveis = sorted(com_pallet['CLIENTE'].unique().tolist()) if not com_pallet.empty else []
    filtro_cliente = st.selectbox(
        "Filtrar por Cliente (opcional):",
        ["Todos"] + clientes_disponiveis,
        key="mapa_cap_cliente",
    )
    com_pallet_filtrado = com_pallet if filtro_cliente == "Todos" else com_pallet[com_pallet['CLIENTE'] == filtro_cliente]

    for rua in _RUAS:
        st.markdown(f"#### Rua {rua}")
        cols = st.columns(_VAGAS_POR_RUA)
        for n in range(1, _VAGAS_POR_RUA + 1):
            codigo = f"{rua}{n}"
            pneus_pos = com_pallet_filtrado[com_pallet_filtrado['LOCAL_PALLET'] == codigo]
            qtd = len(pneus_pos)

            if qtd == 0:
                cor_borda, cor_header, label_status = "#444", "#2c2c2c", "VAZIA"
            elif qtd >= 8:
                cor_borda, cor_header, label_status = "#e74c3c", "#c0392b", "🔴 CHEIA"
            elif qtd >= 5:
                cor_borda, cor_header, label_status = "#f39c12", "#d68910", "🟡 ATENÇÃO"
            else:
                cor_borda, cor_header, label_status = "#27ae60", "#1e8449", "🟢 OK"

            linhas_pneus = ""
            for _, row in pneus_pos.iterrows():
                nrordem = row.get('NRORDEM', '')
                cliente = str(row.get('CLIENTE', '')).split()[0]
                linhas_pneus += (
                    f"<div style='padding:2px 0;font-size:11px;'>"
                    f"OS {nrordem} · {cliente}</div>"
                )

            cols[n - 1].markdown(
                f"""
                <div style="border:2px solid {cor_borda};border-radius:8px;
                            margin-bottom:12px;overflow:hidden;">
                  <div style="background:{cor_header};padding:6px 8px;">
                    <span style="color:#fff;font-size:13px;font-weight:bold;">📍 {codigo}</span>
                    <div style="color:#fff;font-size:10px;">{label_status}</div>
                  </div>
                  <div style="padding:6px 8px;background:#1a1a2e;min-height:30px;">
                    <div style="font-size:11px;color:#aaa;">{qtd} pneu(s)</div>
                    {linhas_pneus}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Posições legadas (nomes que não seguem o padrão A1–H5)
    if not legado.empty:
        st.markdown("---")
        st.warning(f"⚠️ **{legado['LOCAL_PALLET'].nunique()} posição(ões) com nome antigo (fora do padrão Rua/Vaga):**")
        st.dataframe(
            legado[['LOCAL_PALLET', 'NRORDEM', 'CLIENTE', 'DESENHO']],
            use_container_width=True,
            hide_index=True,
        )

    # Pneus sem posição ao final
    if not sem_pallet.empty:
        st.markdown("---")
        st.warning(f"⚠️ **{len(sem_pallet)} pneus sem posição definida:**")
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
              <h4 style="margin:0 0 5px 0;">{icone} — Posição: <b>{pallet}</b></h4>
              <p style="margin:0;font-size:14px;">
                <b>Qtd:</b> {qtd} pneus &nbsp;&nbsp;|&nbsp;&nbsp;
                <b>Pneu mais antigo:</b> {data_antiga} &nbsp;&nbsp;|&nbsp;&nbsp;
                <b>Clientes:</b> {clientes}
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── 5. Enviar para Limpeza (Bipe da posição → libera a vaga) ─────────────────
def _aba_enviar_limpeza(df: pd.DataFrame):
    st.subheader("Enviar Pallet para Máquina de Limpeza")
    st.info(
        "Bipe o código da posição (Rua + Vaga) do pallet que está saindo para a "
        "limpeza. Todos os pneus daquela posição avançam para **'Em Limpeza'** "
        "e a vaga fica disponível imediatamente para um novo pallet."
    )

    if 'limpeza_key' not in st.session_state:
        st.session_state.limpeza_key = 0

    posicao_bipada = st.text_input(
        "🧼 Bipe a Posição (parede):",
        key=f"bipe_limpeza_{st.session_state.limpeza_key}",
        placeholder="Ex: A1, C4, H5...",
    ).strip().upper()

    if posicao_bipada:
        if posicao_bipada not in _POSICOES_VALIDAS:
            st.error(
                f"❌ Posição '{posicao_bipada}' inválida. "
                f"Use Rua A–H + Vaga 1–{_VAGAS_POR_RUA} (ex: C4)."
            )
        else:
            pneus_pos = df[
                (df['STATUS'] == 'Aguardando') & (df['LOCAL_PALLET'] == posicao_bipada)
            ]
            if pneus_pos.empty:
                st.warning(f"⚠️ A posição **{posicao_bipada}** está vazia. Nada para enviar.")
            else:
                qtd = len(pneus_pos)
                clientes = ', '.join(pneus_pos['CLIENTE'].unique().tolist())
                st.session_state.bd_pneus.loc[pneus_pos.index, 'STATUS'] = 'Em Limpeza'
                salvar_dados(st.session_state.bd_pneus)
                st.session_state.msg_limpeza = (
                    f"🧼 **{qtd} pneu(s)** da posição **{posicao_bipada}** "
                    f"({clientes}) enviados para a limpeza. "
                    f"Posição **{posicao_bipada}** liberada!"
                )
                # Redireciona automaticamente para a alocação na rua de
                # pré-produção — o operador está no mesmo local físico
                # (máquina de limpeza) cuidando do que já saiu lavado.
                st.session_state.receb_redirect = _NAV_ABAS[5]
            st.session_state.limpeza_key += 1
            st.rerun()

    st.markdown("---")

    em_limpeza = df[df['STATUS'] == 'Em Limpeza']
    st.markdown(f"**Pneus atualmente em limpeza: {len(em_limpeza)}**")
    if not em_limpeza.empty:
        st.dataframe(
            em_limpeza[['NRORDEM', 'CLIENTE', 'DESENHO', 'LOCAL_PALLET']]
            .rename(columns={'LOCAL_PALLET': 'Posição de Origem'}),
            use_container_width=True,
            hide_index=True,
        )


# ── 6. Alocar em Rua de Pré-Produção (Bipe rua + Bipe OS, capacidade 18) ─────
def _aba_alocar_rua_producao(df: pd.DataFrame):
    st.subheader("Alocar em Rua de Pré-Produção (Pós-Limpeza)")
    st.info(
        "1️⃣ Bipe o código da rua (P1–P8) onde os pneus já limpos estão sendo "
        f"colocados. 2️⃣ Bipe os pneus. Capacidade máxima: {_CAP_RUA_PRODUCAO} "
        "pneus por rua."
    )

    if 'rua_prod_ativa' not in st.session_state:
        st.session_state.rua_prod_ativa = ''
    if 'rua_prod_key' not in st.session_state:
        st.session_state.rua_prod_key = 0
    if 'rua_os_key' not in st.session_state:
        st.session_state.rua_os_key = 0

    rua_bipada = st.text_input(
        "🏭 Bipe a Rua (P1–P8):",
        key=f"bipe_rua_{st.session_state.rua_prod_key}",
        placeholder="Ex: P1, P5, P8...",
    ).strip().upper()

    if rua_bipada:
        if rua_bipada not in _RUAS_PRODUCAO:
            st.error(f"❌ Rua '{rua_bipada}' inválida. Use P1 a P8.")
        else:
            st.session_state.rua_prod_ativa = rua_bipada
        st.session_state.rua_prod_key += 1
        st.rerun()

    if st.session_state.rua_prod_ativa:
        rua = st.session_state.rua_prod_ativa
        ocupacao = len(
            df[(df['STATUS'] == 'Aguardando Produção') & (df['RUA_PRODUCAO'] == rua)]
        )
        cheia = ocupacao >= _CAP_RUA_PRODUCAO

        if cheia:
            st.error(f"🔴 Rua **{rua}** CHEIA — {ocupacao}/{_CAP_RUA_PRODUCAO} pneus. Escolha outra rua.")
        else:
            st.success(f"📍 Rua ativa: **{rua}** — {ocupacao}/{_CAP_RUA_PRODUCAO} pneus")

            os_bipada = st.text_input(
                "📷 Bipe a OS (NRORDEM):",
                key=f"bipe_rua_os_{st.session_state.rua_os_key}",
                placeholder="Aguardando leitor...",
            ).strip()

            if os_bipada:
                idx = df.index[df['NRORDEM'] == os_bipada].tolist()
                if not idx:
                    st.error("❌ OS não encontrada no sistema.")
                else:
                    i = idx[0]
                    status_atual = str(df.at[i, 'STATUS']).strip()
                    if status_atual != 'Em Limpeza':
                        st.error(
                            f"🛑 A OS {os_bipada} está como **{status_atual}**, não "
                            f"**'Em Limpeza'**. Só pneus que saíram da limpeza entram na rua."
                        )
                    elif ocupacao >= _CAP_RUA_PRODUCAO:
                        st.error(f"🔴 Rua **{rua}** ficou cheia. Escolha outra rua.")
                    else:
                        st.session_state.bd_pneus.at[i, 'STATUS']       = 'Aguardando Produção'
                        st.session_state.bd_pneus.at[i, 'RUA_PRODUCAO'] = rua
                        salvar_dados(st.session_state.bd_pneus)
                        st.session_state.msg_rua_prod = (
                            f"✅ OS {os_bipada} alocada na rua **{rua}** "
                            f"({ocupacao + 1}/{_CAP_RUA_PRODUCAO})."
                        )
                        st.session_state.rua_os_key += 1
                        st.rerun()

            if st.button("🔄 Trocar de rua"):
                st.session_state.rua_prod_ativa = ''
                st.rerun()

    if st.session_state.get('msg_rua_prod'):
        st.success(st.session_state.msg_rua_prod)
        st.session_state.msg_rua_prod = None

    st.markdown("---")
    st.markdown("**Ocupação das Ruas de Pré-Produção**")

    cols = st.columns(4)
    for n, rua in enumerate(_RUAS_PRODUCAO):
        ocupacao_rua = len(
            df[(df['STATUS'] == 'Aguardando Produção') & (df['RUA_PRODUCAO'] == rua)]
        )
        if ocupacao_rua >= _CAP_RUA_PRODUCAO:
            cor_borda, cor_header, label = "#e74c3c", "#c0392b", "🔴 CHEIA"
        elif ocupacao_rua >= _CAP_RUA_PRODUCAO * 0.7:
            cor_borda, cor_header, label = "#f39c12", "#d68910", "🟡 ATENÇÃO"
        else:
            cor_borda, cor_header, label = "#27ae60", "#1e8449", "🟢 OK"

        cols[n % 4].markdown(
            f"""
            <div style="border:2px solid {cor_borda};border-radius:8px;
                        margin-bottom:12px;overflow:hidden;">
              <div style="background:{cor_header};padding:6px 8px;">
                <span style="color:#fff;font-size:13px;font-weight:bold;">🏭 {rua}</span>
                <div style="color:#fff;font-size:10px;">{label}</div>
              </div>
              <div style="padding:6px 8px;background:#1a1a2e;">
                <div style="font-size:13px;color:#fff;">{ocupacao_rua}/{_CAP_RUA_PRODUCAO} pneus</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
