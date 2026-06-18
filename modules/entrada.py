"""
Tela 2 — Apontamento de Entrada (Chão de Fábrica).
Mostra os pneus RECEBIDOS no pátio (alocados em pallet no Recebimento)
numa data específica, que ainda aguardam entrada na linha de produção.
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados


def _parse_data(serie: pd.Series) -> pd.Series:
    """Converte DATA_ENTRADA para datetime tentando formatos explícitos."""
    dt = pd.to_datetime(serie, format="%d/%m/%Y %H:%M:%S", errors='coerce')
    for fmt in ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        falta = dt.isna()
        if not falta.any():
            break
        dt.loc[falta] = pd.to_datetime(serie[falta], format=fmt, errors='coerce')
    return dt


def tela_entrada():
    st.title("🏭 Apontamento de Entrada — Recebidos do Dia")

    st.info(
        "Bipe a OS (NRORDEM) para registrar a entrada na linha. A lista mostra os "
        "pneus que já passaram pela **limpeza** (ou foram recebidos no pátio) na "
        "data escolhida e ainda **aguardam** entrada na produção."
    )

    # ── Campo de bipe ────────────────────────────────────────────────────────
    if 'entrada_key' not in st.session_state:
        st.session_state.entrada_key = 0

    os_bipada = st.text_input(
        "📷 Bipe a OS (NRORDEM):",
        key=f"bipe_entrada_{st.session_state.entrada_key}",
        placeholder="Aguardando leitura do código de barras..."
    )

    if os_bipada:
        _processar_bipe(os_bipada.strip())

    # ── Feedback do último bipe ──────────────────────────────────────────────
    if st.session_state.get('msg_entrada'):
        msg = st.session_state.msg_entrada
        if msg['tipo'] == 'sucesso':
            st.success(msg['texto'])
        st.session_state.msg_entrada = None

    st.markdown("---")

    # ── Filtro por data de recebimento ───────────────────────────────────────
    col_d, _ = st.columns([1, 2])
    data_sel = col_d.date_input(
        "📅 Data de recebimento:",
        value=datetime.date.today(),
        format="DD/MM/YYYY",
    )

    _lista_recebidos_do_dia(data_sel)


# ── Processa o bipe (Aguardando → Em Produção) ───────────────────────────────
def _processar_bipe(os_bipada: str):
    df  = st.session_state.bd_pneus
    idx = df.index[df['NRORDEM'] == os_bipada].tolist()

    if not idx:
        st.error("❌ OS não encontrada no sistema. Verifique a importação do PPCP.")
        return

    i = idx[0]
    status_atual = str(df.at[i, 'STATUS']).strip()

    if status_atual in ('Aguardando', 'Em Limpeza', 'Aguardando Produção'):
        df.at[i, 'STATUS']       = 'Em Produção'
        df.at[i, 'DATA_ENTRADA'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        salvar_dados(df)
        st.session_state.msg_entrada = {
            'tipo': 'sucesso',
            'texto': (
                f"✅ **SUCESSO!** OS **{os_bipada}** — "
                f"**{df.at[i, 'CLIENTE']}** | "
                f"**{df.at[i, 'DESENHO']}** entrou na linha de produção!"
            )
        }
        st.session_state.entrada_key += 1
        st.rerun()

    elif status_atual == 'Em Produção':
        st.warning(
            f"⚠️ A OS **{os_bipada}** já está **Em Produção** "
            f"desde {df.at[i, 'DATA_ENTRADA'] or '(data não registrada)'}."
        )
        _exibir_ficha(df, i)

    elif status_atual == 'Expedido':
        st.error(
            f"🛑 A OS **{os_bipada}** já foi **Expedida** "
            f"em {df.at[i, 'DATA_SAIDA'] or '(data não registrada)'}."
        )
    else:
        st.warning(f"⚠️ Status desconhecido: **'{status_atual}'**.")


# ── Lista dos recebidos na data, aguardando, agrupados por pallet ────────────
def _lista_recebidos_do_dia(data_sel: datetime.date):
    df = st.session_state.bd_pneus

    # Pneus alocados no pátio (têm pallet) que já saíram da limpeza (ou ainda
    # estão Aguardando, para quem pula a etapa de limpeza) e aguardam entrada
    base = df[
        (df['STATUS'].isin(['Aguardando', 'Em Limpeza', 'Aguardando Produção'])) &
        (df['LOCAL_PALLET'].astype(str).str.strip() != '')
    ].copy()

    if base.empty:
        st.info("Nenhum pneu alocado no pátio aguardando entrada. Aloque no **Recebimento**.")
        return

    base['_data'] = _parse_data(base['DATA_ENTRADA']).dt.date
    do_dia = base[base['_data'] == data_sel]

    data_txt = data_sel.strftime('%d/%m/%Y')

    if do_dia.empty:
        st.info(f"Nenhum pneu recebido em **{data_txt}** aguardando entrada na produção.")
        return

    st.markdown(
        f"""
        <div style="background:#fff3cd;border:2px solid #ffc107;border-radius:8px;
                    padding:16px;margin-bottom:16px;">
          <h4 style="color:#856404;margin:0 0 8px 0;">
            🚨 {len(do_dia)} PNEU(S) RECEBIDO(S) EM {data_txt} AGUARDANDO ENTRADA
          </h4>
          <p style="color:#856404;margin:0;">
            Bipe os NRORDEMs abaixo no campo de leitura para registrar a entrada na linha.
          </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Mostra a rua de pré-produção (pós-limpeza) quando já alocado lá;
    # senão a posição original do pátio.
    do_dia['_local_atual'] = do_dia['RUA_PRODUCAO'].where(
        do_dia['RUA_PRODUCAO'].astype(str).str.strip() != '', do_dia['LOCAL_PALLET']
    )

    for pallet, grupo in do_dia.groupby('_local_atual'):
        with st.expander(f"📦 Posição {pallet} — {len(grupo)} pneu(s)", expanded=True):
            st.dataframe(
                grupo[['NRORDEM', 'CLIENTE', 'DESENHO', 'NRSERIE', 'IDPEDIDOPNEU']]
                .rename(columns={'IDPEDIDOPNEU': 'IDPEDIDO'})
                .reset_index(drop=True),
                use_container_width=True,
                hide_index=True
            )


def _exibir_ficha(df: pd.DataFrame, i: int):
    with st.expander("📄 Ver detalhes da OS"):
        col1, col2 = st.columns(2)
        col1.write(f"**Cliente:** {df.at[i, 'CLIENTE']}")
        col1.write(f"**Desenho:** {df.at[i, 'DESENHO']}")
        col2.write(f"**Nº Série:** {df.at[i, 'NRSERIE']}")
        col2.write(f"**Entrada:** {df.at[i, 'DATA_ENTRADA'] or '—'}")
