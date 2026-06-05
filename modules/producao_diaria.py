"""
Tela — Pneus a Produzir e Trânsito.
Integração com a Planilha Oficial de PPCP e Trava Poka-Yoke por IDPEDIDO.
"""
import streamlit as st
import pandas as pd
import datetime
import json
import re
import unicodedata
from pathlib import Path

_BASE_DIR   = Path(__file__).resolve().parent.parent
_PLANO_JSON = _BASE_DIR / "data" / "plano_diario.json"


def _norm(s: str) -> str:
    """Remove acentos, caixa alta, espaços extras — para comparar nomes."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s).upper().strip()


# ── Persistência do Plano Diário no GitHub ────────────────────────────────────
_SCHEMA_PLANO = 2   # incrementar quando o formato do plano mudar


def _plano_valido(plano: dict) -> bool:
    """Rejeita planos antigos/corrompidos (salvos por versões antigas do código)."""
    if not isinstance(plano, dict):
        return False
    if plano.get('_schema') != _SCHEMA_PLANO:
        return False
    # Sanidade: nenhum 'cliente' pode ser status/ID puro
    for itens in plano.get('linhas', {}).values():
        for it in itens:
            cli = str(it.get('cliente', '')).strip()
            if cli in ('', '—') or cli.isdigit() or '🔄' in cli or 'EM PROD' in cli.upper():
                return False
    return True


def _salvar_plano(plano: dict) -> None:
    """Salva o plano diário como JSON local e no GitHub."""
    plano = dict(plano)
    plano['_schema'] = _SCHEMA_PLANO
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
    """Carrega o plano diário salvo (GitHub → local → None).
    Planos de schema antigo/corrompido são descartados."""
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/plano_diario.json?ref={branch}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
                plano = json.loads(conteudo)
                if _plano_valido(plano):
                    return plano
    except Exception:
        pass
    if _PLANO_JSON.exists():
        try:
            plano = json.loads(_PLANO_JSON.read_text(encoding="utf-8"))
            if _plano_valido(plano):
                return plano
        except Exception:
            pass
    return None

# ── Mapeamento EXATO da Planilha Oficial (base PPCP2, com IDPEDIDO) ──────────
# Cabeçalho na linha 7 (índice 6): cada bloco tem # | IDPEDIDO | CLIENTE | QTD
# Linha A: IDPEDIDO=col 2,  CLIENTE=col 3,  QTD=col 4
# Linha B: IDPEDIDO=col 10, CLIENTE=col 11, QTD=col 13
# Linha C: IDPEDIDO=col 19, CLIENTE=col 20, QTD=col 22

_CFG_LINHAS = {
    'A': {'col_id': 2,  'col_cliente': 3,  'col_qtd': 4,  'cor': '#1a5276', 'emoji': '🔵', 'cap_max': 165},
    'B': {'col_id': 10, 'col_cliente': 11, 'col_qtd': 13, 'cor': '#1e8449', 'emoji': '🟢', 'cap_max': 170},
    'C': {'col_id': 19, 'col_cliente': 20, 'col_qtd': 22, 'cor': '#784212', 'emoji': '🟠', 'cap_max': 98},
}

_LINHA_INI = 7   # dados começam na linha 8 do Excel (índice 7 no Pandas)
_LINHA_FIM = 60


def _extrair_data(df: pd.DataFrame) -> str:
    """Procura uma célula 'DATA:' nas primeiras linhas e devolve a data ao lado.
    Se não encontrar, usa a data de hoje."""
    try:
        for r in range(min(6, len(df))):
            for c in range(min(12, df.shape[1])):
                if 'DATA' in str(df.iloc[r, c]).upper():
                    # Procura uma data parseável nas células à direita
                    for cc in range(c + 1, min(c + 6, df.shape[1])):
                        val = str(df.iloc[r, cc]).strip()
                        if not val:
                            continue
                        # ISO (2026-06-04) primeiro; só usa dayfirst no fallback BR
                        dt = pd.to_datetime(val, errors='coerce')
                        if pd.isna(dt):
                            dt = pd.to_datetime(val, errors='coerce', dayfirst=True)
                        if pd.notna(dt):
                            return dt.strftime('%d/%m/%Y')
    except Exception:
        pass
    return datetime.date.today().strftime('%d/%m/%Y')


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

    resultado = {'data': _extrair_data(df), 'linhas': {}}

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = []
        for row_idx in range(_LINHA_INI, min(_LINHA_FIM, len(df))):
            try:
                cliente = str(df.iloc[row_idx, cfg['col_cliente']]).strip()
                qtd     = str(df.iloc[row_idx, cfg['col_qtd']]).strip()

                if not cliente or cliente in ('', 'nan'):
                    continue
                # Pula totais e linhas de legenda (ex: "⛔ PARADO = Linha interrompida")
                cli_up = cliente.upper()
                if any(p in cli_up for p in (
                    'TOTAL', 'PROGRAMADO', 'PARADO', 'INTERROMP',
                    'FINALIZAR', 'LEGENDA', 'LINHA ',
                )):
                    continue
                if '=' in cliente or cliente[0] in '⛔⚠️✅🔄☀':
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


def _norm_id(v) -> str:
    """Normaliza um IDPEDIDO: '364182.0' → '364182', remove espaços."""
    s = str(v).strip()
    if s.replace('.', '', 1).isdigit():
        s = s.split('.')[0]
    return s


def _buscar_os(idpedido: str, cliente: str, df_banco: pd.DataFrame) -> pd.DataFrame:
    """Busca os pneus do cliente, priorizando o IDPEDIDO se existir.
    Fallback: nome da planilha aparece como palavra no nome do banco
    (com acentos normalizados)."""
    id_alvo = _norm_id(idpedido) if idpedido else ''
    if id_alvo:
        ids_banco = df_banco['IDPEDIDOPNEU'].apply(_norm_id)
        res = df_banco[ids_banco == id_alvo]
        if not res.empty:
            return res
    if not cliente:
        return pd.DataFrame()

    alvo = _norm(cliente)
    if not alvo:
        return pd.DataFrame()

    nomes = df_banco['CLIENTE'].apply(_norm)

    # 1. Match exato (sem acento)
    res = df_banco[nomes == alvo]
    if not res.empty:
        return res

    # 2. Nome da planilha aparece como PALAVRA INTEIRA no banco.
    #    \bALVO\b — "TRANSCAP" casa "AUTO VIAÇÃO TRANSCAP LTDA",
    #    mas "EMP" NÃO casa dentro de "EMPREENDIMENTOS".
    if len(alvo) >= 2:
        padrao = r'\b' + re.escape(alvo) + r'\b'
        res = df_banco[nomes.str.contains(padrao, regex=True, na=False)]
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
        os_trava  = df[df['IDPEDIDOPNEU'].astype(str).str.strip() == str(id_travado).strip()]
        pendentes = os_trava[os_trava['STATUS'] == 'Aguardando']

        if not os_trava.empty:
            cliente_tr = os_trava['CLIENTE'].iloc[0]
            total_id   = len(os_trava)
            na_linha   = total_id - len(pendentes)

            st.error(
                f"🔒 **TRAVA ATIVA!** Coleta **IDPEDIDO {id_travado}** — {cliente_tr}."
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("📦 Total da coleta", total_id)
            c2.metric("✅ Já na linha", na_linha)
            c3.metric("⏳ Faltam bipar", len(pendentes))
            st.progress(
                na_linha / total_id if total_id > 0 else 0,
                text=f"{na_linha} de {total_id} pneus bipados",
            )

            # Puxa TODA a coleta do CSV e mostra com situação por pneu
            vis = os_trava.copy()
            vis['Situação'] = vis['STATUS'].map(
                lambda s: '⏳ Falta bipar' if str(s).strip() == 'Aguardando' else '✅ Na linha'
            )
            vis['_ord'] = (vis['STATUS'] != 'Aguardando').astype(int)  # pendentes no topo
            vis = vis.sort_values('_ord')

            if not pendentes.empty:
                st.warning(
                    f"⚠️ **FALTAM {len(pendentes)} PNEUS** para liberar o sistema. "
                    f"Procure as OS marcadas com ⏳:"
                )
            else:
                st.success("🎉 **TODOS OS PNEUS DA COLETA ENTRARAM!** O sistema está liberado.")

            st.dataframe(
                vis[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET', 'Situação']],
                hide_index=True,
                use_container_width=True,
            )

            if pendentes.empty:
                if st.button("🔓 Iniciar Próxima Coleta", type="primary"):
                    set_trava_global(None)
                    st.rerun()
                return
        else:
            st.warning(
                f"⚠️ O IDPEDIDO **{id_travado}** não tem nenhuma OS no banco (CSV do "
                f"Painel PPCP). Importe o CSV ou libere a trava."
            )
            if st.button("🔓 Liberar trava", type="primary"):
                set_trava_global(None)
                st.rerun()
            return
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

        # Validação por cliente: confirma se o IDPEDIDO/nome casou no banco
        transito_list = []
        linhas_valid  = []
        for item in itens:
            os_cliente = _buscar_os(item['idpedido'], item['cliente'], df_banco)
            achou      = (not os_cliente.empty) and ('STATUS' in os_cliente.columns)
            n_total    = len(os_cliente) if achou else 0
            n_aguard   = len(os_cliente[os_cliente['STATUS'] == 'Aguardando']) if achou else 0

            if item.get('idpedido'):
                modo = '🆔 por ID'
            elif achou:
                modo = '🔤 por nome'
            else:
                modo = '—'

            linhas_valid.append({
                'Cliente':   item['cliente'],
                'IDPEDIDO':  item.get('idpedido') or '(vazio)',
                'Qtd Plan.': item['qtd'],
                'No banco':  n_total,
                'Aguard.':   n_aguard,
                'Match':     ('✅ ' + modo) if achou else '❌ não achou',
            })

            if achou and n_aguard > 0:
                transito_list.append(os_cliente[os_cliente['STATUS'] == 'Aguardando'])

        with st.expander(f"🔍 Conferência de clientes — Linha {linha_id}", expanded=False):
            st.dataframe(pd.DataFrame(linhas_valid), hide_index=True, use_container_width=True)
            nao_achou = [l['Cliente'] for l in linhas_valid if l['Match'].startswith('❌')]
            if nao_achou:
                st.caption(f"⚠️ Sem correspondência no banco: {', '.join(nao_achou)} "
                           f"— preencha o IDPEDIDO desses na planilha.")

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


# ── 3. Status por Cliente (conforme a Programação do dia) ────────────────────
def _aba_clientes_em_linha(df_banco: pd.DataFrame):
    st.subheader("🏭 Status por Cliente (conforme Programação)")

    plano = _carregar_plano()
    if not plano:
        st.info(
            "Nenhuma programação carregada. Importe a planilha na aba "
            "**📂 2. Importar & Pneus em Trânsito** para acompanhar o status."
        )
        return

    st.caption(f"📅 Programação de **{plano.get('data', '—')}**")

    tot_prog = tot_aguard = tot_prod = tot_exped = 0

    for linha_id, cfg in _CFG_LINHAS.items():
        itens = plano['linhas'].get(linha_id, [])
        if not itens:
            continue

        linhas = []
        l_prog = l_aguard = l_prod = l_exped = 0
        for item in itens:
            os_cli = _buscar_os(item.get('idpedido', ''), item['cliente'], df_banco)
            prog   = int(item['qtd']) if str(item['qtd']).isdigit() else 0

            if os_cli.empty or 'STATUS' not in os_cli.columns:
                aguard = prod = exped = 0
            else:
                aguard = len(os_cli[os_cli['STATUS'] == 'Aguardando'])
                prod   = len(os_cli[os_cli['STATUS'] == 'Em Produção'])
                exped  = len(os_cli[os_cli['STATUS'] == 'Expedido'])

            no_banco = aguard + prod + exped

            if no_banco == 0:
                situ = '❌ Sem pneus no banco'
            elif aguard == 0 and prod == 0:
                situ = '✅ Concluído (expedido)'
            elif prod > 0 and aguard == 0:
                situ = '🔄 Todos na linha'
            elif prod > 0:
                situ = '🔄 Em produção'
            else:
                situ = '⏳ Aguardando entrada'

            linhas.append({
                'IDPEDIDO':     item.get('idpedido') or '(sem ID)',
                'Cliente':      item['cliente'],
                'Programado':   prog,
                'Aguardando':   aguard,
                'Em Produção':  prod,
                'Expedido':     exped,
                'Situação':     situ,
            })
            l_prog += prog; l_aguard += aguard; l_prod += prod; l_exped += exped

        tot_prog += l_prog; tot_aguard += l_aguard; tot_prod += l_prod; tot_exped += l_exped

        st.markdown(
            f"<div style='background:{cfg['cor']};border-radius:6px;"
            f"padding:8px 16px;margin:14px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>"
            f"{cfg['emoji']} LINHA {linha_id} — {l_prog} programados | "
            f"⏳ {l_aguard} aguard. | 🔄 {l_prod} produção | ✅ {l_exped} exped."
            f"</h4></div>",
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

    # Resumo geral
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Programado", tot_prog)
    c2.metric("⏳ Aguardando", tot_aguard)
    c3.metric("🔄 Em Produção", tot_prod)
    c4.metric("✅ Expedido", tot_exped)
