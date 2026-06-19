"""
Camada de dados — leitura, gravação e importação de CSV externos.
Suporta dois modos:
  - LOCAL:  lê/salva em data/ordens.csv E sincroniza com GitHub (banco único)
  - NUVEM:  lê/salva via GitHub API (Streamlit Cloud)

Com banco único: qualquer bipe feito no escritório aparece na nuvem
e vice-versa, pois ambos usam o mesmo ordens.csv do GitHub.
"""
import json
import pandas as pd
import os
from pathlib import Path

# Caminho absoluto, independente de onde o Streamlit for iniciado
_BASE_DIR = Path(__file__).resolve().parent.parent
CAMINHO_CSV = _BASE_DIR / "data" / "ordens.csv"


def _token_github() -> str:
    """Retorna o token do GitHub seja de secrets (nuvem) ou do arquivo local."""
    # 1. Tenta st.secrets (Streamlit Cloud ou secrets.toml local)
    try:
        import streamlit as st
        token = st.secrets.get("github", {}).get("token", "")
        if token and token.strip():
            return token.strip()
    except Exception:
        pass
    # 2. Tenta variável de ambiente
    return os.environ.get("GITHUB_TOKEN", "")


def _modo_github() -> bool:
    """Retorna True se tiver token GitHub configurado — usa nuvem como banco."""
    return bool(_token_github())


def _modo_nuvem() -> bool:
    """Compatibilidade — mesmo que _modo_github."""
    return _modo_github()


