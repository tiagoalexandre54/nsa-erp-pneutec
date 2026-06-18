"""
Tela — Itinerário de Entrega e Coleta.
Roteirização do caminhão integrada ao PPCP.

Fluxo:
  1. Importar ROTEIRIZAÇÃO.xlsx (uma aba por motorista, colunas por dia da semana)
  2. Gerar Plano do Dia — seleciona data, cruza com banco de OS, salva itinerário
  3. Editar itinerário manualmente (ajustes pontuais)
  4. Painel do Dia — acompanha status de produção por parada em tempo real
"""
import streamlit as st
import pandas as pd
import datetime
import json
import re
import unicodedata
from pathlib import Path

_BASE_DIR     = Path(__file__).resolve().parent.parent
_ITIN_JSON    = _BASE_DIR / "data" / "itinerario.json"
_ROTEI_JSON   = _BASE_DIR / "data" / "roteirizacao.json"
_SCHEMA_ITIN  = 1
_SCHEMA_ROTEI = 1

# ── Dias da semana ────────────────────────────────────────────────────────────
_DIAS_PT = {0: 'SEGUNDA', 1: 'TERCA', 2: 'QUARTA', 3: 'QUINTA', 4: 'SEXTA'}
_DIAS_LABEL = {
    'SEGUNDA':     'Segunda-Feira',
    'TERCA':       'Terça-Feira',
    'QUARTA':      'Quarta-Feira',
    'QUINTA':      'Quinta-Feira',
    'SEXTA':       'Sexta-Feira',
    'ESPORADICO':  'Esporádico',
    'ESPORADICO2': 'Esporádico 2',
}

# Mapeamento cabeçalho normalizado → chave padrão.
# Inclui variações por leitura Excel com chars especiais garbled (ex.: EXPORADICO).
_HEADER_MAP = {
    'SEGUNDA FEIRA':  'SEGUNDA',
    'SEGUNDA':        'SEGUNDA',
    'TERCA FEIRA':    'TERCA',
    'TERCA-FEIRA':    'TERCA',
    'TERCA':          'TERCA',
    'QUARTA FEIRA':   'QUARTA',
    'QUARTA':         'QUARTA',
    'QUINTA FEIRA':   'QUINTA',
    'QUINTA':         'QUINTA',
    'SEXTA FEIRA':    'SEXTA',
    'SEXTA':          'SEXTA',
    'ESPORADICO2':    'ESPORADICO2',
    'EXPORADICO2':    'ESPORADICO2',   # garbled (X no lugar de S)
    'ESPORADICO':     'ESPORADICO',
    'EXPORADICO':     'ESPORADICO',    # garbled (X no lugar de S)
}


# ── Utilitários de normalização ───────────────────────────────────────────────

