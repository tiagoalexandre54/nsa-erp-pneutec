"""
Leitor de PDF — Pedido de Recapagem NSA.

Estratégia de parsing:
  Em vez de exigir padrões rígidos no Nr. Série e Desenho, ancora na
  MEDIDA DO PNEU (ex: 275/80R22.5) que tem formato sempre previsível.
  Tudo antes da medida é: Nr. Série + Modelo + Desenho.
  Nr. Série = primeiro token da linha (dígitos + letra opcional: 1223, 1223A, 17399).
  Desenho   = token imediatamente antes da medida.
  Modelo    = tokens entre Série e Desenho.

Compatível com:
  - Séries puramente numéricas: 17399, 16678
  - Séries alfanuméricas: 1223A, 4822a
  - Desenhos com traço: DVUM-3B
  - Desenhos sem traço: VL110LA, VRT1
"""

import re
import pandas as pd

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False


# ── Padrões de medida de pneu ────────────────────────────────────────────────
# Cobre: 275/80R22.5 | 295/80R22,5 | 1200R24 | 17,5X25 | 215/75R17,5
_RE_MEDIDA = re.compile(
    r'(\d{2,4}[/,.]?\d{0,3}[RrXx]\d{2,3}(?:[.,]\d+)?)'
)

# Nr. Série: começa com dígitos, pode terminar com letras (ex: 1223A, 4822a)
_RE_NRSERIE_INICIO = re.compile(r'^(\d{3,6}[A-Za-z]{0,2})\s+')

# Cabeçalho do documento
_RE_CLIENTE    = re.compile(r'Cliente:\s*(.+?)(?:\s{2,}|\s+Condi|\s+Endere|$)', re.IGNORECASE)
_RE_NR_PEDIDO  = re.compile(r'Nr\.?\s*Pedido:\s*(\d+)', re.IGNORECASE)
_RE_DT_EMISSAO = re.compile(r'Data\s+Emiss[aã]o:\s*([\d/]+)', re.IGNORECASE)
_RE_DT_ENTREGA = re.compile(r'Data\s+Entrega:\s*([\d/]+)', re.IGNORECASE)

# Linhas que devem ser ignoradas mesmo que contenham medida
_IGNORAR_SE_CONTEM = ('nr. série', 'nr serie', 'modelo', 'medida', 'observa', 'total:', 'page ')


def _extrair_texto(caminho: str) -> str:
    if not PDFPLUMBER_OK:
        raise ImportError("pdfplumber não instalado. Execute: python -m pip install pdfplumber")
    with pdfplumber.open(caminho) as pdf:
        paginas = [p.extract_text() or "" for p in pdf.pages]
    return "\n".join(paginas)


def _parsear_linha_pneu(linha: str):
    """
    Tenta extrair (nrserie, modelo, desenho, medida) de uma linha.
    Retorna None se a linha não for de pneu.
    """
    linha = linha.strip()

    # Ignora linhas de cabeçalho ou rodapé
    linha_lower = linha.lower()
    if any(ign in linha_lower for ign in _IGNORAR_SE_CONTEM):
        return None

    # Linha deve conter uma medida de pneu
    m_medida = _RE_MEDIDA.search(linha)
    if not m_medida:
        return None

    # Linha deve começar com um Nr. Série
    m_serie = _RE_NRSERIE_INICIO.match(linha)
    if not m_serie:
        return None

    nrserie = m_serie.group(1).strip()
    medida  = m_medida.group(1).strip()

    # Extrai o trecho entre série e medida → Modelo + Desenho
    pos_serie_fim   = m_serie.end()
    pos_medida_ini  = linha.index(medida)

    if pos_medida_ini <= pos_serie_fim:
        return None

    meio = linha[pos_serie_fim:pos_medida_ini].strip()
    tokens = meio.split()

    if not tokens:
        return None

    # Último token antes da medida = Desenho; os anteriores = Modelo
    desenho = tokens[-1]
    modelo  = ' '.join(tokens[:-1]) if len(tokens) > 1 else tokens[0]

    return nrserie, modelo, desenho, medida


def extrair_pneus_pdf(caminho: str) -> pd.DataFrame:
    """
    Lê PDF de Pedido de Recapagem e retorna DataFrame no padrão interno.

    Raises:
        ImportError — pdfplumber não instalado
        ValueError  — nenhum pneu encontrado
    """
    texto  = _extrair_texto(caminho)
    linhas = texto.splitlines()

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    cliente    = ""
    nr_pedido  = ""
    dt_emissao = ""
    dt_entrega = ""

    for linha in linhas:
        if not cliente:
            m = _RE_CLIENTE.search(linha)
            if m:
                cliente = m.group(1).strip()
        if not nr_pedido:
            m = _RE_NR_PEDIDO.search(linha)
            if m:
                nr_pedido = m.group(1).strip()
        if not dt_emissao:
            m = _RE_DT_EMISSAO.search(linha)
            if m:
                dt_emissao = m.group(1).strip()
        if not dt_entrega:
            m = _RE_DT_ENTREGA.search(linha)
            if m:
                dt_entrega = m.group(1).strip()

    # ── Linhas de pneus ──────────────────────────────────────────────────────
    pneus = []
    for linha in linhas:
        resultado = _parsear_linha_pneu(linha)
        if resultado is None:
            continue

        nrserie, modelo, desenho, medida = resultado

        pneus.append({
            'NRORDEM':      nr_pedido,   # mesmo Nr. Pedido para todos os pneus da coleta
            'CLIENTE':      cliente,
            'NRSERIE':      nrserie,
            'DESENHO':      f"{modelo} {desenho} {medida}".strip(),
            'STATUS':       'Aguardando',
            'DATA_ENTRADA': dt_emissao,
            'DATA_SAIDA':   dt_entrega,
        })

    if not pneus:
        raise ValueError(
            "Nenhum pneu encontrado no PDF.\n"
            "Verifique se o layout segue o padrão: Nr.Série  Modelo  Desenho  Medida\n\n"
            f"Texto extraído (500 chars):\n{texto[:500]}"
        )

    from modules.database import COLUNAS
    df = pd.DataFrame(pneus)
    for col in COLUNAS:
        if col not in df.columns:
            df[col] = ''
    return df[COLUNAS]


def verificar_dependencias() -> tuple[bool, str]:
    if PDFPLUMBER_OK:
        return True, "pdfplumber instalado ✅"
    return False, "pdfplumber não instalado."
