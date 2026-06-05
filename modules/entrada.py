"""
Tela 2 — Apontamento de Entrada (Chão de Fábrica) — DO DIA.
Mostra apenas os pneus da programação do dia (coletas A/B/C importadas).
"""
import streamlit as st
import pandas as pd
import datetime
from modules.database import salvar_dados


def tela_entrada():
    st.title("🏭 Apontamento de Entrada — Chão de Fábrica do Dia")

    from modules.producao_diaria import _carregar_plano, _buscar_os, _CFG_LINHAS

    plano = _carregar_plano()

    st.info("Bipe a OS (NRORDEM) para registrar a entrada na linha. A lista abaixo é a **programação do dia**.")

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

    # ── Lista da PROGRAMAÇÃO DO DIA ──────────────────────────────────────────
    if not plano:
        st.warning(
            "Nenhuma programação carregada. Importe a planilha na aba "
            "**🏗️ Pneus a Produzir → 📂 Importar**. Exibindo todos os pneus "
            "aguardando como alternativa:"
        )
        _lista_todos_aguardando()
        return

    st.subheader(f"📋 Programação do dia — {plano.get('data', '—')}")
    _alerta_do_dia(plano, _buscar_os, _CFG_LINHAS)


# ── Processa o bipe (Aguardando → Em Produção) ───────────────────────────────
def _processar_bipe(os_bipada: str):
    df  = st.session_state.bd_pneus
    idx = df.index[df['NRORDEM'] == os_bipada].tolist()

    if not idx:
        st.error("❌ OS não encontrada no sistema. Verifique a importação do PPCP.")
        return

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


# ── Lista guiada pela programação do dia, por linha A/B/C ─────────────────────
def _alerta_do_dia(plano: dict, _buscar_os, _CFG_LINHAS):
    df = st.session_state.bd_pneus

    total_aguard = 0
    blocos = []  # (linha_id, cfg, [(item, df_aguard)])

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = plano['linhas'].get(linha_id, [])
        linha_aguard = []
        for item in itens:
            os_cli = _buscar_os(item.get('idpedido', ''), item['cliente'], df)
            if os_cli.empty or 'STATUS' not in os_cli.columns:
                continue
            aguard = os_cli[os_cli['STATUS'] == 'Aguardando']
            if not aguard.empty:
                linha_aguard.append((item, aguard))
                total_aguard += len(aguard)
        if linha_aguard:
            blocos.append((linha_id, cfg, linha_aguard))

    if total_aguard == 0:
        st.success("🎉 **Toda a programação do dia já entrou na produção!** Nada aguardando.")
        return

    st.markdown(
        f"""
        <div style="background:#fff3cd;border:2px solid #ffc107;border-radius:8px;
                    padding:16px;margin-bottom:16px;">
          <h4 style="color:#856404;margin:0 0 8px 0;">
            🚨 ATENÇÃO — {total_aguard} PNEU(S) DA PROGRAMAÇÃO AGUARDANDO ENTRADA
          </h4>
          <p style="color:#856404;margin:0;">
            Bipe os NRORDEMs abaixo no campo de leitura para registrar a entrada na linha de produção.
          </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    for linha_id, cfg, linha_aguard in blocos:
        n_linha = sum(len(a) for _, a in linha_aguard)
        st.markdown(
            f"<div style='background:{cfg['cor']};border-radius:6px;"
            f"padding:8px 16px;margin:12px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>"
            f"{cfg['emoji']} LINHA {linha_id} — {n_linha} pneu(s) aguardando"
            f"</h4></div>",
            unsafe_allow_html=True,
        )
        for item, aguard in linha_aguard:
            id_txt = item.get('idpedido') or '(sem ID)'
            with st.expander(
                f"📦 {item['cliente']} (ID {id_txt}) — {len(aguard)} pneu(s)",
                expanded=True,
            ):
                st.dataframe(
                    aguard[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET']]
                    .reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                )


# ── Fallback: todos os aguardando (quando não há programação carregada) ──────
def _lista_todos_aguardando():
    df = st.session_state.bd_pneus
    pendentes = df[df['STATUS'] == 'Aguardando'].copy()

    if pendentes.empty:
        st.info("Nenhuma OS aguardando entrada no momento.")
        return

    st.markdown(f"**{len(pendentes)} pneu(s) aguardando (todos os clientes):**")
    for cliente, grupo in pendentes.groupby('CLIENTE'):
        with st.expander(f"📦 {cliente} — {len(grupo)} pneu(s)", expanded=False):
            st.dataframe(
                grupo[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET']]
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
