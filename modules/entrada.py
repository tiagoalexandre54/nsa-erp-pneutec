"""
Tela 2 — Apontamento de Entrada (Chão de Fábrica).
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados


def tela_entrada():
    st.title("🏭 Apontamento de Entrada")

    # ── ALERTA: pneus aguardando entrada vindos de PDF ───────────────────────
    _alerta_coletas_pendentes()

    st.info("Utilize o leitor de código de barras para bipar a Ficha de Produção.")

    # ── Campo de bipe ────────────────────────────────────────────────────────
    if 'entrada_key' not in st.session_state:
        st.session_state.entrada_key = 0

    os_bipada = st.text_input(
        "Bipe a OS (NRORDEM):",
        key=f"bipe_entrada_{st.session_state.entrada_key}",
        placeholder="Aguardando leitura do código de barras..."
    )

    if os_bipada:
        os_bipada = os_bipada.strip()
        df = st.session_state.bd_pneus
        idx = df.index[df['NRORDEM'] == os_bipada].tolist()

        if idx:
            i = idx[0]
            status_atual = str(df.at[i, 'STATUS']).strip()

            if status_atual == 'Aguardando':
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
        else:
            st.error("❌ OS não encontrada no sistema. Verifique a importação do PPCP.")

    # ── Feedback do último bipe ──────────────────────────────────────────────
    if st.session_state.get('msg_entrada'):
        msg = st.session_state.msg_entrada
        if msg['tipo'] == 'sucesso':
            st.success(msg['texto'])
        st.session_state.msg_entrada = None

    st.markdown("---")

    # ── Tabela de OS em produção ─────────────────────────────────────────────
    st.subheader("Últimas entradas registradas")
    df = st.session_state.bd_pneus
    em_producao = df[df['STATUS'] == 'Em Produção'].copy()

    em_producao_sorted = em_producao.sort_values(
        'DATA_ENTRADA', ascending=False, na_position='last',
        key=lambda col: col.fillna('')
    )

    if em_producao_sorted.empty:
        st.info("Nenhuma OS em produção no momento.")
    else:
        st.dataframe(
            em_producao_sorted[['NRORDEM', 'CLIENTE', 'DESENHO', 'NRSERIE', 'DATA_ENTRADA']],
            use_container_width=True
        )


def _alerta_coletas_pendentes():
    """
    Exibe painel de alerta com TODOS os pneus em 'Aguardando',
    agrupados por cliente. Some quando todos forem bipados.
    """
    df = st.session_state.bd_pneus
    pendentes = df[df['STATUS'] == 'Aguardando'].copy()

    if pendentes.empty:
        return

    total = len(pendentes)
    por_cliente = pendentes.groupby('CLIENTE')

    st.markdown(
        f"""
        <div style="background:#fff3cd;border:2px solid #ffc107;border-radius:8px;
                    padding:16px;margin-bottom:16px;">
          <h4 style="color:#856404;margin:0 0 8px 0;">
            🚨 ATENÇÃO — {total} PNEU(S) AGUARDANDO ENTRADA NA PRODUÇÃO
          </h4>
          <p style="color:#856404;margin:0;">
            Bipe os NROROEMs abaixo no campo de leitura para registrar a entrada na linha de produção.
          </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    for cliente, grupo in por_cliente:
        entrega = grupo['DATA_SAIDA'].iloc[0].strip()
        label = f"📦 {cliente} — {len(grupo)} pneu(s)"
        if entrega:
            label += f"  |  Entrega prevista: {entrega}"

        with st.expander(label, expanded=True):
            st.dataframe(
                grupo[['NRORDEM', 'NRSERIE', 'DESENHO', 'DATA_ENTRADA', 'DATA_SAIDA']]
                .rename(columns={
                    'DATA_ENTRADA': 'Data Coleta',
                    'DATA_SAIDA':   'Entrega Prevista'
                })
                .reset_index(drop=True),
                use_container_width=True,
                hide_index=True
            )

    st.markdown("---")


def _exibir_ficha(df: pd.DataFrame, i: int):
    with st.expander("📄 Ver detalhes da OS"):
        col1, col2 = st.columns(2)
        col1.write(f"**Cliente:** {df.at[i, 'CLIENTE']}")
        col1.write(f"**Desenho:** {df.at[i, 'DESENHO']}")
        col2.write(f"**Nº Série:** {df.at[i, 'NRSERIE']}")
        col2.write(f"**Entrada:** {df.at[i, 'DATA_ENTRADA'] or '—'}")
