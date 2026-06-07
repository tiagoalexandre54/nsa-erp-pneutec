"""
Tela — OEE (Overall Equipment Effectiveness).
Importa a planilha de OEE (4 abas), persiste no GitHub e exibe:
Dashboard, Análise Mensal, Lançamento Diário e Pneus/Homem-Mês.
"""
import streamlit as st
import pandas as pd
import datetime
import json
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_OEE_JSON = _BASE_DIR / "data" / "oee.json"
_SCHEMA_OEE = 1


# ── Persistência (GitHub + local) ────────────────────────────────────────────
def _salvar_oee(dados: dict) -> None:
    dados = dict(dados)
    dados['_schema'] = _SCHEMA_OEE
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2)
    try:
        _OEE_JSON.parent.mkdir(parents=True, exist_ok=True)
        _OEE_JSON.write_text(conteudo, encoding="utf-8")
    except Exception:
        pass
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return
        import requests, base64
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/data/oee.json"
        headers = {"Authorization": f"token {token}"}
        b64 = base64.b64encode(conteudo.encode("utf-8")).decode()
        r = requests.get(url, headers=headers, timeout=5)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": "Atualiza OEE", "content": b64, "branch": branch}
        if sha:
            payload["sha"] = sha
        requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


def _carregar_oee() -> dict | None:
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/oee.json?ref={branch}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
                d = json.loads(conteudo)
                if d.get('_schema') == _SCHEMA_OEE:
                    return d
    except Exception:
        pass
    if _OEE_JSON.exists():
        try:
            d = json.loads(_OEE_JSON.read_text(encoding="utf-8"))
            if d.get('_schema') == _SCHEMA_OEE:
                return d
        except Exception:
            pass
    return None


# ── Helpers de parsing ───────────────────────────────────────────────────────
def _num(v, default=0.0):
    """Converte string para float; vazio/inválido → default."""
    try:
        s = str(v).strip()
        if s in ('', 'nan', '—', '-'):
            return default
        return float(s)
    except Exception:
        return default


def _achar_aba(xl, *palavras):
    """Encontra o nome da aba que contém alguma das palavras-chave."""
    for nome in xl.sheet_names:
        alvo = nome.upper()
        if any(p.upper() in alvo for p in palavras):
            return nome
    return None


def _achar_header(df, *rotulos):
    """Acha o índice da linha de cabeçalho que contém os rótulos dados."""
    for r in range(min(12, len(df))):
        linha = [str(df.iloc[r, c]).strip().upper() for c in range(df.shape[1])]
        texto = ' | '.join(linha)
        if all(rot.upper() in texto for rot in rotulos):
            return r
    return None


