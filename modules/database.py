"""
Camada de dados — leitura, gravação e importação de CSV externos.
Suporta dois modos:
  - LOCAL:  lê/salva em data/ordens.csv (uso no escritório)
  - NUVEM:  lê/salva via GitHub API (uso no Streamlit Cloud)
"""
import pandas as pd
import os
from pathlib import Path

# Caminho absoluto, independente de onde o Streamlit for iniciado
_BASE_DIR = Path(__file__).resolve().parent.parent
CAMINHO_CSV = _BASE_DIR / "data" / "ordens.csv"


def _modo_nuvem() -> bool:
    """Retorna True se estiver rodando no Streamlit Cloud com token configurado."""
    try:
        import streamlit as st
        token = st.secrets.get("github", {}).get("token", "")
        return bool(token and token.strip())
    except Exception:
        return False


def _github_cfg():
    import streamlit as st
    cfg = st.secrets["github"]
    return cfg["token"], cfg["repo"], cfg.get("branch", "main"), cfg.get("csv_path", "data/ordens.csv")


def _ler_csv_github() -> pd.DataFrame:
    """Lê o CSV diretamente do repositório GitHub."""
    import requests, base64, io
    token, repo, branch, csv_path = _github_cfg()
    url = f"https://api.github.com/repos/{repo}/contents/{csv_path}?ref={branch}"
    r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=10)
    if r.status_code == 404:
        return None   # arquivo ainda não existe
    r.raise_for_status()
    conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
    return pd.read_csv(io.StringIO(conteudo), dtype=str, keep_default_na=False)


def _salvar_csv_github(df: pd.DataFrame) -> None:
    """Salva o CSV no repositório GitHub (cria ou atualiza)."""
    import requests, base64, io
    token, repo, branch, csv_path = _github_cfg()
    url = f"https://api.github.com/repos/{repo}/contents/{csv_path}"
    headers = {"Authorization": f"token {token}"}

    # Converte para bytes
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    conteudo_b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode()

    # Verifica se já existe (precisa do SHA para atualizar)
    r = requests.get(url, headers=headers, timeout=10)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": "Atualiza ordens.csv via ERP NSA",
        "content": conteudo_b64,
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    requests.put(url, json=payload, headers=headers, timeout=15)

COLUNAS = ['NRORDEM', 'IDPEDIDOPNEU', 'CLIENTE', 'NRSERIE', 'DESENHO', 'STATUS', 'DATA_ENTRADA', 'DATA_SAIDA']

DADOS_INICIAIS = {
    'NRORDEM':      ['1662315', '1662318', '1662247', '1662248', '1584421'],
    'IDPEDIDOPNEU': ['', '', '', '', ''],
    'CLIENTE':      ['BRASPRESS', 'BRASPRESS', 'OPR LOGISTICA', 'OPR LOGISTICA', 'GUEDES AMORIM'],
    'NRSERIE':      ['039241', '039236', '3124', '3324', '1223'],
    'DESENHO':      ['VL110LA', 'VL110LA', 'VT120L', 'VT120L', 'VL110LA'],
    'STATUS':       ['Aguardando', 'Aguardando', 'Em Produção', 'Em Produção', 'Aguardando'],
    'DATA_ENTRADA': ['', '', '', '', ''],
    'DATA_SAIDA':   ['', '', '', '', ''],
}