def _norm(s: str) -> str:
    """Remove acentos, caixa alta, espaços extras."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s).upper().strip()


def _norm_header(h: str) -> str:
    """Normaliza cabeçalho da planilha: remove parênteses adicionais e normaliza."""
    h = _norm(h)
    h = re.sub(r'\s*\(.*?\)', '', h).strip()   # Remove "(BAIXADA)", "(BAIXO)", etc.
    return h


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _salvar_github(caminho_rel: str, conteudo: str, msg: str) -> None:
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return
        import requests, base64
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/{caminho_rel}"
        headers = {'Authorization': f'token {token}'}
        b64 = base64.b64encode(conteudo.encode('utf-8')).decode()
        r = requests.get(url, headers=headers, timeout=5)
        sha = r.json().get('sha') if r.status_code == 200 else None
        payload = {'message': msg, 'content': b64, 'branch': branch}
        if sha:
            payload['sha'] = sha
        requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


def _carregar_github(caminho_rel: str) -> str | None:
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return None
        import requests, base64
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/{caminho_rel}?ref={branch}"
        r = requests.get(url, headers={'Authorization': f'token {token}'}, timeout=5)
        if r.status_code == 200:
            return base64.b64decode(r.json()['content']).decode('utf-8')
    except Exception:
        pass
    return None


def _excluir_github(caminho_rel: str, msg: str) -> None:
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return
        import requests
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/{caminho_rel}"
        headers = {'Authorization': f'token {token}'}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            sha = r.json().get('sha')
            requests.delete(
                url,
                json={'message': msg, 'sha': sha, 'branch': branch},
                headers=headers, timeout=10
            )
    except Exception:
        pass


# ── Itinerário do dia (editável) ──────────────────────────────────────────────

def _itin_valido(it: dict) -> bool:
    return (isinstance(it, dict)
            and it.get('_schema') == _SCHEMA_ITIN
            and 'paradas' in it
            and isinstance(it['paradas'], list))


def _salvar_itinerario(it: dict) -> None:
    it = dict(it)
    it['_schema'] = _SCHEMA_ITIN
    s = json.dumps(it, ensure_ascii=False, indent=2)
    try:
        _ITIN_JSON.parent.mkdir(parents=True, exist_ok=True)
        _ITIN_JSON.write_text(s, encoding='utf-8')
    except Exception:
        pass
    _salvar_github('data/itinerario.json', s, 'Atualiza itinerario')


def _carregar_itinerario() -> dict | None:
    s = _carregar_github('data/itinerario.json')
    if s:
        try:
            it = json.loads(s)
            if _itin_valido(it):
                return it
        except Exception:
            pass
    if _ITIN_JSON.exists():
        try:
            it = json.loads(_ITIN_JSON.read_text(encoding='utf-8'))
            if _itin_valido(it):
                return it
        except Exception:
            pass
    return None


def carregar_mapa_prioridade() -> dict:
    """Retorna {nome_cliente: ordem_parada}. Usado por producao_diaria."""
    it = _carregar_itinerario()
    if not it:
        return {}
    return {p['cliente']: i + 1 for i, p in enumerate(it.get('paradas', []))}


# ── Roteirização (matriz semanal permanente) ──────────────────────────────────

def _rotei_valido(r: dict) -> bool:
    return (isinstance(r, dict)
            and r.get('_schema') == _SCHEMA_ROTEI
            and 'motoristas' in r
            and isinstance(r['motoristas'], dict))


def _salvar_roteirizacao(rotei: dict) -> None:
    rotei = dict(rotei)
    rotei['_schema'] = _SCHEMA_ROTEI
    s = json.dumps(rotei, ensure_ascii=False, indent=2)
    try:
        _ROTEI_JSON.parent.mkdir(parents=True, exist_ok=True)
        _ROTEI_JSON.write_text(s, encoding='utf-8')
    except Exception:
        pass
    _salvar_github('data/roteirizacao.json', s, 'Atualiza roteirizacao')


def _carregar_roteirizacao() -> dict | None:
    s = _carregar_github('data/roteirizacao.json')
    if s:
        try:
            r = json.loads(s)
            if _rotei_valido(r):
                return r
        except Exception:
            pass
    if _ROTEI_JSON.exists():
        try:
            r = json.loads(_ROTEI_JSON.read_text(encoding='utf-8'))
            if _rotei_valido(r):
                return r
        except Exception:
            pass
    return None


def _ler_planilha_roteirizacao(arquivo) -> dict:
    """
    Lê a planilha de roteirização (uma aba por motorista).
    Formato esperado: linha 0 = cabeçalhos (dia | PRAZO | dia | PRAZO ...),
    linhas 1+ = clientes.
    Retorna: {'motoristas': {nome: {dia_key: [{cliente, prazo}]}}}
    """
    xl = pd.ExcelFile(arquivo)
    motoristas = {}

    for aba in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=aba, header=None, dtype=str).fillna('')
        if df.empty or df.shape[0] < 2:
            continue

        nome_motorista = str(aba).strip()

        # ── Detecta colunas pelo cabeçalho (linha 0) ────────────────────────
        header = [str(df.iloc[0, c]) for c in range(df.shape[1])]
        col_map = {}   # dia_key -> col_index (de cliente)

        for c, h in enumerate(header):
            h_norm = _norm_header(h)
            for k, v in _HEADER_MAP.items():
                if _norm(k) == h_norm:
                    # Só registra a primeira ocorrência de cada chave
                    if v not in col_map:
                        col_map[v] = c
                    break

        # ── Extrai clientes por coluna/dia ───────────────────────────────────
        dias_data = {}
        for dia_key, col_idx in col_map.items():
            # Coluna de prazo = coluna imediatamente à direita do cliente
            prazo_col = col_idx + 1 if col_idx + 1 < df.shape[1] else None
            clientes  = []

            for r in range(1, df.shape[0]):
                cliente = str(df.iloc[r, col_idx]).strip()
                if not cliente or cliente.lower() == 'nan':
                    continue

                c_up = cliente.upper()
                # Pula linhas de rodapé / anotações
                if any(p in c_up for p in ('PNEUS A QUENTE', 'QUENTE', 'PRAZO', 'DIAS')):
                    continue
                if _norm(cliente) == _norm(nome_motorista):
                    continue

                prazo = ''
                if prazo_col is not None:
                    prazo = str(df.iloc[r, prazo_col]).strip()
                    if prazo.lower() in ('nan', ''):
                        prazo = ''

                clientes.append({'cliente': cliente, 'prazo': prazo})

            if clientes:
                dias_data[dia_key] = clientes

        if dias_data:
            motoristas[nome_motorista] = dias_data

    return {'motoristas': motoristas}


def _gerar_paradas_dia(rotei: dict, data: datetime.date) -> list:
    """
    Retorna lista de paradas para o dia da semana da data fornecida.
    [{motorista, cliente, prazo}]
    """
    dia_key = _DIAS_PT.get(data.weekday(), '')
    if not dia_key:
        return []   # Fim de semana: sem rota fixa

    paradas = []
    for motorista, dias in rotei.get('motoristas', {}).items():
        for item in dias.get(dia_key, []):
            paradas.append({
                'motorista': motorista,
                'cliente':   item['cliente'],
                'prazo':     item.get('prazo', ''),
            })
    return paradas


def _buscar_cli_banco(nome_plan: str, df_banco: pd.DataFrame) -> pd.DataFrame:
    """Busca cliente no banco por nome normalizado (exato ou palavra-inteira)."""
    alvo = _norm(nome_plan)
    if not alvo:
        return pd.DataFrame()

    nomes = df_banco['CLIENTE'].apply(_norm)

    # 1. Match exato
    res = df_banco[nomes == alvo]
    if not res.empty:
        return res

    # 2. Nome da planilha como palavra inteira no banco
    if len(alvo) >= 3:
        padrao = r'\b' + re.escape(alvo) + r'\b'
        res = df_banco[nomes.str.contains(padrao, regex=True, na=False)]
        if not res.empty:
            return res

    # 3. Qualquer palavra longa do nome como palavra inteira
    for palavra in alvo.split():
        if len(palavra) >= 4:
            padrao = r'\b' + re.escape(palavra) + r'\b'
            res = df_banco[nomes.str.contains(padrao, regex=True, na=False)]
            if not res.empty:
                return res

    return pd.DataFrame()


# ── Tela principal ────────────────────────────────────────────────────────────

def tela_itinerario():
    st.title("🗺️ Itinerário de Entrega e Coleta")

    aba1, aba2, aba3, aba4 = st.tabs([
        "📥 Importar Roteirização",
        "📅 Gerar Plano do Dia",
        "📋 Editar Itinerário Manual",
        "📊 Painel do Dia",
    ])

    with aba1:
        _aba_importar_roteirizacao()
    with aba2:
        _aba_gerar_plano()
    with aba3:
        _aba_editar()
    with aba4:
        _aba_painel()


# ── Aba 1: Importar Roteirização ──────────────────────────────────────────────

def _aba_importar_roteirizacao():
    st.subheader("Importar Planilha de Roteirização")
    st.caption(
        "Faça upload da planilha **ROTEIRIZAÇÃO.xlsx**. "
        "Cada aba deve ser o nome do motorista. "
        "Colunas esperadas: Segunda-Feira | Prazo | Terça-Feira | Prazo | ... "
        "(incluindo Esporádico para clientes sem dia fixo)."
    )

    rotei_atual = _carregar_roteirizacao()

    # ── Exibe roteirização já salva ───────────────────────────────────────────
    if rotei_atual:
        motoristas = list(rotei_atual['motoristas'].keys())
        tot_clientes = sum(
            len(v) for dias in rotei_atual['motoristas'].values()
            for v in dias.values()
        )
        st.success(
            f"✅ Roteirização ativa: **{len(motoristas)} motorista(s)** | "
            f"**{tot_clientes} entradas** de clientes cadastradas"
        )
        st.markdown(f"**Motoristas:** {' · '.join(motoristas)}")

        with st.expander("📋 Ver resumo completo por motorista", expanded=False):
            for mot, dias in rotei_atual['motoristas'].items():
                tot = sum(len(v) for v in dias.values())
                st.markdown(
                    f"<div style='background:#1a5276;border-radius:5px;"
                    f"padding:5px 12px;margin:8px 0 3px;'>"
                    f"<b style='color:#fff;'>🚛 {mot} — {tot} cliente(s)</b>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                linhas = []
                for dia, clientes in dias.items():
                    lista = ', '.join(c['cliente'] for c in clientes[:6])
                    if len(clientes) > 6:
                        lista += f' ... +{len(clientes) - 6}'
                    linhas.append({
                        'Dia':       _DIAS_LABEL.get(dia, dia),
                        'Qtd':       len(clientes),
                        'Clientes':  lista,
                    })
                st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

        st.markdown("---")

    # ── Upload ────────────────────────────────────────────────────────────────
    arquivo = st.file_uploader(
        "📂 Selecione a planilha de Roteirização (.xlsx / .xls):",
        type=["xlsx", "xls"],
        key="uploader_roteirizacao",
    )

    if arquivo:
        try:
            with st.spinner("Lendo planilha..."):
                rotei_nova = _ler_planilha_roteirizacao(arquivo)

            motoristas = list(rotei_nova['motoristas'].keys())
            tot = sum(
                len(v) for dias in rotei_nova['motoristas'].values()
                for v in dias.values()
            )

            st.success(
                f"✅ Planilha lida! **{len(motoristas)} motoristas** detectados, "
                f"**{tot} entradas** de clientes."
            )

            # Prévia detalhada
            st.subheader("Prévia:")
            for mot, dias in rotei_nova['motoristas'].items():
                with st.expander(
                    f"🚛 {mot} — {sum(len(v) for v in dias.values())} clientes",
                    expanded=False,
                ):
                    for dia, clientes in dias.items():
                        st.markdown(
                            f"**{_DIAS_LABEL.get(dia, dia)} ({len(clientes)}):** "
                            + ' · '.join(c['cliente'] for c in clientes)
                        )

            if st.button("💾 Salvar Roteirização no Sistema", type="primary"):
                with st.spinner("Salvando..."):
                    _salvar_roteirizacao(rotei_nova)
                st.success(
                    f"✅ Roteirização salva! {len(motoristas)} motoristas, {tot} entradas. "
                    f"Use a aba **📅 Gerar Plano do Dia** para gerar o roteiro de qualquer data."
                )
                st.rerun()

        except Exception as e:
            st.error(f"❌ Erro ao ler planilha: {e}")

    # ── Remover ───────────────────────────────────────────────────────────────
    if rotei_atual:
        st.markdown("---")
        if st.button("🗑️ Remover roteirização salva"):
            try:
                _ROTEI_JSON.unlink(missing_ok=True)
            except Exception:
                pass
            _excluir_github('data/roteirizacao.json', 'Remove roteirizacao')
            st.success("Roteirização removida.")
            st.rerun()


# ── Aba 2: Gerar Plano do Dia ─────────────────────────────────────────────────

def _aba_gerar_plano():
    st.subheader("Gerar Plano do Dia a partir da Roteirização")

    rotei = _carregar_roteirizacao()
    if not rotei:
        st.warning(
            "Nenhuma roteirização importada. "
            "Faça upload na aba **📥 Importar Roteirização**."
        )
        return

    df_banco = st.session_state.bd_pneus

    # ── Seleção de data ───────────────────────────────────────────────────────
    col_d, col_info = st.columns([2, 3])
    data_sel   = col_d.date_input("Data do plano:", value=datetime.date.today(), key='plano_data')
    dia_semana = data_sel.weekday()
    dia_key    = _DIAS_PT.get(dia_semana, '')
    dia_label  = _DIAS_LABEL.get(dia_key, 'Fim de Semana')

    col_info.markdown(f"**Dia:** {dia_label}  \n**Data:** {data_sel.strftime('%d/%m/%Y')}")

    if not dia_key:
        st.info(
            "Não há rota fixa para fim de semana. "
            "Use a aba **📋 Editar Itinerário Manual** para criar um roteiro avulso "
            "ou selecione os clientes esporádicos abaixo."
        )
        _exibir_esporadicos(rotei, df_banco, data_sel)
        return

    paradas = _gerar_paradas_dia(rotei, data_sel)
    if not paradas:
        st.info(f"Nenhum cliente cadastrado para {dia_label} na roteirização.")
        _exibir_esporadicos(rotei, df_banco, data_sel)
        return

    # ── Agrupa por motorista ──────────────────────────────────────────────────
    por_motorista: dict[str, list] = {}
    for p in paradas:
        por_motorista.setdefault(p['motorista'], []).append(p)

    resumo_geral    = []
    paradas_itin    = []
    cores_motorista = ['#1a5276', '#1e8449', '#784212', '#6c3483',
                       '#117a65', '#b7950b', '#922b21', '#17202a', '#0e6655']

    for idx_mot, (motorista, clientes) in enumerate(por_motorista.items()):
        cor = cores_motorista[idx_mot % len(cores_motorista)]
        st.markdown(
            f"<div style='background:{cor};border-radius:6px;"
            f"padding:8px 16px;margin:14px 0 4px;'>"
            f"<h4 style='color:#fff;margin:0;'>🚛 {motorista} — {len(clientes)} cliente(s)</h4>"
            f"</div>",
            unsafe_allow_html=True,
        )

        linhas = []
        for item in clientes:
            cli   = item['cliente']
            prazo = item.get('prazo', '')

            os_cli = _buscar_cli_banco(cli, df_banco)
            if os_cli.empty or 'STATUS' not in os_cli.columns:
                aguard = prod = exped = total = 0
                situacao = '❌ Sem OS no banco'
                pct      = 0
            else:
                aguard = len(os_cli[os_cli['STATUS'].isin(['Aguardando', 'Em Limpeza'])])
                prod   = len(os_cli[os_cli['STATUS'] == 'Em Produção'])
                exped  = len(os_cli[os_cli['STATUS'] == 'Expedido'])
                total  = aguard + prod + exped
                pct    = round((prod + exped) / total * 100) if total > 0 else 0
                if pct == 100:
                    situacao = '✅ Pronto'
                elif prod > 0 and aguard == 0:
                    situacao = '🔄 Todos na linha'
                elif prod > 0:
                    situacao = '🔄 Em produção'
                else:
                    situacao = '⏳ Aguardando'

            linha = {
                'Cliente':   cli,
                'Prazo':     prazo or '—',
                'Aguard.':   aguard,
                'Em Prod.':  prod,
                'Expedido':  exped,
                '% Pronto':  f"{pct}%",
                'Situação':  situacao,
            }
            linhas.append(linha)
            resumo_geral.append({**linha, 'Motorista': motorista})

            obs = f"Motorista: {motorista}"
            if prazo:
                obs += f" | Prazo: {prazo}"
            paradas_itin.append({
                'cliente':   cli,
                'tipo':      'Entrega e Coleta',
                'hora':      '',
                'obs':       obs,
                'motorista': motorista,
                'prazo':     prazo,
            })

        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

    # ── Resumo geral ──────────────────────────────────────────────────────────
    tot_aguard = sum(r['Aguard.']  for r in resumo_geral)
    tot_prod   = sum(r['Em Prod.'] for r in resumo_geral)
    tot_exped  = sum(r['Expedido'] for r in resumo_geral)
    tot_sem_os = sum(1 for r in resumo_geral if r['Situação'].startswith('❌'))

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⏳ Aguardando",          tot_aguard)
    c2.metric("🔄 Em Produção",          tot_prod)
    c3.metric("✅ Expedido",             tot_exped)
    c4.metric("❌ Sem OS no banco",      tot_sem_os)

    if tot_sem_os > 0:
        sem_os = [r['Cliente'] for r in resumo_geral if r['Situação'].startswith('❌')]
        st.caption(
            f"⚠️ Clientes sem OS no banco (verifique o CSV importado): "
            f"{', '.join(sem_os)}"
        )

    # ── Esporádicos ───────────────────────────────────────────────────────────
    _exibir_esporadicos(rotei, df_banco, data_sel)

    # ── Salvar como itinerário ────────────────────────────────────────────────
    st.markdown("---")
    col_s, col_txt = st.columns([1, 2])
    col_txt.caption(
        f"Salva o itinerário de **{data_sel.strftime('%d/%m/%Y')}** com as "
        f"**{len(paradas_itin)} paradas** acima (ordenadas por motorista). "
        f"Depois edite a ordem na aba **📋 Editar Itinerário Manual** se necessário."
    )
    if col_s.button("📋 Salvar como Itinerário do Dia", type="primary", key="btn_salvar_plano"):
        motorista_str = ' / '.join(por_motorista.keys()) if len(por_motorista) > 1 else list(por_motorista.keys())[0]
        it = {
            'data':      data_sel.strftime('%d/%m/%Y'),
            'motorista': motorista_str,
            'veiculo':   '',
            'paradas':   paradas_itin,
        }
        _salvar_itinerario(it)
        st.session_state.itin_paradas = list(paradas_itin)
        st.success(
            f"✅ Itinerário de {dia_label} salvo com {len(paradas_itin)} paradas! "
            f"Acesse **📊 Painel do Dia** para acompanhar em tempo real."
        )


def _exibir_esporadicos(rotei: dict, df_banco: pd.DataFrame, data_sel: datetime.date):
    """Exibe clientes esporádicos disponíveis para adicionar ao roteiro."""
    espo: list[dict] = []
    for mot, dias in rotei['motoristas'].items():
        for dia_k in ('ESPORADICO', 'ESPORADICO2'):
            for item in dias.get(dia_k, []):
                os_cli = _buscar_cli_banco(item['cliente'], df_banco)
                total  = len(os_cli) if not os_cli.empty else 0
                aguard = len(os_cli[os_cli['STATUS'].isin(['Aguardando', 'Em Limpeza'])]) if total else 0
                espo.append({
                    'Motorista': mot,
                    'Cliente':   item['cliente'],
                    'Prazo':     item.get('prazo', '') or '—',
                    'OS no banco': total,
                    'Aguardando':  aguard,
                })

    if not espo:
        return

    st.markdown("---")
    with st.expander(f"📦 {len(espo)} cliente(s) Esporádico(s) disponíveis", expanded=False):
        st.caption(
            "Clientes sem dia fixo. Eles NÃO são incluídos automaticamente no plano — "
            "adicione manualmente na aba **📋 Editar Itinerário Manual** quando necessário."
        )
        st.dataframe(pd.DataFrame(espo), hide_index=True, use_container_width=True)


# ── Aba 3: Editar Itinerário Manual ──────────────────────────────────────────

def _aba_editar():
    df_banco = st.session_state.bd_pneus
    it_salvo = _carregar_itinerario()

    st.subheader("Dados do Roteiro")
    col_d, col_m, col_v = st.columns(3)

    data_default = datetime.date.today()
    if it_salvo and it_salvo.get('data'):
        try:
            data_default = datetime.datetime.strptime(it_salvo['data'], '%d/%m/%Y').date()
        except Exception:
            pass

    data_rot  = col_d.date_input("Data do Roteiro:", value=data_default)
    motorista = col_m.text_input(
        "Motorista(s):",
        value=it_salvo.get('motorista', '') if it_salvo else ''
    )
    veiculo = col_v.text_input(
        "Veículo / Placa:",
        value=it_salvo.get('veiculo', '') if it_salvo else ''
    )

    st.markdown("---")
    st.subheader("Paradas do Roteiro")

    # Inicializa paradas da session_state (só na primeira vez ou após geração automática)
    if 'itin_paradas' not in st.session_state:
        st.session_state.itin_paradas = list(it_salvo.get('paradas', [])) if it_salvo else []

    paradas = st.session_state.itin_paradas

    clientes_disponiveis = sorted(
        df_banco['CLIENTE'].replace('', pd.NA).dropna().unique().tolist()
    )

    with st.expander("➕ Adicionar Parada", expanded=(len(paradas) == 0)):
        col_c, col_t, col_h = st.columns([3, 2, 2])
        novo_cliente = col_c.selectbox("Cliente:", [''] + clientes_disponiveis, key='itin_novo_cliente')
        novo_tipo    = col_t.selectbox("Tipo:", ['Entrega e Coleta', 'Entrega', 'Coleta'], key='itin_novo_tipo')
        nova_hora    = col_h.text_input("Hora prevista:", placeholder="08:30", key='itin_nova_hora')
        nova_obs     = st.text_input(
            "Observação (opcional):", key='itin_nova_obs',
            placeholder="Ex.: Portão lateral, ligar antes"
        )

        if st.button("➕ Adicionar ao Roteiro", type="primary"):
            if not novo_cliente:
                st.warning("Selecione um cliente.")
            else:
                paradas.append({
                    'cliente': novo_cliente,
                    'tipo':    novo_tipo,
                    'hora':    nova_hora.strip(),
                    'obs':     nova_obs.strip(),
                })
                st.session_state.itin_paradas = paradas
                st.rerun()

    if not paradas:
        st.info(
            "Nenhuma parada adicionada. Use o formulário acima ou gere automaticamente "
            "na aba **📅 Gerar Plano do Dia**."
        )
    else:
        st.markdown(f"**{len(paradas)} parada(s) — use ↑↓ para reordenar:**")
        for i, p in enumerate(paradas):
            col_n, col_c, col_t, col_h, col_up, col_dn, col_rm = st.columns(
                [0.5, 3, 2, 1.5, 0.5, 0.5, 0.5]
            )
            col_n.markdown(f"**{i + 1}.**")
            col_c.write(p.get('cliente', ''))
            col_t.write(p.get('tipo', '') or p.get('prazo', '') or '')
            col_h.write(p.get('hora', '') or '—')

            if col_up.button("↑", key=f"itin_up_{i}", help="Mover para cima") and i > 0:
                paradas[i], paradas[i - 1] = paradas[i - 1], paradas[i]
                st.session_state.itin_paradas = paradas
                st.rerun()
            if col_dn.button("↓", key=f"itin_dn_{i}", help="Mover para baixo") and i < len(paradas) - 1:
                paradas[i], paradas[i + 1] = paradas[i + 1], paradas[i]
                st.session_state.itin_paradas = paradas
                st.rerun()
            if col_rm.button("🗑️", key=f"itin_rm_{i}", help="Remover parada"):
                paradas.pop(i)
                st.session_state.itin_paradas = paradas
                st.rerun()

            if p.get('obs'):
                st.caption(f"  ↳ 📝 {p['obs']}")

    st.markdown("---")
    col_s, col_l = st.columns(2)

    if col_s.button("💾 Salvar Itinerário", type="primary"):
        it = {
            'data':      data_rot.strftime('%d/%m/%Y'),
            'motorista': motorista.strip(),
            'veiculo':   veiculo.strip(),
            'paradas':   paradas,
        }
        _salvar_itinerario(it)
        st.success("✅ Itinerário salvo! O painel do dia e o PPCP já refletem a nova ordem.")

    if col_l.button("🗑️ Limpar / Novo Roteiro"):
        st.session_state.itin_paradas = []
        try:
            _ITIN_JSON.unlink(missing_ok=True)
        except Exception:
            pass
        _excluir_github('data/itinerario.json', 'Remove itinerario')
        st.rerun()


# ── Aba 4: Painel do Dia ──────────────────────────────────────────────────────

def _aba_painel():
    it = _carregar_itinerario()
    if not it:
        st.info(
            "Nenhum itinerário salvo. Gere o plano na aba **📅 Gerar Plano do Dia** "
            "ou monte manualmente em **📋 Editar Itinerário Manual**."
        )
        return

    df = st.session_state.bd_pneus

    st.markdown(f"### 🗓️ Roteiro de **{it.get('data', '—')}**")
    col_m, col_v = st.columns(2)
    if it.get('motorista'):
        col_m.markdown(f"**Motorista(s):** {it['motorista']}")
    if it.get('veiculo'):
        col_v.markdown(f"**Veículo:** {it['veiculo']}")

    st.markdown("---")

    paradas = it.get('paradas', [])
    if not paradas:
        st.warning("Itinerário sem paradas. Edite na aba anterior.")
        return

    # ── Tabela-resumo ─────────────────────────────────────────────────────────
    resumo      = []
    tot_aguard  = tot_prod = tot_exped = 0

    for i, p in enumerate(paradas):
        cli    = p['cliente']
        os_cli = _buscar_cli_banco(cli, df)
        aguard = len(os_cli[os_cli['STATUS'].isin(['Aguardando', 'Em Limpeza'])])  if not os_cli.empty else 0
        prod   = len(os_cli[os_cli['STATUS'] == 'Em Produção'])  if not os_cli.empty else 0
        exped  = len(os_cli[os_cli['STATUS'] == 'Expedido'])     if not os_cli.empty else 0
        total  = aguard + prod + exped
        pct    = round((prod + exped) / total * 100) if total > 0 else 0

        if total == 0:     situ = '❌ Sem OS no banco'
        elif pct == 100:   situ = '✅ Pronto p/ expedir'
        elif aguard == 0:  situ = '🔄 Todos na linha'
        elif prod > 0:     situ = '🔄 Em produção'
        else:              situ = '⏳ Aguardando'

        tot_aguard += aguard
        tot_prod   += prod
        tot_exped  += exped

        resumo.append({
            'Parada':    i + 1,
            'Hora':      p.get('hora', '') or '—',
            'Cliente':   cli,
            'Motorista': p.get('motorista', '') or '—',
            'Prazo':     p.get('prazo', '') or '—',
            'Aguard.':   aguard,
            'Na linha':  prod,
            'Expedido':  exped,
            '% Pronto':  f"{pct}%",
            'Situação':  situ,
        })

    st.dataframe(pd.DataFrame(resumo), hide_index=True, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("⏳ Aguardando", tot_aguard)
    c2.metric("🔄 Na Linha",   tot_prod)
    c3.metric("✅ Expedido",   tot_exped)

    # ── Detalhe por parada ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Detalhe por Parada")

    for i, p in enumerate(paradas):
        cli  = p['cliente']
        hora = p.get('hora', '') or ''
        obs  = p.get('obs', '') or ''
        mot  = p.get('motorista', '') or ''

        os_cli = _buscar_cli_banco(cli, df)
        aguard = os_cli[os_cli['STATUS'].isin(['Aguardando', 'Em Limpeza'])]  if not os_cli.empty else pd.DataFrame()
        prod   = os_cli[os_cli['STATUS'] == 'Em Produção']       if not os_cli.empty else pd.DataFrame()
        exped  = os_cli[os_cli['STATUS'] == 'Expedido']          if not os_cli.empty else pd.DataFrame()
        total  = len(os_cli)
        pct    = round((len(prod) + len(exped)) / total * 100) if total > 0 else 0
        emoji  = '✅' if pct == 100 else ('🔄' if pct >= 50 else '⏳')

        titulo = f"{emoji} Parada {i + 1}"
        if hora:  titulo += f" — {hora}"
        if mot:   titulo += f" | 🚛 {mot}"
        titulo += f" | {cli}"

        with st.expander(titulo, expanded=(pct < 100)):
            if obs:
                st.caption(f"📝 {obs}")

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total OS",       total)
            col_b.metric("⏳ Aguardando",  len(aguard))
            col_c.metric("🔄 Em Produção", len(prod))
            col_d.metric("✅ Expedidos",   len(exped))

            st.progress(pct / 100, text=f"{pct}% pronto para embarque")

            if not exped.empty:
                with st.expander(f"📦 {len(exped)} pneus expedidos"):
                    st.dataframe(
                        exped[['NRORDEM', 'NRSERIE', 'DESENHO', 'DATA_SAIDA']],
                        hide_index=True, use_container_width=True
                    )
            if not prod.empty:
                with st.expander(f"🔄 {len(prod)} na linha (em produção)"):
                    st.dataframe(
                        prod[['NRORDEM', 'NRSERIE', 'DESENHO']],
                        hide_index=True, use_container_width=True
                    )
            if not aguard.empty:
                with st.expander(f"⏳ {len(aguard)} aguardando entrar na linha"):
                    st.dataframe(
                        aguard[['NRORDEM', 'NRSERIE', 'DESENHO', 'LOCAL_PALLET']],
                        hide_index=True, use_container_width=True
                    )
