"""
Tela — Pneus a Produzir.

Lê a planilha PLANEJAMENTO_DIARIO_PCP.xlsx e vincula cada cliente
com as OS do banco. Salva o plano diário para consulta posterior.

Cruzamento:
 - Se IDPEDIDO preenchido (cols F/K/Q) → busca por IDPEDIDOPNEU
 - Se não preenchido → busca por nome do CLIENTE (match parcial)
"""
import streamlit as st
import pandas as pd
import datetime
import json
from pathlib import Path

_BASE_DIR   = Path(__file__).resolve().parent.parent
_PLANO_JSON = _BASE_DIR / "data" / "plano_diario.json"

# Configuração base das linhas de produção
# col_id: detectado automaticamente pela busca do header "IDPEDIDO"
# Fallback: F(5), K(10), Q(16) — posições padrão adicionadas na planilha
_CFG_LINHAS = {
    'A': {'col_id': 5,  'col_cliente': 2,  'col_qtd': 3,  'col_status': 4,  'cor': '#1a5276', 'emoji': '🔵'},
    'B': {'col_id': 10, 'col_cliente': 7,  'col_qtd': 8,  'col_status': 9,  'cor': '#1e8449', 'emoji': '🟢'},
    'C': {'col_id': 16, 'col_cliente': 12, 'col_qtd': 13, 'col_status': 15, 'cor': '#784212', 'emoji': '🟠'},
}

# Colunas onde o usuário pode ter colocado IDPEDIDO manualmente
# Aceita qualquer coluna com header contendo "IDPEDIDO" ou "ID"
_COLUNAS_ID_MANUAL = {
    'C': 2,   # usuário indicou col C
    'L': 11,  # usuário indicou col L
    'U': 20,  # usuário indicou col U
    'F': 5,   # padrão Linha A
    'K': 10,  # padrão Linha B
    'Q': 16,  # padrão Linha C
}
_LINHA_INI = 7
_LINHA_FIM = 26


# ── Persistência do plano ─────────────────────────────────────────────────────

def _salvar_plano(plano: dict):
    """Salva o plano diário em JSON local e no GitHub."""
    _PLANO_JSON.parent.mkdir(parents=True, exist_ok=True)
    _PLANO_JSON.write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding='utf-8')
    # Sincroniza com GitHub se disponível
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/plano_diario.json"
            headers = {"Authorization": f"token {token}"}
            conteudo = base64.b64encode(
                json.dumps(plano, ensure_ascii=False, indent=2).encode('utf-8')
            ).decode()
            r = requests.get(url, headers=headers, timeout=5)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload = {"message": "Atualiza plano diário", "content": conteudo, "branch": branch}
            if sha:
                payload["sha"] = sha
            requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