# ── Mapeamento de nomes alternativos de colunas ──────────────────────────────
# Cobre variações comuns de sistemas ERP/exportações brasileiras.
_MAPEAMENTO_COLUNAS = {
    # ID do Pedido de Pneu (campo do ERP NSA) — nível pedido
    'IDPEDIDOPNEU':      'IDPEDIDOPNEU',
    'ID_PEDIDO_PNEU':    'IDPEDIDOPNEU',
    'ID_PEDIDO':         'IDPEDIDOPNEU',

    # ID do Item do Pedido — nível pneu individual → NRORDEM
    'IDITEMPEDIDOPNEU':  'NRORDEM',
    'ID_ITEM_PEDIDO':    'NRORDEM',
    'IDITEMPEDIDO':      'NRORDEM',

    # Data de fechamento/conclusão
    'DTFECHAMENTO':      'DATA_SAIDA',
    'DT_FECHAMENTO':     'DATA_SAIDA',
    'DATA_FECHAMENTO':   'DATA_SAIDA',

    # Número da Ordem
    'NR_ORDEM':        'NRORDEM',
    'NR ORDEM':        'NRORDEM',
    'ORDEM':           'NRORDEM',
    'NRORDEM':         'NRORDEM',
    'NUM_ORDEM':       'NRORDEM',
    'NUMERO_ORDEM':    'NRORDEM',
    'PEDIDO':          'NRORDEM',
    'NR_PEDIDO':       'NRORDEM',

    # Número de Série
    'NR_SERIE':        'NRSERIE',
    'NR SERIE':        'NRSERIE',
    'SERIE':           'NRSERIE',
    'NRSERIE':         'NRSERIE',
    'NUMERO_SERIE':    'NRSERIE',
    'NUM_SERIE':       'NRSERIE',

    # Desenho / Modelo
    'DESCRICAO':       'DESENHO',
    'DESCRIÇÃO':       'DESENHO',
    'DESC':            'DESENHO',
    'DESENHO':         'DESENHO',
    'MODELO':          'DESENHO',
    'PRODUTO':         'DESENHO',

    # Cliente
    'NOME_CLIENTE':    'CLIENTE',
    'RAZAO_SOCIAL':    'CLIENTE',
    'RAZÃO_SOCIAL':    'CLIENTE',
    'CLIENTE':         'CLIENTE',
    'EMPRESA':         'CLIENTE',

    # Data de Entrada / Coleta  ← inclui DTENTRADA do ERP NSA
    'DATA_ENTRADA':    'DATA_ENTRADA',
    'DT_ENTRADA':      'DATA_ENTRADA',
    'DTENTRADA':       'DATA_ENTRADA',   # ← ERP NSA
    'DATA_COLETA':     'DATA_ENTRADA',
    'DT_COLETA':       'DATA_ENTRADA',
    'DATA_EMISSAO':    'DATA_ENTRADA',
    'DATA_EMISSÃO':    'DATA_ENTRADA',
    'DT_EMISSAO':      'DATA_ENTRADA',
    'DT_EMISSÃO':      'DATA_ENTRADA',
    'DTEMISSAO':       'DATA_ENTRADA',   # ← ERP NSA (fallback quando DTENTRADA vazia)
    'DATA_ABERTURA':   'DATA_ENTRADA',
    'DT_ABERTURA':     'DATA_ENTRADA',

    # Data de Saída / Entrega  ← inclui DTENTREGA do ERP NSA
    'DATA_SAIDA':      'DATA_SAIDA',
    'DATA_SAÍDA':      'DATA_SAIDA',
    'DT_SAIDA':        'DATA_SAIDA',
    'DT_SAÍDA':        'DATA_SAIDA',
    'DATA_ENTREGA':    'DATA_SAIDA',
    'DT_ENTREGA':      'DATA_SAIDA',
    'DTENTREGA':       'DATA_SAIDA',     # ← ERP NSA
    'DATA_PREVISTA':   'DATA_SAIDA',
    'DT_PREVISTA':     'DATA_SAIDA',
    'PREV_ENTREGA':    'DATA_SAIDA',
    'PREVISAO':        'DATA_SAIDA',
    'PREVISÃO':        'DATA_SAIDA',

    # Status  ← inclui ST_PNEU do ERP NSA
    'STATUS':          'STATUS',
    'SITUACAO':        'STATUS',
    'SITUAÇÃO':        'STATUS',
    'ESTADO':          'STATUS',
    'ST_PNEU':         'STATUS',         # ← ERP NSA

    # Cliente  ← inclui NM_PESSOA do ERP NSA
    'NM_PESSOA':       'CLIENTE',        # ← ERP NSA
    'NOME_PESSOA':     'CLIENTE',

    # Desenho  ← inclui DS_ITEM do ERP NSA
    'DS_ITEM':         'DESENHO',        # ← ERP NSA
    'ITEM':            'DESENHO',
}


