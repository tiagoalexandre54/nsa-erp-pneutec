"""
Tela — Pneus a Produzir e Trânsito.
Integração com a Planilha Oficial de PPCP e Trava Poka-Yoke por IDPEDIDO.
"""
import streamlit as st
import pandas as pd
import datetime
import json
from pathlib import Path

_BASE_DIR   = Path(__file__).resolve().parent.parent
_PLANO_JSON = _BASE_DIR / "data" / "plano_diario.json"


# ── Persistência do Plano Diário no GitHub ────────────────────────────────────
def _salvar_plano(plano: dict) -> None:
    """Salva o plano diário como JSON local e no GitHub."""
    conteudo_str = json.dumps(plano, ensure_ascii=False, indent=2)
    try:
        _PLANO_JSON.parent.mkdir(parents=True, exist_ok=True)
        _PLANO_JSON.write_text(conteudo_str, encoding="utf-8")
    except Exception:
        pass
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return
        import requests, base64
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/data/plano_diario.json"
        headers = {"Authorization": f"token {token}"}
        conteudo_b64 = base64.b64encode(conteudo_str.encode("utf-8")).decode()
        r = requests.get(url, headers=headers, timeout=5)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": "Atualiza plano diario", "content": conteudo_b64, "branch": branch}
        if sha:
            payload["sha"] = sha
        requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


