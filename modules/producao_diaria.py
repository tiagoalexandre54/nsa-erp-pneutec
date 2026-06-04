"""
Tela — Pneus a Produzir.

Lê a planilha PLANEJAMENTO_DIARIO_PCP.xlsx, extrai os IDPEDIDO
de cada linha de produção (A, B, C) e exibe as OS correspondentes
do banco de dados, prontas para entrar em produção.
"""
import streamlit as st
import pandas as pd
import datetime
from io import BytesIO


# Mapeamento das colunas de IDPEDIDO na planilha
# Linha A → col F (5), Linha B → col K (10), Linha C → col Q (16)
_LINHAS = {
    'A': {'col_id': 5,  'col_cliente': 2, 'col_qtd': 3, 'cor': '#1a5276', 'emoji': '🔵'},
    'B': {'col_id': 10, 'col_cliente': 7, 'col_qtd': 8, 'cor': '#1e8449', 'emoji': '🟢'},
    'C': {'col_id': 16, 'col_cliente': 12,'col_qtd': 13, 'cor': '#784212', 'emoji': '🟠'},
}

# Linha de início dos dados (0-based index no dataframe)
_LINHA_DADOS_INI = 7   # linha 8 no Excel (cabeçalho em 7)
_LINHA_DADOS_FIM = 24  # até linha 25 no Excel


def _ler_planilha(arquivo) -> dict:
    """
    Lê a planilha de planejamento e retorna dict com:
    {
      'data':   '14/03/2026',
      'linhas': {
        'A': [{'idpedido': '356774', 'cliente': 'ETC', 'qtd': '4'}, ...],
        'B': [...],
        'C': [...],
      }
    }
    """
    df = pd.read_excel(arquivo, sheet_name=0, header=None, dtype=str)
    df = df.fillna('')

    # Extrai data do banner (linha 1, coluna 1)
    data_str = ''
    try:
        banner = str(df.iloc[1, 1])
        import re
        m = re.search(r'(\d{2}/\d{2}/\d{4})', banner)
        if m:
            data_str = m.group(1)
    except Exception:
        pass

    resultado = {'data': data_str, 'linhas': {}}

    for linha_id, cfg in _LINHAS.items():
        itens = []
        for row_idx in range(_LINHA_DADOS_INI, min(_LINHA_DADOS_FIM, len(df))):
            try:
                idpedido = str(df.iloc[row_idx, cfg['col_id']]).strip()
                cliente  = str(df.iloc[row_idx, cfg['col_cliente']]).strip()
                qtd      = str(df.iloc[row_idx, cfg['col_qtd']]).strip()

                # Ignora linhas sem IDPEDIDO e linhas de TOTAL
                if not idpedido or idpedido in ('', 'nan', '0'):
                    continue
                if 'TOTAL' in cliente.upper() or 'TOTAL' in idpedido.upper():
                    continue
                # Ignora se não for numérico
                if not idpedido.strip().isdigit():
                    continue

                itens.append({
                    'idpedido': idpedido,
                    'cliente':  cliente if cliente not in ('', 'nan') else '—',
                    'qtd':      qtd if qtd not in ('', 'nan') else '—',
                })
            except Exception:
                continue
        resultado['linhas'][linha_id] = itens

    return resultado