def carregar_dados() -> pd.DataFrame:
    """
    Carrega dados do CSV — local ou GitHub conforme o ambiente.
    """
    df = None

    if _modo_nuvem():
        try:
            df = _ler_csv_github()
        except Exception:
            df = None
    elif CAMINHO_CSV.exists():
        df = pd.read_csv(CAMINHO_CSV, dtype=str, keep_default_na=False)

    if df is None:
        return pd.DataFrame(DADOS_INICIAIS)

    for col in COLUNAS:
        if col not in df.columns:
            df[col] = ''
    df = df[df['NRORDEM'].str.strip() != ''].reset_index(drop=True)
    return df[COLUNAS]


def salvar_dados(df: pd.DataFrame) -> None:
    """Persiste o DataFrame — local ou GitHub conforme o ambiente."""
    if _modo_nuvem():
        _salvar_csv_github(df)
    else:
        CAMINHO_CSV.parent.mkdir(parents=True, exist_ok=True)
        tmp = CAMINHO_CSV.with_suffix('.tmp')
        df.to_csv(tmp, index=False)
        tmp.replace(CAMINHO_CSV)


def excluir_os(nrordem: str) -> tuple[bool, str]:
    """
    Remove uma OS do banco de dados pelo NRORDEM.
    Retorna (sucesso, mensagem).
    """
    import streamlit as st
    df = st.session_state.bd_pneus
    idx = df.index[df['NRORDEM'] == nrordem.strip()].tolist()
    if not idx:
        return False, f"OS {nrordem} não encontrada."
    st.session_state.bd_pneus = df.drop(index=idx).reset_index(drop=True)
    salvar_dados(st.session_state.bd_pneus)
    return True, f"OS {nrordem} excluída com sucesso."


def _detectar_separador(caminho: str) -> str:
    """Detecta automaticamente se o CSV usa ; ou ,"""
    with open(caminho, 'r', encoding='latin1', errors='ignore') as f:
        primeira_linha = f.readline()
    return ';' if primeira_linha.count(';') >= primeira_linha.count(',') else ','