def _carregar_plano() -> dict | None:
    """Carrega o plano diário salvo (GitHub → local → None)."""
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
    if _PLANO_JSON.exists():
        try:
            return json.loads(_PLANO_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

# ── Mapeamento EXATO da Planilha Oficial ─────────────────────────────────────
# Linha A: Colunas 1, 2, 4 (B, C, E no Excel) | Cap: 150 + 10% = 165
# Linha B: Colunas 9, 10, 12 (J, K, M no Excel) | Cap: 155 + 10% = 170
# Linha C: Colunas 17, 18, 20 (R, S, U no Excel) | Cap: 89 + 10% = 98

_CFG_LINHAS = {
    'A': {'col_id': 5,  'col_cliente': 2,  'col_qtd': 3,  'cor': '#1a5276', 'emoji': '🔵', 'cap_max': 165},
    'B': {'col_id': 10, 'col_cliente': 7,  'col_qtd': 8,  'cor': '#1e8449', 'emoji': '🟢', 'cap_max': 170},
    'C': {'col_id': 16, 'col_cliente': 12, 'col_qtd': 13, 'cor': '#784212', 'emoji': '🟠', 'cap_max': 98},
}

_LINHA_INI = 7   # dados começam na linha 8 do Excel (índice 7 no Pandas)
_LINHA_FIM = 40


# ── Leitura do Excel / CSV de Programação ────────────────────────────────────
def _ler_planilha(arquivo) -> dict:
    nome = getattr(arquivo, 'name', '') or ''
    if nome.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(arquivo, sheet_name=0, header=None, dtype=str)
        df = df.fillna('')
    else:
        try:
            df = pd.read_csv(arquivo, header=None, dtype=str, keep_default_na=False)
        except Exception:
            # Reseta ponteiro antes de tentar como Excel
            try:
                arquivo.seek(0)
            except Exception:
                pass
            df = pd.read_excel(arquivo, sheet_name=0, header=None, dtype=str)
            df = df.fillna('')

    resultado = {'data': datetime.date.today().strftime('%d/%m/%Y'), 'linhas': {}}

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = []
        for row_idx in range(_LINHA_INI, min(_LINHA_FIM, len(df))):
            try:
                cliente = str(df.iloc[row_idx, cfg['col_cliente']]).strip()
                qtd     = str(df.iloc[row_idx, cfg['col_qtd']]).strip()

                if not cliente or cliente in ('', 'nan'):
                    continue
                if any(p in cliente.upper() for p in ('TOTAL', 'PROGRAMADO')):
                    continue

                idpedido = str(df.iloc[row_idx, cfg['col_id']]).strip()
                if idpedido in ('nan', '0', ''):
                    idpedido = ''
                elif idpedido.replace('.', '').isdigit():
                    idpedido = idpedido.split('.')[0]

                # Normaliza QTD: "4.0" → "4", "nan" → "0"
                try:
                    qtd_norm = str(int(float(qtd))) if qtd and qtd not in ('nan', '') else '0'
                except Exception:
                    qtd_norm = '0'

                itens.append({
                    'idpedido': idpedido,
                    'cliente':  cliente,
                    'qtd':      qtd_norm,
                })
            except Exception:
                continue
        resultado['linhas'][linha_id] = itens
    return resultado


def _buscar_os(idpedido: str, cliente: str, df_banco: pd.DataFrame) -> pd.DataFrame:
    """Busca os pneus do cliente, priorizando o IDPEDIDO se existir.
    Fallback: banco contém o nome abreviado da planilha (mínimo 4 chars)."""
    if idpedido:
        res = df_banco[df_banco['IDPEDIDOPNEU'] == idpedido]
        if not res.empty:
            return res
    if cliente:
        cliente_up = cliente.upper().strip()
        nomes = df_banco['CLIENTE'].str.upper().str.strip()
        # 1. Match exato
        res = df_banco[nomes == cliente_up]
        if not res.empty:
            return res
        # 2. Banco contém o nome da planilha — só se tiver ≥4 chars (evita matches amplos)
        if len(cliente_up) >= 4:
            res = df_banco[nomes.str.contains(cliente_up, regex=False, na=False)]
            if not res.empty:
                return res
    return pd.DataFrame()


# ── Tela Principal ────────────────────────────────────────────────────────────
def tela_producao_diaria():
    st.title("🏗️ Pneus a Produzir e Trânsito")
    df_banco = st.session_state.bd_pneus

    aba1, aba2, aba3 = st.tabs([
        "📷 1. Linha de Produção (Bipe)",
        "📂 2. Importar & Pneus em Trânsito",
        "🏭 3. Status Clientes",
    ])

    with aba1:
        _aba_bipe(df_banco)
    with aba2:
        _aba_importar(df_banco)
    with aba3:
        _aba_clientes_em_linha(df_banco)


# ── 1. Bipe de Produção (Trava Poka-Yoke por IDPEDIDO) ───────────────────────
def _aba_bipe(df: pd.DataFrame):
    from modules.database import salvar_dados, ler_trava_global, set_trava_global

    st.subheader("Bipagem de Entrada na Máquina")

    id_travado = ler_trava_global()

    if id_travado:
        os_trava  = df[df['IDPEDIDOPNEU'] == id_travado]
        pendentes = os_trava[os_trava['STATUS'] == 'Aguardando']

        if not os_trava.empty:
            cliente_tr = os_trava['CLIENTE'].iloc[0]
            total_id   = len(os_trava)
            na_linha   = total_id - len(pendentes)

            st.error(
                f"🔒 **TRAVA ATIVA!** A linha está bloqueada no IDPEDIDO "
                f"**{id_travado}** ({cliente_tr})."
            )
            st.progress(na_linha / total_id if total_id > 0 else 0)

            if not pendentes.empty:
                st.warning(
                    f"⚠️ **FALTAM {len(pendentes)} PNEUS** para liberar o sistema. "
                    f"Procure as seguintes OS:"
                )
                st.dataframe(
                    pendentes[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET']],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.success("🎉 **TODOS OS PNEUS DA COLETA ENTRARAM!** O sistema está liberado.")
                if st.button("🔓 Iniciar Próxima Coleta", type="primary"):
                    set_trava_global(None)
                    st.rerun()
                return
        else:
            set_trava_global(None)
            st.rerun()
    else:
        st.info(
            "Digite ou Bipe o **IDPEDIDO** para puxar toda a coleta "
            "e travar a linha de produção."
        )

    if 'prod_bipe_key' not in st.session_state:
        st.session_state.prod_bipe_key = 0

    codigo = st.text_input(
        "🔍 Bipe a OS (NRORDEM) ou o IDPEDIDO:",
        key=f"bipe_{st.session_state.prod_bipe_key}",
        placeholder="Aguardando leitura do código de barras...",
    )

    if not codigo:
        return

    codigo = codigo.strip()
    df     = st.session_state.bd_pneus

    idx_nrordem  = df.index[df['NRORDEM']      == codigo].tolist()
    idx_idpedido = df.index[df['IDPEDIDOPNEU'] == codigo].tolist()

    # Bipou um pneu individual (NRORDEM)
    if idx_nrordem:
        i          = idx_nrordem[0]
        id_do_pneu = str(df.at[i, 'IDPEDIDOPNEU']).strip()

        if id_travado and id_do_pneu != id_travado:
            st.error(
                f"🛑 **PNEU ERRADO!** Esta OS pertence ao IDPEDIDO **{id_do_pneu}**, "
                f"mas a linha aguarda o **{id_travado}**."
            )
            st.session_state.prod_bipe_key += 1
            st.rerun()

        status_atual = str(df.at[i, 'STATUS']).strip()
        if status_atual == 'Aguardando':
            st.session_state.bd_pneus.at[i, 'STATUS']      = 'Em Produção'
            st.session_state.bd_pneus.at[i, 'DATA_ENTRADA'] = (
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )
            salvar_dados(st.session_state.bd_pneus)

            df_up  = st.session_state.bd_pneus
            faltam = len(
                df_up[
                    (df_up['IDPEDIDOPNEU'] == id_do_pneu) &
                    (df_up['STATUS'] == 'Aguardando')
                ]
            )
            if faltam == 0 and id_travado == id_do_pneu:
                st.success("✅ ÚLTIMO PNEU! Coleta completa. Clique em 🔓 para liberar.")
            else:
                st.success(f"✅ OS {codigo} registrada! Faltam {faltam} pneus desta coleta.")

            st.session_state.prod_bipe_key += 1
            st.rerun()
        else:
            st.warning(f"⚠️ A OS {codigo} já consta como **{status_atual}**.")

    # Bipou um IDPEDIDO (ativa trava global)
    elif idx_idpedido:
        if id_travado and id_travado != codigo:
            st.error("🔒 Finalize a coleta atual antes de iniciar um novo IDPEDIDO.")
        else:
            set_trava_global(codigo)
            st.session_state.prod_bipe_key += 1
            st.rerun()

    else:
        st.error("❌ Código não encontrado no banco de dados.")


# ── 2. Importar Planilha de Programação e Trânsito ───────────────────────────
def _aba_importar(df_banco: pd.DataFrame):
    st.subheader("Carregar Programação Diária")

    col_up, col_btn = st.columns([3, 1])
    arquivo = col_up.file_uploader(
        "📂 Selecione sua planilha PLANEJAMENTO_DIARIO:",
        type=["xlsx", "xls", "csv"],
        key="uploader_planejamento",
    )
    if col_btn.button("🗑️ Limpar programação salva", help="Remove o plano salvo e volta à tela de upload"):
        try:
            _PLANO_JSON.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            from modules.database import _modo_github, _github_cfg
            if _modo_github():
                import requests, base64
                token, repo, branch, _ = _github_cfg()
                url = f"https://api.github.com/repos/{repo}/contents/data/plano_diario.json"
                headers = {"Authorization": f"token {token}"}
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code == 200:
                    sha = r.json().get("sha")
                    requests.delete(url, json={"message": "Remove plano diario", "sha": sha, "branch": branch}, headers=headers, timeout=10)
        except Exception:
            pass
        st.success("Programação apagada.")
        st.rerun()

    plano = None

    if arquivo:
        try:
            plano = _ler_planilha(arquivo)
            _salvar_plano(plano)
            st.success("✅ Programação salva! Será carregada automaticamente na próxima vez.")
        except Exception as e:
            st.error(f"❌ Erro ao ler planilha: {e}")
            return
    else:
        plano = _carregar_plano()
        if plano:
            st.info(f"📂 Exibindo programação salva de **{plano.get('data', '—')}**. "
                    f"Faça upload de uma nova planilha para atualizar.")
        else:
            st.warning("Nenhuma programação salva. Faça upload da planilha PLANEJAMENTO_DIARIO.")
            return

    st.markdown(f"**Data da Programação:** {plano['data']}")
    st.markdown("---")

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = plano['linhas'].get(linha_id, [])
        if not itens:
            continue

        total_linha = sum(int(item['qtd']) for item in itens if str(item['qtd']).isdigit())

        st.markdown(
            f"<div style='background:{cfg['cor']};border-radius:6px;"
            f"padding:8px 16px;margin:10px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>"
            f"{cfg['emoji']} LINHA {linha_id} — {len(itens)} cliente(s) | "
            f"{total_linha} pneus programados (Limite: {cfg['cap_max']})"
            f"</h4></div>",
            unsafe_allow_html=True,
        )

        if total_linha > cfg['cap_max']:
            st.error(
                f"🚨 ALERTA LINHA {linha_id}: Capacidade excedida! "
                f"(Programado: {total_linha} | Máximo: {cfg['cap_max']})"
            )

        transito_list = []
        for item in itens:
            os_cliente = _buscar_os(item['idpedido'], item['cliente'], df_banco)
            if os_cliente.empty or 'STATUS' not in os_cliente.columns:
                continue
            aguardando = os_cliente[os_cliente['STATUS'] == 'Aguardando']
            if not aguardando.empty:
                transito_list.append(aguardando)

        if transito_list:
            df_transito = pd.concat(transito_list, ignore_index=True)
            with st.expander(
                f"🚛 Pneus em Trânsito (Fila de Espera) — "
                f"{len(df_transito)} pneus na Linha {linha_id}",
                expanded=True,
            ):
                st.dataframe(
                    df_transito[['IDPEDIDOPNEU', 'CLIENTE', 'NRORDEM', 'LOCAL_PALLET']],
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.caption(f"Nenhum pneu aguardando para a Linha {linha_id}.")

        st.markdown("")


# ── 3. Status por Cliente ─────────────────────────────────────────────────────
def _aba_clientes_em_linha(df_banco: pd.DataFrame):
    st.subheader("🏭 Status por Cliente")
    em_linha = df_banco[df_banco['STATUS'] == 'Em Produção']

    if em_linha.empty:
        st.info("Nenhum pneu em produção nas máquinas no momento.")
        return

    resumo = (
        em_linha.groupby(['CLIENTE', 'IDPEDIDOPNEU'])
        .size()
        .reset_index(name='QTD_NA_LINHA')
    )
    st.dataframe(resumo, use_container_width=True, hide_index=True)