def tela_producao_diaria():
    st.title("🏗️ Pneus a Produzir")
    st.write("Carregue a planilha de programação diária para visualizar as OS de cada linha de produção.")

    df_banco = st.session_state.bd_pneus

    # ── Upload da planilha ────────────────────────────────────────────────────
    arquivo = st.file_uploader(
        "📂 Selecione a planilha PLANEJAMENTO_DIARIO_PCP.xlsx:",
        type=["xlsx", "xls"],
        key="uploader_planejamento"
    )

    if not arquivo:
        # Dica visual
        st.info(
            "👆 Carregue a planilha de programação diária com os **IDPEDIDO** "
            "preenchidos nas colunas **F** (Linha A), **K** (Linha B) e **Q** (Linha C)."
        )
        _exibir_instrucoes()
        return

    # ── Lê a planilha ────────────────────────────────────────────────────────
    try:
        plano = _ler_planilha(arquivo)
    except Exception as e:
        st.error(f"❌ Erro ao ler a planilha: {e}")
        return

    data_plano = plano['data'] or datetime.date.today().strftime('%d/%m/%Y')

    st.markdown(
        f"""
        <div style="background:#003366;border-radius:8px;padding:12px 20px;margin-bottom:16px;">
          <h3 style="color:#fff;margin:0;">📋 Programação de Produção — {data_plano}</h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── Resumo geral ──────────────────────────────────────────────────────────
    total_pedidos = sum(len(v) for v in plano['linhas'].values())
    total_os = 0

    # ── Processa cada linha ───────────────────────────────────────────────────
    for linha_id, cfg in _LINHAS.items():
        itens = plano['linhas'].get(linha_id, [])
        if not itens:
            continue

        cor  = cfg['cor']
        emoji = cfg['emoji']

        # Para cada IDPEDIDO, busca OS no banco
        todos_ids = [item['idpedido'] for item in itens]
        os_da_linha = df_banco[df_banco['IDPEDIDOPNEU'].isin(todos_ids)].copy()
        total_os += len(os_da_linha)

        st.markdown(
            f"""
            <div style="background:{cor};border-radius:6px;padding:10px 16px;margin:12px 0 4px 0;">
              <h4 style="color:#fff;margin:0;">
                {emoji} LINHA {linha_id} — {len(itens)} pedido(s) planejado(s) |
                {len(os_da_linha)} OS no sistema
              </h4>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Tabela de OS agrupadas por IDPEDIDO
        for item in itens:
            idp = item['idpedido']
            os_pedido = os_da_linha[os_da_linha['IDPEDIDOPNEU'] == idp].copy()

            aguard = len(os_pedido[os_pedido['STATUS'] == 'Aguardando'])
            prod   = len(os_pedido[os_pedido['STATUS'] == 'Em Produção'])
            exped  = len(os_pedido[os_pedido['STATUS'] == 'Expedido'])

            label = (
                f"IDPEDIDO **{idp}** — {item['cliente']} "
                f"| Planejado: {item['qtd']} pneus "
                f"| 🟡 {aguard} Aguard. 🔵 {prod} Prod. 🟢 {exped} Exped."
            )

            if os_pedido.empty:
                with st.expander(f"⚠️ IDPEDIDO {idp} — {item['cliente']} | Não encontrado no banco"):
                    st.warning(
                        f"IDPEDIDO **{idp}** não encontrado. "
                        f"Importe o CSV correspondente no Painel PPCP."
                    )
            else:
                with st.expander(label, expanded=(aguard > 0)):
                    exibir = os_pedido[[
                        'NRORDEM', 'NRSERIE', 'DESENHO', 'STATUS',
                        'LOCAL_PALLET', 'DATA_ENTRADA', 'DATA_SAIDA'
                    ]].copy()
                    exibir = exibir.rename(columns={
                        'LOCAL_PALLET': 'Pallet',
                        'DATA_ENTRADA': 'Data Coleta',
                        'DATA_SAIDA':   'Entrega Prev.',
                    })
                    st.dataframe(
                        exibir.style.apply(_colorir, axis=1),
                        use_container_width=True,
                        hide_index=True
                    )

                    # Botão de entrada em produção para os aguardando
                    if aguard > 0:
                        if st.button(
                            f"▶️ Enviar {aguard} pneu(s) para Produção",
                            key=f"btn_prod_{linha_id}_{idp}",
                            type="primary"
                        ):
                            mask = (
                                (df_banco['IDPEDIDOPNEU'] == idp) &
                                (df_banco['STATUS'] == 'Aguardando')
                            )
                            from modules.database import salvar_dados
                            st.session_state.bd_pneus.loc[mask, 'STATUS'] = 'Em Produção'
                            st.session_state.bd_pneus.loc[mask, 'DATA_ENTRADA'] = \
                                datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            salvar_dados(st.session_state.bd_pneus)
                            st.success(f"✅ {aguard} pneu(s) do pedido {idp} enviados para produção!")
                            st.rerun()

    # ── Resumo final ──────────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Pedidos no plano", total_pedidos)
    c2.metric("OS encontradas", total_os)
    c3.metric("Data do plano", data_plano)


def _colorir(row: pd.Series):
    cores = {
        'Aguardando':  'background-color:#fff3cd;color:#856404',
        'Em Produção': 'background-color:#cce5ff;color:#004085',
        'Expedido':    'background-color:#d4edda;color:#155724',
    }
    return [cores.get(str(row.get('STATUS', '')).strip(), '')] * len(row)


def _exibir_instrucoes():
    with st.expander("📖 Como usar", expanded=True):
        st.markdown("""
        **Passo a passo:**

        1. Abra a planilha `PLANEJAMENTO_DIARIO_PCP.xlsx`
        2. Preencha a coluna **F** com os IDPEDIDO da **Linha A**
        3. Preencha a coluna **K** com os IDPEDIDO da **Linha B**
        4. Preencha a coluna **Q** com os IDPEDIDO da **Linha C**
        5. Salve e carregue aqui com o botão acima

        **O sistema irá:**
        - Buscar as OS de cada IDPEDIDO no banco de dados
        - Mostrar status de cada pneu (Aguardando / Em Produção / Expedido)
        - Indicar qual pallet cada pneu está alocado
        - Permitir enviar lotes inteiros para produção com 1 clique
        """)