def _github_cfg():
    token = _token_github()
    try:
        import streamlit as st
        cfg = st.secrets.get("github", {})
        repo     = cfg.get("repo",     "tiagoalexandre54/nsa-erp-pneutec")
        branch   = cfg.get("branch",   "main")
        csv_path = cfg.get("csv_path", "data/ordens.csv")
    except Exception:
        repo     = "tiagoalexandre54/nsa-erp-pneutec"
        branch   = "main"
        csv_path = "data/ordens.csv"
    return token, repo, branch, csv_path


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
    """
    Salva o CSV no repositório GitHub (cria ou atualiza).
    Lança exceção se a escrita falhar — quem chama precisa saber.
    """
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

    resp = requests.put(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()

COLUNAS = ['NRORDEM', 'IDPEDIDOPNEU', 'CLIENTE', 'NRSERIE', 'DESENHO', 'STATUS', 'DATA_ENTRADA', 'DATA_SAIDA', 'LOCAL_PALLET', 'RUA_PRODUCAO']

DADOS_INICIAIS = {
    'NRORDEM':      ['1662315', '1662318', '1662247', '1662248', '1584421'],
    'IDPEDIDOPNEU': ['', '', '', '', ''],
    'CLIENTE':      ['BRASPRESS', 'BRASPRESS', 'OPR LOGISTICA', 'OPR LOGISTICA', 'GUEDES AMORIM'],
    'NRSERIE':      ['039241', '039236', '3124', '3324', '1223'],
    'DESENHO':      ['VL110LA', 'VL110LA', 'VT120L', 'VT120L', 'VL110LA'],
    'STATUS':       ['Aguardando', 'Aguardando', 'Em Produção', 'Em Produção', 'Aguardando'],
    'DATA_ENTRADA': ['', '', '', '', ''],
    'DATA_SAIDA':   ['', '', '', '', ''],
    'LOCAL_PALLET': ['', '', '', '', ''],
    'RUA_PRODUCAO': ['', '', '', '', ''],
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
    Carrega dados do GitHub (banco único) quando token disponível.
    Fallback: CSV local — para uso offline sem internet.
    """
    df = None

    if _modo_github():
        try:
            df = _ler_csv_github()
        except Exception:
            df = None   # sem internet → cai para CSV local

    # Fallback: CSV local
    if df is None and CAMINHO_CSV.exists():
        df = pd.read_csv(CAMINHO_CSV, dtype=str, keep_default_na=False)

    if df is None:
        return pd.DataFrame(DADOS_INICIAIS)

    for col in COLUNAS:
        if col not in df.columns:
            df[col] = ''
    df = df[df['NRORDEM'].str.strip() != ''].reset_index(drop=True)
    return df[COLUNAS]


def salvar_dados(df: pd.DataFrame) -> bool:
    """
    Salva no GitHub (banco único) quando token disponível.
    Também salva CSV local como backup offline (efêmero no Streamlit Cloud —
    não sobrevive a reboot, por isso NÃO conta como persistência durável).

    Retorna True só se o dado realmente persistiu de forma durável:
    - modo GitHub: True somente se a escrita no GitHub teve sucesso
    - modo local (sem token configurado): True se salvou o CSV local
    """
    # Sempre salva backup local (best-effort, não decide o retorno em modo GitHub)
    local_ok = False
    try:
        CAMINHO_CSV.parent.mkdir(parents=True, exist_ok=True)
        tmp = CAMINHO_CSV.with_suffix('.tmp')
        df.to_csv(tmp, index=False)
        tmp.replace(CAMINHO_CSV)
        local_ok = True
    except Exception:
        pass

    # Sincroniza com GitHub (banco principal — única fonte durável na nuvem)
    if _modo_github():
        try:
            _salvar_csv_github(df)
            return True
        except Exception:
            return False  # falhou de verdade — quem chamou precisa saber

    return local_ok


def atualizar_e_salvar(filtro, campos: dict) -> tuple[bool, pd.DataFrame, int]:
    """
    Atualiza linhas do banco de forma ATÔMICA, evitando que dois operadores
    bipando ao mesmo tempo (recebimento, limpeza, linha, expedição) apaguem
    a mudança um do outro.

    Em vez de sobrescrever o banco inteiro com a cópia que está na memória
    do navegador (que pode estar desatualizada), este fluxo:
      1. Busca a versão MAIS RECENTE do banco (GitHub/local) na hora do bipe
      2. Aplica 'filtro' (função df -> máscara booleana) sobre essa versão
         fresca para achar as linhas certas
      3. Define os campos em 'campos' só nessas linhas
      4. Salva e retorna o dataframe atualizado

    Args:
        filtro: função que recebe o DataFrame fresco e retorna uma Series
                booleana (ex: lambda df: df['NRORDEM'] == '123')
        campos: dict {nome_coluna: valor} a aplicar nas linhas filtradas

    Returns:
        (sucesso, df_atualizado, qtd_linhas_afetadas)
        - sucesso=False  → falha real ao salvar (chamador deve avisar o usuário
          e NÃO considerar a ação como concluída)
        - qtd_linhas_afetadas=0 → filtro não encontrou nada (ex: OS já mudou
          de estado por outra pessoa entre o bipe e o salvamento)

        Chame `st.session_state.bd_pneus = df_atualizado` quando sucesso=True,
        mesmo se qtd_linhas_afetadas for 0, para refletir a verdade mais
        recente do banco na sessão.
    """
    df_fresh = carregar_dados()
    mask = filtro(df_fresh)
    qtd = int(mask.sum())

    if qtd == 0:
        return True, df_fresh, 0

    for campo, valor in campos.items():
        df_fresh.loc[mask, campo] = valor

    sucesso = salvar_dados(df_fresh)
    return sucesso, df_fresh, qtd


# ── Trava Global de IDPEDIDO (Poka-Yoke) ────────────────────────────────────
_TRAVA_JSON = _BASE_DIR / "data" / "trava_global.json"


def ler_trava_global() -> str | None:
    """
    Retorna o IDPEDIDO atualmente travado, ou None se não houver trava.
    Lê do GitHub em nuvem; arquivo local como fallback offline.
    """
    if _modo_github():
        try:
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/trava_global.json?ref={branch}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
                return json.loads(conteudo).get("id_travado")
        except Exception:
            pass
    if _TRAVA_JSON.exists():
        try:
            return json.loads(_TRAVA_JSON.read_text(encoding="utf-8")).get("id_travado")
        except Exception:
            pass
    return None


def set_trava_global(id_pedido: str | None) -> None:
    """
    Define (ou limpa) a trava global de IDPEDIDO.
    Persiste no GitHub em nuvem e localmente como backup.
    """
    payload = {"id_travado": id_pedido}
    conteudo_str = json.dumps(payload, ensure_ascii=False)

    # Salva local
    try:
        _TRAVA_JSON.parent.mkdir(parents=True, exist_ok=True)
        _TRAVA_JSON.write_text(conteudo_str, encoding="utf-8")
    except Exception:
        pass

    # Sincroniza GitHub
    if _modo_github():
        try:
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/trava_global.json"
            headers = {"Authorization": f"token {token}"}
            conteudo_b64 = base64.b64encode(conteudo_str.encode("utf-8")).decode()
            r = requests.get(url, headers=headers, timeout=5)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload_gh = {"message": "Atualiza trava global", "content": conteudo_b64, "branch": branch}
            if sha:
                payload_gh["sha"] = sha
            requests.put(url, json=payload_gh, headers=headers, timeout=10)
        except Exception:
            pass


def excluir_os(nrordem: str) -> tuple[bool, str]:
    """
    Remove uma OS do banco de dados pelo NRORDEM.
    Busca a versão mais recente antes de excluir (evita reverter mudanças
    de outro operador) e confirma que o salvamento realmente persistiu.
    Retorna (sucesso, mensagem).
    """
    import streamlit as st
    df_fresh = carregar_dados()
    idx = df_fresh.index[df_fresh['NRORDEM'] == nrordem.strip()].tolist()
    if not idx:
        return False, f"OS {nrordem} não encontrada."
    df_novo = df_fresh.drop(index=idx).reset_index(drop=True)
    if not salvar_dados(df_novo):
        return False, f"⚠️ Falha ao salvar — verifique a conexão e tente novamente. OS {nrordem} NÃO foi excluída."
    st.session_state.bd_pneus = df_novo
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