def _carregar_plano() -> dict:
    """Carrega o plano diário salvo (local ou GitHub)."""
    # Tenta GitHub primeiro
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/plano_diario.json?ref={branch}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
                return json.loads(conteudo)
    except Exception:
        pass
    # Fallback local
    if _PLANO_JSON.exists():
        try:
            return json.loads(_PLANO_JSON.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


# ── Leitura da planilha ───────────────────────────────────────────────────────

def _detectar_colunas_id(df: pd.DataFrame) -> dict:
    """
    Detecta automaticamente as colunas de IDPEDIDO na planilha.
    Procura por headers contendo 'IDPEDIDO' ou 'ID' nas linhas 6-7.
    Retorna {linha_producao: col_index} ex: {'A': 5, 'B': 10, 'C': 16}
    """
    cols_encontradas = []

    # Varre linhas de cabeçalho procurando "IDPEDIDO" ou "ID"
    for row_idx in range(5, 8):
        if row_idx >= len(df):
            break
        for col_idx in range(len(df.columns)):
            val = str(df.iloc[row_idx, col_idx]).strip().upper()
            if val in ('IDPEDIDO', 'ID', 'IDPEDIDO\n', 'ID PEDIDO', 'ID_PEDIDO'):
                if col_idx not in cols_encontradas:
                    cols_encontradas.append(col_idx)

    # Também tenta as colunas que o usuário indicou (C=2, L=11, U=20)
    for nome, idx in _COLUNAS_ID_MANUAL.items():
        if idx < len(df.columns) and idx not in cols_encontradas:
            # Verifica se alguma linha de dados tem valor numérico nessa coluna
            for row_idx in range(_LINHA_INI, min(_LINHA_FIM, len(df))):
                val = str(df.iloc[row_idx, idx]).strip()
                if val and val not in ('', 'nan') and val.isdigit():
                    cols_encontradas.append(idx)
                    break

    cols_encontradas = sorted(set(cols_encontradas))

    # Associa cada coluna encontrada a uma linha de produção (A, B, C)
    linhas = list(_CFG_LINHAS.keys())
    resultado = {}
    for i, linha_id in enumerate(linhas):
        if i < len(cols_encontradas):
            resultado[linha_id] = cols_encontradas[i]
        else:
            resultado[linha_id] = _CFG_LINHAS[linha_id]['col_id']  # fallback padrão

    return resultado


def _ler_planilha(arquivo) -> dict:
    df = pd.read_excel(arquivo, sheet_name=0, header=None, dtype=str)
    df = df.fillna('')

    # Data no banner
    data_str = datetime.date.today().strftime('%d/%m/%Y')
    try:
        import re
        banner = str(df.iloc[1, 1])
        m = re.search(r'(\d{2}/\d{2}/\d{4})', banner)
        if m:
            data_str = m.group(1)
    except Exception:
        pass

    # Detecta automaticamente as colunas de IDPEDIDO
    colunas_id = _detectar_colunas_id(df)

    resultado = {'data': data_str, 'linhas': {}, 'colunas_id': colunas_id}

    for linha_id, cfg in _CFG_LINHAS.items():
        col_id = colunas_id.get(linha_id, cfg['col_id'])
        itens = []

        for row_idx in range(_LINHA_INI, min(_LINHA_FIM, len(df))):
            try:
                cliente = str(df.iloc[row_idx, cfg['col_cliente']]).strip()
                qtd     = str(df.iloc[row_idx, cfg['col_qtd']]).strip()

                if not cliente or cliente in ('', 'nan'):
                    continue
                if any(p in cliente.upper() for p in ('TOTAL', 'PROGRAMADO')):
                    continue

                # Lê IDPEDIDO da coluna detectada
                idpedido = ''
                try:
                    if col_id < len(df.columns):
                        val = str(df.iloc[row_idx, col_id]).strip()
                        if val and val not in ('nan', '0', '') and val.replace('.','').isdigit():
                            idpedido = val.split('.')[0]  # remove decimal se houver
                except Exception:
                    pass

                itens.append({
                    'idpedido': idpedido,
                    'cliente':  cliente,
                    'qtd':      qtd if qtd not in ('', 'nan') else '—',
                })
            except Exception:
                continue
        resultado['linhas'][linha_id] = itens

    return resultado


# ── Cruzamento com banco ──────────────────────────────────────────────────────

def _buscar_os(idpedido: str, cliente: str, df_banco: pd.DataFrame) -> pd.DataFrame:
    """
    Busca OS pelo IDPEDIDO se disponível, senão pelo nome do cliente.
    """
    if idpedido and idpedido.strip():
        # Busca exata por IDPEDIDOPNEU
        resultado = df_banco[df_banco['IDPEDIDOPNEU'] == idpedido.strip()]
        if not resultado.empty:
            return resultado

    # Fallback: busca por cliente (match parcial, case insensitive)
    if cliente and cliente.strip():
        cliente_upper = cliente.strip().upper()
        mask = df_banco['CLIENTE'].str.upper().str.contains(cliente_upper, na=False, regex=False)
        # Se o cliente tiver mais de uma palavra, tenta com a primeira
        if mask.sum() == 0 and ' ' in cliente_upper:
            primeira = cliente_upper.split()[0]
            if len(primeira) > 3:
                mask = df_banco['CLIENTE'].str.upper().str.contains(primeira, na=False, regex=False)
        return df_banco[mask]

    return pd.DataFrame()


# ── Tela principal ────────────────────────────────────────────────────────────

def tela_producao_diaria():
    st.title("🏗️ Pneus a Produzir")

    df_banco = st.session_state.bd_pneus

    # ── Abas ─────────────────────────────────────────────────────────────────
    aba1, aba2, aba3, aba4 = st.tabs([
        "📷 Bipe de Entrada",
        "🏭 Clientes em Linha",
        "📂 Importar Planilha",
        "📋 Plano Salvo"
    ])

    with aba1:
        _aba_bipe(df_banco)

    with aba2:
        _aba_clientes_em_linha(df_banco)

    with aba3:
        _aba_importar(df_banco)

    with aba4:
        _aba_plano_salvo(df_banco)


def _aba_bipe(df_banco: pd.DataFrame):
    """
    Bipe de entrada na produção com trava de IDPEDIDO.
    - NRORDEM   → dá baixa em 1 pneu (se houver trava, só aceita do ID travado)
    - IDPEDIDO  → ativa trava: todos os pneus devem entrar antes de mudar de ID
    """
    from modules.database import salvar_dados

    st.subheader("📷 Bipagem de Entrada na Produção")

    # ── Trava de IDPEDIDO ────────────────────────────────────────────────────
    id_travado = st.session_state.get('id_travado', None)
    df = st.session_state.bd_pneus

    if id_travado:
        os_trava   = df[df['IDPEDIDOPNEU'] == id_travado]
        pendentes  = os_trava[os_trava['STATUS'].isin(['Aguardando', 'Em Produção'])]
        total_id   = len(os_trava)
        na_linha   = total_id - len(pendentes)
        cliente_tr = os_trava['CLIENTE'].iloc[0] if not os_trava.empty else ''
        perc       = int(na_linha / total_id * 100) if total_id > 0 else 0

        st.markdown(
            f"""<div style="background:#7d6608;border:2px solid #f0c800;
                border-radius:8px;padding:12px 18px;margin-bottom:12px;">
              <h4 style="color:#fff;margin:0 0 6px 0;">
                🔒 TRAVA ATIVA — IDPEDIDO: {id_travado} | {cliente_tr}
              </h4>
              <p style="color:#ffe;margin:0;">
                {na_linha}/{total_id} pneus na linha —
                faltam <b>{len(pendentes)}</b> para liberar o próximo pedido
              </p>
            </div>""",
            unsafe_allow_html=True
        )
        st.progress(perc, text=f"{na_linha}/{total_id} pneus confirmados ({perc}%)")

        if len(pendentes) == 0:
            st.success("✅ Todos os pneus deste IDPEDIDO entraram na linha! Trava liberada.")
            if st.button("🔓 Liberar trava e iniciar próximo", type="primary", key="liberar_trava"):
                st.session_state.id_travado = None
                st.session_state.prod_bipe_key = st.session_state.get('prod_bipe_key', 0) + 1
                st.rerun()
            return
    else:
        st.info(
            "**Bipe o NRORDEM** para dar baixa em 1 pneu, ou "
            "**bipe/digite o IDPEDIDO** para ativar a trava da coleta."
        )

    if 'prod_bipe_key' not in st.session_state:
        st.session_state.prod_bipe_key = 0

    placeholder_txt = (
        f"Bipe NRORDEM do IDPEDIDO {id_travado}..." if id_travado
        else "Ex: 1610546 (NRORDEM) ou 356774 (IDPEDIDO)"
    )

    codigo = st.text_input(
        "🔍 Bipe NRORDEM ou IDPEDIDO:",
        key=f"bipe_prod_{st.session_state.prod_bipe_key}",
        placeholder=placeholder_txt
    )

    if codigo:
        codigo = codigo.strip()
        agora  = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        idx_nrordem  = df.index[df['NRORDEM']      == codigo].tolist()
        idx_idpedido = df.index[df['IDPEDIDOPNEU'] == codigo].tolist()

        # ── Trava ativa: só aceita NRORDEM do ID travado ─────────────────────
        if id_travado and idx_nrordem:
            i = idx_nrordem[0]
            id_do_pneu = str(df.at[i, 'IDPEDIDOPNEU']).strip()
            if id_do_pneu != id_travado:
                st.error(
                    f"🔒 **TRAVA ATIVA!** Este pneu é do IDPEDIDO **{id_do_pneu}** "
                    f"mas a trava está no **{id_travado}**.\n\n"
                    f"Confirme todos os pneus do IDPEDIDO **{id_travado}** antes de continuar."
                )
                st.session_state.prod_bipe_key += 1
                st.rerun()

        if idx_nrordem:
            # ── Bipe de pneu individual ──────────────────────────────────────
            i            = idx_nrordem[0]
            status_atual = str(df.at[i, 'STATUS']).strip()
            cliente      = df.at[i, 'CLIENTE']
            desenho      = df.at[i, 'DESENHO']
            nrserie      = df.at[i, 'NRSERIE']
            id_pneu      = str(df.at[i, 'IDPEDIDOPNEU']).strip()

            if status_atual in ('Aguardando', 'Em Produção'):
                st.session_state.bd_pneus.at[i, 'STATUS']       = 'Em Produção'
                st.session_state.bd_pneus.at[i, 'DATA_ENTRADA'] = agora
                salvar_dados(st.session_state.bd_pneus)

                # Verifica se ainda faltam pneus do mesmo IDPEDIDO
                df_up   = st.session_state.bd_pneus
                faltam  = df_up[
                    (df_up['IDPEDIDOPNEU'] == id_pneu) &
                    (df_up['STATUS'].isin(['Aguardando', 'Em Produção']))
                ]
                total_id = len(df_up[df_up['IDPEDIDOPNEU'] == id_pneu])
                na_linha = total_id - len(faltam)

                if len(faltam) > 0 and id_travado == id_pneu:
                    msg_extra = f" | Faltam **{len(faltam)}** pneus do IDPEDIDO {id_pneu}"
                else:
                    msg_extra = f" | {na_linha}/{total_id} pneus do IDPEDIDO {id_pneu} na linha"

                st.session_state.msg_prod_bipe = (
                    f"✅ OS **{codigo}** | **{cliente}** | {desenho} | "
                    f"Série: {nrserie} → **Na Linha!**{msg_extra}"
                )
                st.session_state.prod_bipe_key += 1
                st.rerun()

            elif status_atual == 'Expedido':
                st.error(f"🛑 OS **{codigo}** já foi **Expedida**.")

        elif idx_idpedido:
            # ── IDPEDIDO: ativa trava e mostra coleta ───────────────────────
            # Verifica se há trava de outro ID ativa
            if id_travado and id_travado != codigo:
                os_trava  = df[df['IDPEDIDOPNEU'] == id_travado]
                pendentes = os_trava[os_trava['STATUS'].isin(['Aguardando', 'Em Produção'])]
                if len(pendentes) > 0:
                    st.error(
                        f"🔒 **Não é possível iniciar IDPEDIDO {codigo}!**\n\n"
                        f"Ainda faltam **{len(pendentes)} pneus** do IDPEDIDO **{id_travado}** "
                        f"entrarem na linha. Bipe todos antes de continuar."
                    )
                    st.session_state.prod_bipe_key += 1
                    st.rerun()

            os_coleta  = df.loc[idx_idpedido].copy()
            cliente    = os_coleta['CLIENTE'].iloc[0]
            pendentes  = os_coleta[os_coleta['STATUS'].isin(['Aguardando', 'Em Produção'])]
            expedido   = os_coleta[os_coleta['STATUS'] == 'Expedido']
            total      = len(os_coleta)
            na_linha   = total - len(pendentes)

            # Ativa trava automaticamente
            if len(pendentes) > 0:
                st.session_state.id_travado = codigo

            st.markdown(
                f"<div style='background:#1a5276;border-radius:7px;padding:12px 18px;'>"
                f"<h4 style='color:#fff;margin:0;'>📦 IDPEDIDO: {codigo} — {cliente}</h4>"
                f"<small style='color:#aad;'>Total: {total} pneus | "
                f"🔵 {na_linha} na linha | ⏳ {len(pendentes)} faltando | "
                f"🟢 {len(expedido)} Exped.</small></div>",
                unsafe_allow_html=True
            )
            st.progress(int(na_linha/total*100) if total else 0,
                        text=f"{na_linha}/{total} na linha")
            st.markdown("")

            exibir = os_coleta[['NRORDEM','NRSERIE','DESENHO','STATUS','LOCAL_PALLET']].copy()
            exibir = exibir.rename(columns={'LOCAL_PALLET': 'Pallet'})
            st.dataframe(
                exibir.style.apply(_colorir_status, axis=1),
                use_container_width=True, hide_index=True
            )

            if not pendentes.empty:
                c1, c2 = st.columns(2)
                if c1.button(
                    f"▶️ Confirmar todos ({len(pendentes)}) na linha",
                    key=f"lancar_{codigo}", type="primary"
                ):
                    st.session_state.bd_pneus.loc[pendentes.index, 'STATUS']       = 'Em Produção'
                    st.session_state.bd_pneus.loc[pendentes.index, 'DATA_ENTRADA'] = agora
                    salvar_dados(st.session_state.bd_pneus)
                    st.session_state.id_travado    = None
                    st.session_state.msg_prod_bipe = (
                        f"✅ **{len(pendentes)} pneus** do IDPEDIDO **{codigo}** "
                        f"({cliente}) confirmados! Trava liberada."
                    )
                    st.session_state.prod_bipe_key += 1
                    st.rerun()
                c2.info("Ou bipe cada NRORDEM um por um.")
            else:
                st.session_state.id_travado = None
                st.success("✅ Todos os pneus desta coleta já estão na linha!")

        else:
            st.error(f"❌ **{codigo}** não encontrado. Verifique o NRORDEM ou IDPEDIDO.")

    # Feedback pós-bipe
    if st.session_state.get('msg_prod_bipe'):
        st.success(st.session_state.msg_prod_bipe)
        st.session_state.msg_prod_bipe = None

    st.markdown("---")

    # Painel de OS aguardando (do plano salvo)
    plano = _carregar_plano()
    if plano:
        st.subheader(f"📋 Aguardando Produção — Plano {plano.get('data','')}")
        df_atual = st.session_state.bd_pneus
        total_aguard = 0

        for linha_id, cfg in _CFG_LINHAS.items():
            itens = plano.get('linhas', {}).get(linha_id, [])
            aguard_linha = []

            for item in itens:
                os_cli = _buscar_os(item.get('idpedido',''), item.get('cliente',''), df_atual)
                os_aguard = os_cli[os_cli['STATUS'] == 'Aguardando'] if not os_cli.empty else pd.DataFrame()
                if not os_aguard.empty:
                    for _, row in os_aguard.iterrows():
                        aguard_linha.append({
                            'NRORDEM': row['NRORDEM'],
                            'Cliente': item['cliente'],
                            'Desenho': row['DESENHO'],
                            'Série':   row['NRSERIE'],
                            'Pallet':  row.get('LOCAL_PALLET', ''),
                        })
                    total_aguard += len(os_aguard)

            if aguard_linha:
                st.markdown(
                    f"<div style='background:{cfg['cor']};border-radius:5px;"
                    f"padding:6px 12px;margin:6px 0 2px;'>"
                    f"<b style='color:#fff;'>{cfg['emoji']} LINHA {linha_id} "
                    f"— {len(aguard_linha)} pneu(s) aguardando</b></div>",
                    unsafe_allow_html=True
                )
                st.dataframe(
                    pd.DataFrame(aguard_linha),
                    use_container_width=True, hide_index=True
                )

        if total_aguard == 0:
            st.success("✅ Todos os pneus do plano já estão em produção!")
        else:
            st.info(f"🔍 Bipe os **NRORDEM** acima no campo de leitura para dar baixa.")
    else:
        st.info("Carregue uma planilha na aba **📂 Importar Planilha** para ver os pneus a bipar.")


def _aba_clientes_em_linha(df_banco: pd.DataFrame):
    """
    Mostra todos os clientes com pneus na linha de produção hoje,
    com indicador de quantos faltam entrar por IDPEDIDO.
    """
    st.subheader("🏭 Clientes em Linha de Produção")

    df = st.session_state.bd_pneus

    # Todos os pneus Em Produção agrupados por cliente e IDPEDIDO
    em_linha = df[df['STATUS'] == 'Em Produção'].copy()
    # Pneus do mesmo cliente ainda aguardando
    aguardando = df[df['STATUS'].isin(['Aguardando'])].copy()

    if em_linha.empty:
        st.info("Nenhum pneu em linha de produção no momento.")
        return

    # Agrupa por cliente
    clientes = sorted(em_linha['CLIENTE'].replace('', pd.NA).dropna().unique())

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes em linha", len(clientes))
    c2.metric("Pneus em produção", len(em_linha))
    c3.metric("Pneus aguardando entrada", len(aguardando))

    st.markdown("---")

    for cliente in clientes:
        em_linha_cli = em_linha[em_linha['CLIENTE'] == cliente]
        aguard_cli   = aguardando[aguardando['CLIENTE'] == cliente]
        ids_cliente  = em_linha_cli['IDPEDIDOPNEU'].replace('', pd.NA).dropna().unique()

        # Conta pneus faltando por IDPEDIDO
        detalhes_ids = []
        for idp in ids_cliente:
            total_id   = len(df[df['IDPEDIDOPNEU'] == idp])
            na_linha   = len(em_linha_cli[em_linha_cli['IDPEDIDOPNEU'] == idp])
            faltam_id  = len(df[(df['IDPEDIDOPNEU'] == idp) &
                                 (df['STATUS'].isin(['Aguardando']))])
            detalhes_ids.append({
                'IDPEDIDO': idp,
                'Na Linha': na_linha,
                'Total':    total_id,
                'Faltam':   faltam_id,
            })

        total_na_linha = len(em_linha_cli)
        total_faltam   = len(aguard_cli)
        completo       = total_faltam == 0

        cor_hdr = '#155724' if completo else '#004085'
        icone   = '✅' if completo else '⏳'

        with st.expander(
            f"{icone} **{cliente}** — {total_na_linha} na linha | "
            f"{'Completo' if completo else str(total_faltam) + ' faltando'}",
            expanded=not completo
        ):
            # Tabela por IDPEDIDO
            if detalhes_ids:
                df_ids = pd.DataFrame(detalhes_ids)
                def _cor_id(row):
                    if row.get('Faltam', 0) == 0:
                        return ['background:#d4edda;color:#155724'] * len(row)
                    return ['background:#cce5ff;color:#004085'] * len(row)
                st.dataframe(
                    df_ids.style.apply(_cor_id, axis=1),
                    use_container_width=True, hide_index=True
                )

            # Pneus na linha
            st.markdown("**Pneus na linha:**")
            exibir = em_linha_cli[['NRORDEM','IDPEDIDOPNEU','NRSERIE','DESENHO',
                                    'LOCAL_PALLET','DATA_ENTRADA']].copy()
            exibir = exibir.rename(columns={
                'LOCAL_PALLET': 'Pallet', 'DATA_ENTRADA': 'Entrada'
            })
            st.dataframe(exibir, use_container_width=True, hide_index=True)

            # Pneus que ainda faltam
            if not aguard_cli.empty:
                st.markdown(f"**⏳ Faltam entrar ({len(aguard_cli)}):**")
                falt = aguard_cli[['NRORDEM','IDPEDIDOPNEU','NRSERIE','DESENHO','LOCAL_PALLET']].copy()
                falt = falt.rename(columns={'LOCAL_PALLET': 'Pallet'})
                st.dataframe(
                    falt.style.applymap(lambda _: 'background:#fff3cd;color:#856404'),
                    use_container_width=True, hide_index=True
                )


def _aba_importar(df_banco: pd.DataFrame):
    st.subheader("Carregar Programação Diária")
    st.info(
        "Carregue a planilha. O sistema vincula cada cliente com as OS do banco.\n\n"
        "**Com IDPEDIDO preenchido (cols F/K/Q):** vinculação exata.\n"
        "**Sem IDPEDIDO:** vinculação automática pelo nome do cliente."
    )

    arquivo = st.file_uploader(
        "📂 Selecione PLANEJAMENTO_DIARIO_PCP.xlsx:",
        type=["xlsx", "xls"],
        key="uploader_planejamento"
    )

    if not arquivo:
        _exibir_instrucoes()
        return

    try:
        plano = _ler_planilha(arquivo)
    except Exception as e:
        st.error(f"❌ Erro ao ler planilha: {e}")
        return

    data_plano = plano['data']
    total_itens = sum(len(v) for v in plano['linhas'].values())

    st.markdown(
        f"<div style='background:#003366;border-radius:8px;padding:10px 18px;'>"
        f"<h3 style='color:#fff;margin:0;'>📋 Programação — {data_plano} | {total_itens} clientes</h3>"
        f"</div>", unsafe_allow_html=True
    )
    st.markdown("")

    # Monta resumo enriquecido com OS do banco
    plano_completo = {'data': data_plano, 'linhas': {}}
    resumo_geral = {'aguard': 0, 'prod': 0, 'exped': 0, 'sem_os': 0}

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = plano['linhas'].get(linha_id, [])
        if not itens:
            continue

        cor   = cfg['cor']
        emoji = cfg['emoji']
        itens_enriquecidos = []
        total_os_linha = 0

        st.markdown(
            f"<div style='background:{cor};border-radius:6px;padding:8px 16px;margin:10px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>{emoji} LINHA {linha_id} — {len(itens)} cliente(s)</h4>"
            f"</div>", unsafe_allow_html=True
        )

        for item in itens:
            os_cliente = _buscar_os(item['idpedido'], item['cliente'], df_banco)
            total_os_linha += len(os_cliente)

            aguard = len(os_cliente[os_cliente['STATUS'] == 'Aguardando'])
            prod   = len(os_cliente[os_cliente['STATUS'] == 'Em Produção'])
            exped  = len(os_cliente[os_cliente['STATUS'] == 'Expedido'])

            resumo_geral['aguard'] += aguard
            resumo_geral['prod']   += prod
            resumo_geral['exped']  += exped
            if os_cliente.empty:
                resumo_geral['sem_os'] += 1

            # Salva para persistência
            itens_enriquecidos.append({
                **item,
                'idpedidos_encontrados': os_cliente['IDPEDIDOPNEU'].unique().tolist() if not os_cliente.empty else [],
                'nrordens': os_cliente['NRORDEM'].tolist() if not os_cliente.empty else [],
            })

            modo = '✅ IDPEDIDO' if item['idpedido'] else '🔍 Cliente'
            label = (
                f"**{item['cliente']}** | Qtd: {item['qtd']} | "
                f"🟡 {aguard} 🔵 {prod} 🟢 {exped} | Busca: {modo}"
            )

            if os_cliente.empty:
                with st.expander(f"⚠️ {item['cliente']} — Não encontrado"):
                    st.warning("Cliente não encontrado no banco. Verifique o nome ou importe o CSV.")
            else:
                with st.expander(label, expanded=(aguard > 0)):
                    exibir = os_cliente[[
                        'NRORDEM', 'IDPEDIDOPNEU', 'NRSERIE', 'DESENHO',
                        'STATUS', 'LOCAL_PALLET', 'DATA_ENTRADA', 'DATA_SAIDA'
                    ]].copy().rename(columns={
                        'LOCAL_PALLET': 'Pallet',
                        'DATA_ENTRADA': 'Data Coleta',
                        'DATA_SAIDA':   'Entrega Prev.',
                    })
                    st.dataframe(
                        exibir.style.apply(_colorir_status, axis=1),
                        use_container_width=True, hide_index=True
                    )

                    if aguard > 0:
                        if st.button(
                            f"▶️ Enviar {aguard} pneu(s) para Produção",
                            key=f"prod_{linha_id}_{item['cliente']}",
                            type="primary"
                        ):
                            from modules.database import salvar_dados
                            ids_busca = os_cliente.index[os_cliente['STATUS'] == 'Aguardando']
                            agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            st.session_state.bd_pneus.loc[ids_busca, 'STATUS'] = 'Em Produção'
                            st.session_state.bd_pneus.loc[ids_busca, 'DATA_ENTRADA'] = agora
                            salvar_dados(st.session_state.bd_pneus)
                            st.success(f"✅ {aguard} pneu(s) de {item['cliente']} enviados para produção!")
                            st.rerun()

        plano_completo['linhas'][linha_id] = itens_enriquecidos

    # ── Salva o plano ─────────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟡 Aguardando", resumo_geral['aguard'])
    c2.metric("🔵 Em Produção", resumo_geral['prod'])
    c3.metric("🟢 Expedidos",  resumo_geral['exped'])
    c4.metric("⚠️ Sem OS",     resumo_geral['sem_os'])

    if st.button("💾 Salvar este plano", type="primary", key="btn_salvar_plano"):
        _salvar_plano(plano_completo)
        st.success(f"✅ Plano de {data_plano} salvo com sucesso!")
        st.rerun()


def _aba_plano_salvo(df_banco: pd.DataFrame):
    st.subheader("Plano Diário Salvo")
    plano = _carregar_plano()

    if not plano:
        st.info("Nenhum plano salvo ainda. Importe a planilha na aba ao lado e clique em 💾 Salvar.")
        return

    data_plano = plano.get('data', '—')
    st.markdown(
        f"<div style='background:#003366;border-radius:8px;padding:10px 18px;'>"
        f"<h3 style='color:#fff;margin:0;'>📋 Plano salvo — {data_plano}</h3>"
        f"</div>", unsafe_allow_html=True
    )
    st.markdown("")

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = plano.get('linhas', {}).get(linha_id, [])
        if not itens:
            continue

        st.markdown(
            f"<div style='background:{cfg['cor']};border-radius:6px;padding:8px 16px;margin:10px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>{cfg['emoji']} LINHA {linha_id} — {len(itens)} cliente(s)</h4>"
            f"</div>", unsafe_allow_html=True
        )

        for item in itens:
            # Recarrega OS do banco em tempo real
            os_cliente = _buscar_os(item.get('idpedido',''), item.get('cliente',''), df_banco)
            aguard = len(os_cliente[os_cliente['STATUS'] == 'Aguardando']) if not os_cliente.empty else 0
            prod   = len(os_cliente[os_cliente['STATUS'] == 'Em Produção']) if not os_cliente.empty else 0
            exped  = len(os_cliente[os_cliente['STATUS'] == 'Expedido'])    if not os_cliente.empty else 0

            label = (
                f"**{item.get('cliente','—')}** | Qtd: {item.get('qtd','—')} | "
                f"🟡 {aguard} 🔵 {prod} 🟢 {exped}"
            )

            with st.expander(label, expanded=(aguard > 0)):
                if os_cliente.empty:
                    st.warning("OS não encontrada no banco.")
                else:
                    exibir = os_cliente[[
                        'NRORDEM', 'IDPEDIDOPNEU', 'NRSERIE', 'DESENHO',
                        'STATUS', 'LOCAL_PALLET', 'DATA_ENTRADA'
                    ]].copy().rename(columns={'LOCAL_PALLET': 'Pallet', 'DATA_ENTRADA': 'Data Coleta'})
                    st.dataframe(
                        exibir.style.apply(_colorir_status, axis=1),
                        use_container_width=True, hide_index=True
                    )

                    if aguard > 0:
                        if st.button(
                            f"▶️ Enviar {aguard} pneu(s) para Produção",
                            key=f"plano_{linha_id}_{item.get('cliente','')}",
                            type="primary"
                        ):
                            from modules.database import salvar_dados
                            ids_busca = os_cliente.index[os_cliente['STATUS'] == 'Aguardando']
                            agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            st.session_state.bd_pneus.loc[ids_busca, 'STATUS'] = 'Em Produção'
                            st.session_state.bd_pneus.loc[ids_busca, 'DATA_ENTRADA'] = agora
                            salvar_dados(st.session_state.bd_pneus)
                            st.success(f"✅ {aguard} pneu(s) enviados para produção!")
                            st.rerun()


def _colorir_status(row: pd.Series):
    cores = {
        'Aguardando':  'background-color:#fff3cd;color:#856404',
        'Em Produção': 'background-color:#cce5ff;color:#004085',
        'Expedido':    'background-color:#d4edda;color:#155724',
    }
    return [cores.get(str(row.get('STATUS', '')).strip(), '')] * len(row)


def _exibir_instrucoes():
    with st.expander("📖 Como usar", expanded=True):
        st.markdown("""
        **Com IDPEDIDO na planilha (recomendado):**
        1. Abra `PLANEJAMENTO_DIARIO_PCP.xlsx`
        2. Preencha a coluna **F** com IDPEDIDO da **Linha A**
        3. Preencha a coluna **K** com IDPEDIDO da **Linha B**
        4. Preencha a coluna **Q** com IDPEDIDO da **Linha C**

        **Sem IDPEDIDO:**
        - O sistema encontra as OS automaticamente pelo **nome do cliente**

        **Depois de carregar:**
        - Veja as OS de cada cliente por linha de produção
        - Clique **"▶️ Enviar para Produção"** para lançar em lote
        - Clique **"💾 Salvar este plano"** para manter o plano disponível

        **Aba "Plano Salvo":**
        - Mostra o último plano importado com status atualizado em tempo real
        """)