def importar_csv_externo(caminho: str) -> pd.DataFrame:
    """
    Importa CSV externo (rel 1 / rel 2) e normaliza para o padrão interno.
    - Detecta separador automaticamente (; ou ,)
    - Tenta múltiplas codificações (UTF-8, Latin-1, CP1252)
    - Mapeia dezenas de nomes alternativos de colunas
    - Preserva DATA_ENTRADA e DATA_SAIDA se existirem no CSV
    - Lança ValueError com mensagem clara em caso de coluna obrigatória ausente
    """
    sep = _detectar_separador(caminho)

    df_ext = None
    for enc in ('utf-8-sig', 'latin1', 'cp1252'):
        try:
            df_ext = pd.read_csv(
                caminho,
                dtype=str,
                encoding=enc,
                sep=sep,
                keep_default_na=False,
            )
            break
        except UnicodeDecodeError:
            continue

    if df_ext is None:
        raise ValueError("Não foi possível decodificar o arquivo CSV. Use UTF-8 ou Latin-1.")

    # Normaliza nomes de colunas: strip + maiúsculo
    df_ext.columns = df_ext.columns.str.strip().str.upper()

    # ── Evita colunas duplicadas após rename ─────────────────────────────────
    # Quando duas colunas do CSV mapeiam para o mesmo campo interno,
    # mantém apenas a mais prioritária e descarta a secundária do rename.
    # Prioridade DATA_ENTRADA: DTENTRADA > DTEMISSAO
    # Prioridade DATA_SAIDA:   DTENTREGA > DTFECHAMENTO

    tem_entrada_dupla = 'DTEMISSAO' in df_ext.columns and 'DTENTRADA' in df_ext.columns
    tem_saida_dupla   = 'DTFECHAMENTO' in df_ext.columns and 'DTENTREGA' in df_ext.columns

    # Preserva DTEMISSAO como fallback antes de excluí-la do rename
    if tem_entrada_dupla:
        df_ext['_DTEMISSAO_ORIG'] = df_ext['DTEMISSAO']

    # Monta rename sem as colunas secundárias que gerariam duplicatas
    colunas_excluir_rename = set()
    if tem_entrada_dupla:
        colunas_excluir_rename.add('DTEMISSAO')    # DTENTRADA tem prioridade
    if tem_saida_dupla:
        colunas_excluir_rename.add('DTFECHAMENTO') # DTENTREGA tem prioridade

    # Também garante que dois campos distintos não virem o mesmo alvo
    alvos_usados = {}
    renomear = {}
    for k, v in _MAPEAMENTO_COLUNAS.items():
        if k not in df_ext.columns:
            continue
        if k in colunas_excluir_rename:
            continue
        if v in alvos_usados:
            continue   # já tem uma coluna mapeada para este alvo
        renomear[k] = v
        alvos_usados[v] = k

    df_ext.rename(columns=renomear, inplace=True)

    # Remove colunas duplicadas que possam ter sobrado (mantém a primeira ocorrência)
    df_ext = df_ext.loc[:, ~df_ext.columns.duplicated()]

    # Validação: NRORDEM é obrigatório
    if 'NRORDEM' not in df_ext.columns:
        colunas_encontradas = ', '.join(df_ext.columns.tolist())
        raise ValueError(
            f"Coluna NRORDEM (ou equivalente) não encontrada no CSV.\n"
            f"Colunas detectadas: {colunas_encontradas}\n\n"
            f"Nomes aceitos: NR_ORDEM, NR ORDEM, ORDEM, PEDIDO, NR_PEDIDO, NRORDEM"
        )

    # Garante colunas de controle com valor padrão
    for col in ['STATUS', 'DATA_ENTRADA', 'DATA_SAIDA']:
        if col not in df_ext.columns:
            df_ext[col] = ''

    # ── Fallback de data: se DTENTRADA veio vazia mas DTEMISSAO existe,
    # usa DTEMISSAO como DATA_ENTRADA (caso "Aguardando" do ERP NSA)
    if '_DTEMISSAO_ORIG' in df_ext.columns:
        mask = df_ext['DATA_ENTRADA'].str.strip() == ''
        df_ext.loc[mask, 'DATA_ENTRADA'] = df_ext.loc[mask, '_DTEMISSAO_ORIG']
        df_ext.drop(columns=['_DTEMISSAO_ORIG'], inplace=True, errors='ignore')

    # ── Normaliza status do ERP para os valores padrão do sistema ──────────
    STATUS_MAP = {
        'aguardando imp. ficha':          'Aguardando',
        'aguardando impressão da ficha':  'Aguardando',
        'aguardando':                     'Aguardando',
        'em produção':                    'Em Produção',
        'em producao':                    'Em Produção',
        'produção concluída':             'Em Produção',
        'producao concluida':             'Em Produção',
        'ordem finalizada':               'Em Produção',
        'finalizadas':                    'Em Produção',
        'expedido':                       'Expedido',
        'faturado':                       'Expedido',
    }
    df_ext['STATUS'] = df_ext['STATUS'].apply(
        lambda s: STATUS_MAP.get(str(s).strip().lower(), s if str(s).strip() else 'Aguardando')
    )

    # Garante todas as colunas restantes
    for col in COLUNAS:
        if col not in df_ext.columns:
            df_ext[col] = ''

    # Quando NRORDEM ainda está vazio, usa IDPEDIDOPNEU como fallback
    mask_sem_ordem = df_ext['NRORDEM'].str.strip() == ''
    if 'IDPEDIDOPNEU' in df_ext.columns and mask_sem_ordem.any():
        df_ext.loc[mask_sem_ordem, 'NRORDEM'] = df_ext.loc[mask_sem_ordem, 'IDPEDIDOPNEU'].str.strip()

    # Remove linhas onde nenhum identificador foi encontrado
    df_ext = df_ext[df_ext['NRORDEM'].str.strip() != ''].reset_index(drop=True)

    # Limpa espaços em todos os campos de texto
    for col in COLUNAS:
        df_ext[col] = df_ext[col].astype(str).str.strip()

    return df_ext[COLUNAS].copy()