def _ler_oee(arquivo) -> dict:
    xl = pd.ExcelFile(arquivo, engine='openpyxl')
    resultado = {
        'gerado_em': datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        'mensal': [], 'diario': [], 'homem_mes': [],
    }

    # ── Análise Mensal ──
    nome = _achar_aba(xl, 'Mensal', 'Análise', 'Analise')
    if nome:
        df = pd.read_excel(xl, sheet_name=nome, header=None, dtype=str).fillna('')
        h = _achar_header(df, 'MÊS', 'OEE') or _achar_header(df, 'MES', 'OEE') or 3
        for r in range(h + 1, len(df)):
            mes = str(df.iloc[r, 0]).strip()
            if not mes or 'MÉDIA' in mes.upper() or 'MEDIA' in mes.upper() or 'ELABOR' in mes.upper():
                continue
            produzido = _num(df.iloc[r, 3])
            if produzido <= 0:
                continue  # mês ainda não preenchido
            resultado['mensal'].append({
                'mes': mes, 'ano': str(df.iloc[r, 1]).strip(),
                'dias_uteis': _num(df.iloc[r, 2]),
                'produzido': produzido, 'aprovados': _num(df.iloc[r, 4]),
                'defeitos': _num(df.iloc[r, 5]), 'pct_defeito': _num(df.iloc[r, 6]),
                'disponib': _num(df.iloc[r, 7]), 'desempenho': _num(df.iloc[r, 8]),
                'qualidade': _num(df.iloc[r, 9]), 'oee': _num(df.iloc[r, 10]),
                'meta': _num(df.iloc[r, 11]), 'pct_meta': _num(df.iloc[r, 12]),
                'resultado': str(df.iloc[r, 13]).strip(),
            })

    # ── Lançamento Diário ──
    nome = _achar_aba(xl, 'Lançamento', 'Lancamento', 'Diário', 'Diario')
    if nome:
        df = pd.read_excel(xl, sheet_name=nome, header=None, dtype=str).fillna('')
        h = _achar_header(df, 'DATA', 'OEE') or 5
        for r in range(h + 1, len(df)):
            produzidos = _num(df.iloc[r, 12])
            colab = _num(df.iloc[r, 3])
            if produzidos <= 0 and colab <= 0:
                continue  # dia sem lançamento (fim de semana/feriado)
            data_raw = str(df.iloc[r, 1]).strip()
            dt = pd.to_datetime(data_raw, errors='coerce')
            data_fmt = dt.strftime('%d/%m/%Y') if pd.notna(dt) else data_raw
            resultado['diario'].append({
                'data': data_fmt, 'dia': str(df.iloc[r, 2]).strip(),
                'colab_total': _num(df.iloc[r, 3]), 'colab_pres': _num(df.iloc[r, 4]),
                'colab_aus': _num(df.iloc[r, 5]),
                'paradas_plan': _num(df.iloc[r, 7]), 'paradas_nplan': _num(df.iloc[r, 8]),
                'produzir': _num(df.iloc[r, 11]), 'produzidos': produzidos,
                'defeitos': _num(df.iloc[r, 13]), 'aprovados': _num(df.iloc[r, 14]),
                'disponib': _num(df.iloc[r, 15]), 'desempenho': _num(df.iloc[r, 16]),
                'qualidade': _num(df.iloc[r, 17]), 'oee': _num(df.iloc[r, 18]),
                'status': str(df.iloc[r, 19]).strip(),
            })

    # ── Pneus Homem-Mês ──
    nome = _achar_aba(xl, 'Homem')
    if nome:
        df = pd.read_excel(xl, sheet_name=nome, header=None, dtype=str).fillna('')
        h = _achar_header(df, 'MÊS', 'PNEUS') or _achar_header(df, 'MES', 'PNEUS') or 3
        for r in range(h + 1, len(df)):
            mes = str(df.iloc[r, 0]).strip()
            if not mes or 'MÉDIA' in mes.upper() or 'MEDIA' in mes.upper():
                continue
            prod = _num(df.iloc[r, 3])
            if prod <= 0:
                continue
            resultado['homem_mes'].append({
                'mes': mes, 'ano': str(df.iloc[r, 1]).strip(),
                'media_colab': _num(df.iloc[r, 2]), 'produzidos': prod,
                'pneus_pessoa': _num(df.iloc[r, 4]),
            })

    return resultado


# ── Tela principal ───────────────────────────────────────────────────────────
def tela_oee():
    st.title("📊 OEE — Eficiência Global dos Equipamentos")

    with st.expander("📂 Importar / Atualizar planilha de OEE", expanded=False):
        arquivo = st.file_uploader(
            "Selecione a planilha de OEE (.xlsx):",
            type=["xlsx", "xls"], key="uploader_oee",
        )
        if arquivo:
            try:
                dados = _ler_oee(arquivo)
                _salvar_oee(dados)
                st.success(
                    f"✅ OEE importado! {len(dados['mensal'])} mês(es), "
                    f"{len(dados['diario'])} lançamento(s) diário(s)."
                )
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao ler a planilha: {e}")

    dados = _carregar_oee()
    if not dados:
        st.info("Nenhum dado de OEE carregado. Importe a planilha acima para começar.")
        return

    st.caption(f"📅 Atualizado em {dados.get('gerado_em', '—')}")

    aba1, aba2, aba3, aba4 = st.tabs([
        "🏆 Dashboard", "📈 Análise Mensal", "📋 Lançamento Diário", "🔧 Pneus/Homem",
    ])
    with aba1:
        _dashboard(dados)
    with aba2:
        _analise_mensal(dados)
    with aba3:
        _lancamento_diario(dados)
    with aba4:
        _pneus_homem(dados)


def _pct(v):
    return f"{v * 100:.1f}%"


