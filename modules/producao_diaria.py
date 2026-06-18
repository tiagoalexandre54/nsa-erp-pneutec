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
    'B': {'col_id': 10, 'col_cliente': 11, 'col_qtd': 13, 'cor': '#1e8449', 'emoji': '🟢', 'cap_max': 165},
    'C': {'col_id': 19, 'col_cliente': 20, 'col_qtd': 22, 'cor': '#784212', 'emoji': '🟠', 'cap_max': 77},
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


# ── Auto-detecção de layout (resiliente a mudanças na planilha) ──────────────
def _detectar_layout(df: pd.DataFrame):
    """Lê o cabeçalho e descobre as colunas IDPEDIDO/CLIENTE/QTD de cada linha
    (A/B/C), pareando da esquerda p/ direita. Retorna (cfg, linha_ini) ou None
    se não conseguir detectar (aí cai no mapeamento fixo)."""
    try:
        header_row = None
        for r in range(min(12, len(df))):
            valores = [_norm(df.iloc[r, c]) for c in range(df.shape[1])]
            tem_cli = valores.count('CLIENTE') >= 2
            tem_id  = any(v in ('IDPEDIDO', 'ID', 'ID PEDIDO', 'ID_PEDIDO') for v in valores)
            tem_qtd = any(v.startswith('QTD') for v in valores)
            if tem_cli and tem_id and tem_qtd:
                header_row = r
                break
        if header_row is None:
            return None

        valores = [_norm(df.iloc[header_row, c]) for c in range(df.shape[1])]
        cli_cols = [c for c, v in enumerate(valores) if v == 'CLIENTE']
        qtd_cols = [c for c, v in enumerate(valores) if v.startswith('QTD')]
        id_cols  = [c for c, v in enumerate(valores) if v in ('IDPEDIDO', 'ID', 'ID PEDIDO', 'ID_PEDIDO')]
        if not (cli_cols and qtd_cols and id_cols):
            return None
        cli_cols.sort(); qtd_cols.sort(); id_cols.sort()

        linhas = list(_CFG_LINHAS.keys())
        n = min(len(linhas), len(cli_cols), len(qtd_cols), len(id_cols))
        if n == 0:
            return None
        cfg = {}
        for i, lid in enumerate(linhas):
            base = dict(_CFG_LINHAS[lid])
            if i < n:
                base['col_cliente'] = cli_cols[i]
                base['col_qtd']     = qtd_cols[i]
                base['col_id']      = id_cols[i]
            cfg[lid] = base
        return cfg, header_row + 1
    except Exception:
        return None


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

    # Tenta detectar o layout pelo cabeçalho; se falhar, usa o mapa fixo PPCP2.
    detectado = _detectar_layout(df)
    if detectado:
        cfg_linhas, linha_ini = detectado
    else:
        cfg_linhas, linha_ini = _CFG_LINHAS, _LINHA_INI

    for linha_id, cfg in cfg_linhas.items():
        itens = []
        for row_idx in range(linha_ini, min(_LINHA_FIM, len(df))):
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

    if 'prod_bipe_key' not in st.session_state:
        st.session_state.prod_bipe_key = 0

    codigo = None  # preenchido pelo campo de bipagem conforme o estado

    if id_travado:
        os_trava  = df[df['IDPEDIDOPNEU'].astype(str).str.strip() == str(id_travado).strip()]
        pendentes = os_trava[os_trava['STATUS'].isin(['Aguardando', 'Em Limpeza'])]

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
                lambda s: '⏳ Falta bipar' if str(s).strip() in ('Aguardando', 'Em Limpeza') else '✅ Na linha'
            )
            vis['_ord'] = (~vis['STATUS'].isin(['Aguardando', 'Em Limpeza'])).astype(int)  # pendentes no topo
            vis = vis.sort_values('_ord')

            if not pendentes.empty:
                # ─── Campo DEDICADO de bipagem da OS (destaque, acima da lista) ───
                st.markdown(f"### 📷 Bipe a OS do pneu — faltam **{len(pendentes)}**")
                codigo = st.text_input(
                    "Escaneie o código de barras da OS (NRORDEM):",
                    key=f"bipe_{st.session_state.prod_bipe_key}",
                    placeholder="Aguardando leitura do leitor...",
                    label_visibility="collapsed",
                )
                st.caption("Procure as OS marcadas com ⏳ na lista abaixo.")
                st.dataframe(
                    vis[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET', 'Situação']],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.success("🎉 **TODOS OS PNEUS DA COLETA ENTRARAM!** O sistema está liberado.")
                st.dataframe(
                    vis[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET', 'Situação']],
                    hide_index=True,
                    use_container_width=True,
                )
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
        codigo = st.text_input(
            "🔍 Bipe o IDPEDIDO para iniciar a coleta (ou uma OS):",
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
        if status_atual in ('Aguardando', 'Em Limpeza'):
            st.session_state.bd_pneus.at[i, 'STATUS']      = 'Em Produção'
            st.session_state.bd_pneus.at[i, 'DATA_ENTRADA'] = (
                datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )
            salvar_dados(st.session_state.bd_pneus)

            df_up  = st.session_state.bd_pneus
            faltam = len(
                df_up[
                    (df_up['IDPEDIDOPNEU'] == id_do_pneu) &
                    (df_up['STATUS'].isin(['Aguardando', 'Em Limpeza']))
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

    # Bipou um IDPEDIDO (inicia a coleta: reseta para Aguardando + trava)
    elif idx_idpedido:
        if id_travado and id_travado != codigo:
            st.error("🔒 Finalize a coleta atual antes de iniciar um novo IDPEDIDO.")
        elif id_travado == codigo:
            st.info("ℹ️ Esta coleta já está ativa. Bipe as OS dos pneus.")
            st.session_state.prod_bipe_key += 1
            st.rerun()
        else:
            # Inicia a coleta: TODO pneu deste IDPEDIDO volta a "Aguardando"
            # (exceto os já Expedidos), mesmo que o ERP tenha mandado como
            # "Em Produção" — pois aqui o pneu só entra na linha ao ser BIPADO.
            bd = st.session_state.bd_pneus
            mask = (
                (bd['IDPEDIDOPNEU'].astype(str).str.strip() == codigo) &
                (bd['STATUS'] != 'Expedido')
            )
            bd.loc[mask, 'STATUS'] = 'Aguardando'
            salvar_dados(bd)
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
            n_aguard   = len(os_cliente[os_cliente['STATUS'].isin(['Aguardando', 'Em Limpeza'])]) if achou else 0

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
                transito_list.append(os_cliente[os_cliente['STATUS'].isin(['Aguardando', 'Em Limpeza'])])

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


# ── Roteirização semanal ──────────────────────────────────────────────────────
_DIA_WEEKDAY = {'SEGUNDA': 0, 'TERCA': 1, 'QUARTA': 2, 'QUINTA': 3, 'SEXTA': 4}
_DIA_LABEL   = {'SEGUNDA': 'Segunda', 'TERCA': 'Terça', 'QUARTA': 'Quarta',
                 'QUINTA': 'Quinta',  'SEXTA': 'Sexta'}


def _carregar_roteirizacao() -> dict | None:
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64 as _b64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/roteirizacao.json?ref={branch}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                return json.loads(_b64.b64decode(r.json()["content"]).decode("utf-8"))
    except Exception:
        pass
    p = _BASE_DIR / "data" / "roteirizacao.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _mapa_rotei(rotei: dict) -> dict:
    """norm(cliente) → lista de {dia, prazo_dias, prazo_str, motorista}"""
    mapa: dict[str, list] = {}
    for motorista, dias in rotei.get('motoristas', {}).items():
        for dia, itens in dias.items():
            if dia not in _DIA_WEEKDAY:
                continue
            for item in itens:
                cli = (item.get('cliente') or '').strip()
                if not cli:
                    continue
                prazo_str = (item.get('prazo') or '').strip()
                dias_num: int | None = None
                m = re.search(r'(\d+)\s*DIA', prazo_str.upper())
                if m:
                    dias_num = int(m.group(1))
                chave = _norm(cli)
                if chave not in mapa:
                    mapa[chave] = []
                mapa[chave].append({
                    'dia': dia, 'prazo_dias': dias_num,
                    'prazo_str': prazo_str or '—', 'motorista': motorista,
                })
    return mapa


def _proxima_data_dia(dia: str, hoje: datetime.date) -> datetime.date | None:
    alvo = _DIA_WEEKDAY.get(dia)
    if alvo is None:
        return None
    delta = (alvo - hoje.weekday()) % 7 or 7  # mesmo dia = próxima semana
    return hoje + datetime.timedelta(days=delta)


def _match_nome(k_norm: str, cli_norm: str) -> bool:
    """Todas as palavras de k_norm devem aparecer como palavra inteira em cli_norm."""
    return all(re.search(r'\b' + re.escape(p) + r'\b', cli_norm) for p in k_norm.split())


# ── 3. Fila de Produção PPCP ──────────────────────────────────────────────────
def _aba_clientes_em_linha(df_banco: pd.DataFrame):
    st.subheader("🏭 Fila de Produção — OS em Aberto por Cliente")

    itin  = None
    rotei = None
    try:
        from modules.itinerario import _carregar_itinerario
        raw = _carregar_itinerario()
        if raw and raw.get('paradas'):
            itin = raw
    except Exception:
        pass

    try:
        raw_rotei = _carregar_roteirizacao()
        if raw_rotei:
            rotei = _mapa_rotei(raw_rotei)
    except Exception:
        pass

    plano = _carregar_plano()

    if plano:
        fonte = st.radio(
            "Modo de visualização:",
            ["🏭 Fila de Produção (automático)", "📂 Planilha PPCP (manual)"],
            horizontal=True,
        )
        if fonte.startswith("📂"):
            _status_por_plano_ppcp(plano, df_banco)
            return

    _status_por_itinerario(itin, rotei, df_banco)


def _parse_data(s: str) -> datetime.date | None:
    """Converte string de data (dd/mm/yyyy ou variantes) para date. Retorna None se falhar."""
    try:
        dt = pd.to_datetime(str(s).strip(), dayfirst=True, errors='coerce')
        return dt.date() if pd.notna(dt) else None
    except Exception:
        return None


def _status_por_itinerario(itin: dict | None, rotei: dict | None, df_banco: pd.DataFrame):
    """
    Fila de produção PPCP completa:
    1. Clientes no itinerário de hoje  → prazo calculado por DATA_COLETA + prazo
    2. Clientes na roteirização semanal → prazo calculado por PRÓXIMA_VISITA - prazo
    3. Clientes sem cadastro            → "Sem prazo"

    Ordens: Atrasado (0) → Produzir Hoje (1) → Dentro do Prazo (2) →
            Programado/futuro (3, por data) → Sem prazo (4)
    """
    hoje = datetime.date.today()

    df_aberto    = df_banco[df_banco['STATUS'].isin(['Aguardando', 'Em Limpeza'])].copy()
    total_aberto = len(df_aberto)
    ja_em_linha  = len(df_banco[df_banco['STATUS'] == 'Em Produção'])
    expedidos    = len(df_banco[df_banco['STATUS'] == 'Expedido'])

    # ── Mapa de prazo do itinerário de HOJE ──────────────────────────────────
    mapa_prazo: dict[str, dict] = {}
    data_itin_str = '—'
    if itin and itin.get('paradas'):
        data_itin_str = itin.get('data', '—')
        for p in itin.get('paradas', []):
            cli_itin  = (p.get('cliente')  or '').strip()
            prazo_str = (p.get('prazo')    or '').strip()
            motorista = (p.get('motorista') or '').strip()
            if not cli_itin:
                continue
            dias: int | None = None
            m = re.search(r'(\d+)\s*DIA', prazo_str.upper())
            if m:
                dias = int(m.group(1))
            chave = _norm(cli_itin)
            if chave:
                mapa_prazo[chave] = {
                    'prazo_dias': dias, 'prazo_str': prazo_str or '—',
                    'motorista': motorista or '—', 'fonte': 'hoje',
                    'proxima_visita': None, 'dia_semana': '—',
                }

    # ── Caption ───────────────────────────────────────────────────────────────
    partes = []
    if itin:
        partes.append(f"📅 Itinerário de **{data_itin_str}**")
    partes.append(f"**{total_aberto}** OS aguardando | 🔄 {ja_em_linha} na linha | ✅ {expedidos} expedidos")
    st.caption(" | ".join(partes))

    if df_aberto.empty:
        st.success("🎉 Nenhuma OS em aberto!")
        return

    # ── Monta a fila ─────────────────────────────────────────────────────────
    linhas = []

    for cli_full in df_aberto['CLIENTE'].dropna().unique():
        os_cli = df_aberto[df_aberto['CLIENTE'] == cli_full]
        qtd    = len(os_cli)

        ids_raw     = os_cli['IDPEDIDOPNEU'].dropna().apply(_norm_id).unique().tolist()
        idpedidos   = ' / '.join(x for x in ids_raw if x not in ('', 'nan', '0')) or '—'

        datas_validas = [_parse_data(d) for d in os_cli['DATA_ENTRADA'].dropna()
                         if str(d).strip() not in ('', 'nan')]
        datas_validas = [d for d in datas_validas if d is not None]
        data_coleta_obj = min(datas_validas) if datas_validas else None
        data_coleta_str = data_coleta_obj.strftime('%d/%m/%Y') if data_coleta_obj else '—'

        cli_norm = _norm(cli_full)

        # 1) Tenta itinerário de hoje
        prazo_info: dict | None = None
        for k_norm, v in mapa_prazo.items():
            if _match_nome(k_norm, cli_norm):
                prazo_info = v
                break

        # 2) Fallback: roteirização semanal
        if prazo_info is None and rotei:
            for k_norm, visitas in rotei.items():
                if not _match_nome(k_norm, cli_norm):
                    continue
                # Encontrou na roteirização — pega a próxima visita mais cedo
                melhor: tuple | None = None
                for v in visitas:
                    nd = _proxima_data_dia(v['dia'], hoje)
                    if nd and (melhor is None or nd < melhor[0]):
                        melhor = (nd, v['prazo_dias'], v['prazo_str'], v['motorista'], v['dia'])
                if melhor:
                    prox_visit, prazo_dias_r, prazo_str_r, mot_r, dia_r = melhor
                    prazo_info = {
                        'prazo_dias':     prazo_dias_r,
                        'prazo_str':      prazo_str_r,
                        'motorista':      mot_r,
                        'fonte':          'rotei',
                        'proxima_visita': prox_visit,
                        'dia_semana':     _DIA_LABEL.get(dia_r, dia_r),
                    }
                break

        # ── Calcula datas e status ────────────────────────────────────────────
        prazo_dias = prazo_info['prazo_dias']     if prazo_info else None
        prazo_str  = prazo_info['prazo_str']      if prazo_info else '—'
        motorista  = prazo_info['motorista']      if prazo_info else '—'
        fonte      = prazo_info.get('fonte', '')  if prazo_info else ''
        prox_visit = prazo_info.get('proxima_visita') if prazo_info else None
        dia_semana = prazo_info.get('dia_semana', '—') if prazo_info else '—'

        if fonte == 'hoje':
            # Prazo relativo à data de coleta
            data_prod_obj = (data_coleta_obj + datetime.timedelta(days=prazo_dias)
                             if data_coleta_obj and prazo_dias is not None else None)
        elif fonte == 'rotei' and prazo_dias is not None and prox_visit:
            # Prazo relativo à próxima visita: precisa estar pronto N dias antes
            data_prod_obj = prox_visit - datetime.timedelta(days=prazo_dias)
        else:
            data_prod_obj = None

        data_prod_str = data_prod_obj.strftime('%d/%m/%Y') if data_prod_obj else '—'
        prox_visit_str = prox_visit.strftime('%d/%m/%Y') if prox_visit else '—'

        # Status e ordenação
        if data_prod_obj is not None:
            dias_restantes = (data_prod_obj - hoje).days
            if dias_restantes < 0:
                status_ppcp   = 'Fifo – Atrasado'
                entrada_linha = 'Até 09:00'
                ord_status    = 0
            elif dias_restantes == 0:
                status_ppcp   = 'Produzir Hoje'
                entrada_linha = 'Até 09:00'
                ord_status    = 1
            else:
                if fonte == 'hoje':
                    status_ppcp   = 'Dentro do Prazo'
                    entrada_linha = 'Até 13:00'
                    ord_status    = 2
                else:
                    status_ppcp   = f'Coleta: {dia_semana} ({prox_visit_str})'
                    entrada_linha = f'Até {data_prod_str}'
                    ord_status    = 3
        elif prazo_info and prox_visit:
            # Tem visita mas sem prazo definido
            status_ppcp   = f'Coleta: {dia_semana} ({prox_visit_str})'
            entrada_linha = '—'
            ord_status    = 3
        else:
            status_ppcp   = 'Sem prazo'
            entrada_linha = '—'
            ord_status    = 4

        ord_coleta = data_coleta_obj if data_coleta_obj else datetime.date.max

        # Para "Programado" ordena por data de produção (mais urgente primeiro)
        ord_prod = data_prod_obj if data_prod_obj else (prox_visit or datetime.date.max)

        linhas.append({
            '_ord_status': ord_status,
            '_ord_coleta': ord_coleta,
            '_ord_prod':   ord_prod,
            'status_ppcp': status_ppcp,
            'cli_full':    cli_full,
            'idpedidos':   idpedidos,
            'qtd':         qtd,
            'data_coleta': data_coleta_str,
            'prazo_str':   prazo_str,
            'data_prod':   data_prod_str,
            'proxima_coleta': prox_visit_str if fonte == 'rotei' else '—',
            'entrada_linha': entrada_linha,
            'motorista':     motorista,
        })

    # ── Ordena e numera ───────────────────────────────────────────────────────
    df_lin = (
        pd.DataFrame(linhas)
        .sort_values(['_ord_status', '_ord_prod', '_ord_coleta', 'cli_full'])
        .reset_index(drop=True)
    )
    df_lin.insert(0, 'Fila', range(1, len(df_lin) + 1))

    # ── Métricas ──────────────────────────────────────────────────────────────
    n_atrasado  = (df_lin['_ord_status'] == 0).sum()
    n_hoje      = (df_lin['_ord_status'] == 1).sum()
    n_prazo     = (df_lin['_ord_status'] == 2).sum()
    n_prog      = (df_lin['_ord_status'] == 3).sum()
    n_sem_pz    = (df_lin['_ord_status'] == 4).sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("⏳ OS em Aberto",      total_aberto)
    c2.metric("🔴 Fifo – Atrasado",   int(n_atrasado),  help="Prazo venceu — entrar até 09:00")
    c3.metric("🟠 Produzir Hoje",      int(n_hoje),      help="Deadline hoje — entrar até 09:00")
    c4.metric("🟢 Dentro do Prazo",   int(n_prazo),     help="Coleta hoje, prazo OK")
    c5.metric("📅 Programado",         int(n_prog),      help="Coleta em dia futuro — alerta antecipado")

    if n_sem_pz:
        st.caption(f"⚪ {int(n_sem_pz)} cliente(s) sem cadastro no itinerário nem na roteirização")

    # ── Tabela ────────────────────────────────────────────────────────────────
    df_exibir = df_lin.rename(columns={
        'status_ppcp':     'Status',
        'cli_full':        'Cliente',
        'idpedidos':       'IDPEDIDO',
        'qtd':             'Qtd.',
        'data_coleta':     'Data Coleta',
        'prazo_str':       'Prazo',
        'data_prod':       'Prod. até',
        'proxima_coleta':  'Próx. Coleta',
        'entrada_linha':   'Entrada na Linha',
        'motorista':       'Motorista',
    })[['Fila', 'Status', 'Cliente', 'IDPEDIDO', 'Qtd.',
        'Data Coleta', 'Prazo', 'Prod. até', 'Próx. Coleta',
        'Entrada na Linha', 'Motorista']]

    st.dataframe(
        df_exibir.style.apply(_colorir_fila_ppcp, axis=1),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("---")
    st.caption(f"**{len(df_lin)} clientes** na fila | **{total_aberto} pneus** aguardando produção")


def _colorir_fila_ppcp(row: pd.Series) -> list[str]:
    status = str(row.get('Status', ''))
    if 'Atrasado' in status:
        return ['background-color:#fdecea;color:#8b0000'] * len(row)
    if 'Produzir Hoje' in status:
        return ['background-color:#fff3e0;color:#e65100'] * len(row)
    if 'Dentro do Prazo' in status:
        return ['background-color:#e8f5e9;color:#1b5e20'] * len(row)
    if 'Coleta:' in status:
        return ['background-color:#e8eaf6;color:#1a237e'] * len(row)
    return [''] * len(row)


def _status_por_plano_ppcp(plano: dict, df_banco: pd.DataFrame):
    """Plano de produção lido da planilha PPCP importada manualmente."""

    st.caption(f"📅 Programação de **{plano.get('data', '—')}**")

    # Carrega prioridade do itinerário (opcional — enriquece a coluna Parada)
    try:
        from modules.itinerario import carregar_mapa_prioridade
        mapa_parada = carregar_mapa_prioridade()
    except Exception:
        mapa_parada = {}

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
                aguard = len(os_cli[os_cli['STATUS'].isin(['Aguardando', 'Em Limpeza'])])
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

            parada_itin = mapa_parada.get(item['cliente'], '')
            linhas.append({
                'Parada 🗺️':    parada_itin or '—',
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

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Programado", tot_prog)
    c2.metric("⏳ Aguardando", tot_aguard)
    c3.metric("🔄 Em Produção", tot_prod)
    c4.metric("✅ Expedido", tot_exped)