# ── 1. Dashboard (mês mais recente) ──────────────────────────────────────────
def _dashboard(dados: dict):
    mensal = dados.get('mensal', [])
    if not mensal:
        st.info("Sem dados mensais para o dashboard.")
        return

    atual = mensal[-1]  # mês mais recente preenchido
    st.subheader(f"Indicadores de {atual['mes']}/{atual['ano']}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 OEE Geral",       _pct(atual['oee']))
    c2.metric("⏱️ Disponibilidade", _pct(atual['disponib']))
    c3.metric("⚡ Desempenho",      _pct(atual['desempenho']))
    c4.metric("✅ Qualidade",       _pct(atual['qualidade']))

    st.markdown("---")
    st.markdown("**Produção & Metas**")
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("🔢 Produzido", int(atual['produzido']))
    p2.metric("✅ Aprovados", int(atual['aprovados']))
    p3.metric("❌ Defeitos",  int(atual['defeitos']))
    p4.metric("🎯 Meta",      int(atual['meta']))
    p5.metric("📈 % Meta",    _pct(atual['pct_meta']))

    # Pneus/Homem do mês mais recente
    hm = [h for h in dados.get('homem_mes', []) if h['mes'] == atual['mes']]
    if hm:
        st.markdown("---")
        h = hm[-1]
        q1, q2 = st.columns(2)
        q1.metric("👥 Média Colaboradores", f"{h['media_colab']:.1f}")
        q2.metric("🔧 Pneus / Pessoa",      f"{h['pneus_pessoa']:.1f}")

    # Classificação OEE
    oee = atual['oee']
    if oee >= 0.85:
        st.success(f"🟢 **World Class** — OEE de {_pct(oee)} (≥ 85%).")
    elif oee >= 0.60:
        st.warning(f"🟡 **Bom** — OEE de {_pct(oee)} (60–85%). Há espaço para melhoria.")
    else:
        st.error(f"🔴 **Baixo** — OEE de {_pct(oee)} (< 60%). Requer atenção.")


# ── 2. Análise Mensal ────────────────────────────────────────────────────────
def _analise_mensal(dados: dict):
    mensal = dados.get('mensal', [])
    if not mensal:
        st.info("Sem dados mensais.")
        return

    df = pd.DataFrame(mensal)
    df_view = pd.DataFrame({
        'Mês': df['mes'], 'Produzido': df['produzido'].astype(int),
        'Aprovados': df['aprovados'].astype(int), 'Defeitos': df['defeitos'].astype(int),
        'Disponib.': (df['disponib'] * 100).round(1),
        'Desempenho': (df['desempenho'] * 100).round(1),
        'Qualidade': (df['qualidade'] * 100).round(1),
        'OEE %': (df['oee'] * 100).round(1),
        '% Meta': (df['pct_meta'] * 100).round(1),
        'Resultado': df['resultado'],
    })
    st.dataframe(df_view, hide_index=True, use_container_width=True)

    st.markdown("**Evolução dos indicadores (%)**")
    chart = df.set_index('mes')[['disponib', 'desempenho', 'qualidade', 'oee']] * 100
    chart.columns = ['Disponib.', 'Desempenho', 'Qualidade', 'OEE']
    st.line_chart(chart)


# ── 3. Lançamento Diário ─────────────────────────────────────────────────────
def _lancamento_diario(dados: dict):
    diario = dados.get('diario', [])
    if not diario:
        st.info("Sem lançamentos diários.")
        return

    df = pd.DataFrame(diario)
    df_view = pd.DataFrame({
        'Data': df['data'], 'Dia': df['dia'],
        'Colab. Pres.': df['colab_pres'].astype(int),
        'Paradas (h)': (df['paradas_plan'] + df['paradas_nplan']).round(2),
        'Produzidos': df['produzidos'].astype(int),
        'Defeitos': df['defeitos'].astype(int),
        'Aprovados': df['aprovados'].astype(int),
        'Disp. %': (df['disponib'] * 100).round(1),
        'Desemp. %': (df['desempenho'] * 100).round(1),
        'Qual. %': (df['qualidade'] * 100).round(1),
        'OEE %': (df['oee'] * 100).round(1),
        'Status': df['status'],
    })
    st.dataframe(df_view, hide_index=True, use_container_width=True)

    st.markdown("**OEE diário (%)**")
    chart = df[['data', 'oee']].copy()
    chart['OEE %'] = (chart['oee'] * 100).round(1)
    st.line_chart(chart.set_index('data')[['OEE %']])


# ── 4. Pneus / Homem-Mês ─────────────────────────────────────────────────────
def _pneus_homem(dados: dict):
    hm = dados.get('homem_mes', [])
    if not hm:
        st.info("Sem dados de pneus por homem.")
        return

    df = pd.DataFrame(hm)
    df_view = pd.DataFrame({
        'Mês': df['mes'], 'Ano': df['ano'],
        'Média Colab.': df['media_colab'].round(1),
        'Produzidos': df['produzidos'].astype(int),
        'Pneus / Pessoa': df['pneus_pessoa'].round(1),
    })
    st.dataframe(df_view, hide_index=True, use_container_width=True)

    st.markdown("**Pneus por pessoa (mês)**")
    st.bar_chart(df.set_index('mes')[['pneus_pessoa']].rename(columns={'pneus_pessoa': 'Pneus/Pessoa'}))
