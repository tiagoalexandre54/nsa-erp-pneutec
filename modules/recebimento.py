"""
Tela 5 — Recebimento de Pneus / Controle de Pallets.

Layout fixo:
  8 fileiras (A–H) × 5 pallets por fileira = 40 pallets
  Capacidade: 8 pneus por pallet → 320 pneus no total
"""
import streamlit as st
import pandas as pd
from modules.database import CAMINHO_CSV

# ── Constantes de layout ──────────────────────────────────────────────────────
FILEIRAS       = list("ABCDEFGH")   # 8 fileiras
PALLETS_LINHA  = 5                  # pallets por fileira
CAP_PALLET     = 8                  # pneus por pallet (altura)
TOTAL_PALLETS  = len(FILEIRAS) * PALLETS_LINHA  # 40

TODOS_PALLETS = [f"{f}{p}" for f in FILEIRAS for p in range(1, PALLETS_LINHA + 1)]
# ['A1','A2','A3','A4','A5','B1',...,'H5']


def _rastrear_os():
    """
    Campo de rastreamento: bipa o NRORDEM e mostra
    a qual coleta pertence + localização de todos os pneus.
    """
    df = st.session_state.bd_pneus

    if 'rastrear_key' not in st.session_state:
        st.session_state.rastrear_key = 0

    col_input, col_limpar = st.columns([4, 1])
    nrordem = col_input.text_input(
        "🔍 Bipe ou digite o NRORDEM para rastrear:",
        key=f"rastrear_{st.session_state.rastrear_key}",
        placeholder="Ex: 366488 ou 1615078..."
    )
    if col_limpar.button("✖ Limpar", key="btn_limpar_rastrear"):
        st.session_state.rastrear_key += 1
        st.rerun()

    if not nrordem:
        return

    nrordem = nrordem.strip()

    # Busca todas as OS com esse NRORDEM
    mask = df['NRORDEM'] == nrordem
    encontrados = df[mask].copy()

    if encontrados.empty:
        # Tenta busca parcial
        mask_parcial = df['NRORDEM'].str.contains(nrordem, case=False, na=False)
        encontrados = df[mask_parcial].copy()
        if encontrados.empty:
            st.error(f"❌ Nenhuma OS encontrada com NRORDEM **{nrordem}**.")
            return
        st.info(f"Busca parcial — mostrando OS que contêm **'{nrordem}'**")

    # ── Cabeçalho da coleta ──────────────────────────────────────────────────
    cliente      = encontrados['CLIENTE'].iloc[0]
    data_coleta  = encontrados['DATA_ENTRADA'].iloc[0]
    data_entrega = encontrados['DATA_SAIDA'].iloc[0]
    total_pneus  = len(encontrados)

    # Conta por status
    status_count = encontrados['STATUS'].value_counts().to_dict()
    aguard = status_count.get('Aguardando', 0)
    prod   = status_count.get('Em Produção', 0)
    exped  = status_count.get('Expedido', 0)

    st.markdown(
        f"""
        <div style="background:#e8f0fe;border:2px solid #003366;border-radius:10px;
                    padding:16px;margin:8px 0 16px 0;">
          <h4 style="color:#003366;margin:0 0 8px 0;">
            📦 Coleta encontrada — OS: <b>{nrordem}</b>
          </h4>
          <div style="display:flex;gap:32px;flex-wrap:wrap;">
            <div><b>Cliente:</b> {cliente}</div>
            <div><b>Data Coleta:</b> {data_coleta or '—'}</div>
            <div><b>Entrega Prev.:</b> {data_entrega or '—'}</div>
            <div><b>Total de Pneus:</b> {total_pneus}</div>
          </div>
          <div style="display:flex;gap:16px;margin-top:8px;">
            <span style="color:#856404;">🟡 Aguardando: <b>{aguard}</b></span>
            <span style="color:#004085;">🔵 Em Produção: <b>{prod}</b></span>
            <span style="color:#155724;">🟢 Expedido: <b>{exped}</b></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── Localização de cada pneu ─────────────────────────────────────────────
    st.markdown("**📍 Localização de cada pneu:**")

    if 'LOCAL_PALLET' not in encontrados.columns:
        encontrados['LOCAL_PALLET'] = ''

    encontrados['LOCAL_PALLET'] = encontrados['LOCAL_PALLET'].astype(str).str.strip().replace('nan','')

    def _icone_status(s):
        return {'Aguardando':'🟡','Em Produção':'🔵','Expedido':'🟢'}.get(s,'⚪')

    def _local(row):
        p = row['LOCAL_PALLET']
        if p:
            return f"📦 Pallet **{p}**"
        return "⚠️ Sem pallet atribuído"

    exibir = encontrados[['NRSERIE','DESENHO','STATUS','LOCAL_PALLET','DATA_ENTRADA','DATA_SAIDA']].copy()
    exibir['Status']   = exibir['STATUS'].apply(lambda s: f"{_icone_status(s)} {s}")
    exibir['Pallet']   = exibir['LOCAL_PALLET'].apply(lambda p: f"📦 {p}" if p else "⚠️ Sem pallet")
    exibir = exibir.rename(columns={
        'NRSERIE':       'Nº Série',
        'DESENHO':       'Desenho',
        'DATA_ENTRADA':  'Data Coleta',
        'DATA_SAIDA':    'Entrega Prev.',
    })

    st.dataframe(
        exibir[['Nº Série','Desenho','Status','Pallet','Data Coleta','Entrega Prev.']],
        use_container_width=True,
        hide_index=True
    )

    # ── Alerta se houver pneus sem pallet ────────────────────────────────────
    sem_pallet = encontrados[encontrados['LOCAL_PALLET'] == '']
    if not sem_pallet.empty:
        st.warning(
            f"⚠️ **{len(sem_pallet)} pneu(s)** desta coleta ainda não têm pallet atribuído. "
            f"Use a seção **📷 Receber por QR Code** abaixo para alocar."
        )

    st.markdown("---")


def _garantir_coluna():
    df = st.session_state.bd_pneus
    if 'LOCAL_PALLET' not in df.columns:
        df['LOCAL_PALLET'] = ''
        st.session_state.bd_pneus = df


def _salvar():
    from modules.database import salvar_dados
    salvar_dados(st.session_state.bd_pneus)


def _bipe_recebimento(resumo: dict):
    """
    Recebe pneus bipando o NRORDEM (QR Code / código de barras da OS).
    Fluxo:
      1. Seleciona pallet de destino
      2. Bipa o NRORDEM — o sistema localiza a OS
      3. Atribui ao pallet com um clique (ou automaticamente)
    """
    df = st.session_state.bd_pneus

    st.info("📷 Selecione o pallet de destino e bipe o QR Code da Ordem de Serviço.")

    col_pallet, col_bipe = st.columns([1, 2])

    # Pallet de destino
    def _label(p):
        info = resumo.get(p)
        qtd  = info['qtd'] if info else 0
        flag = " ⚠️ CHEIO" if qtd >= CAP_PALLET else ""
        return f"Pallet {p}  [{qtd}/{CAP_PALLET}]{flag}"

    pallet_bipe = col_pallet.selectbox(
        "Pallet de destino:",
        TODOS_PALLETS,
        format_func=_label,
        key="bipe_pallet_dest"
    )

    # Rotação de key para limpar campo após bipe
    if 'receb_bipe_key' not in st.session_state:
        st.session_state.receb_bipe_key = 0

    nrordem_bipado = col_bipe.text_input(
        "Bipe o QR Code / NRORDEM:",
        key=f"bipe_receb_{st.session_state.receb_bipe_key}",
        placeholder="Aguardando leitura do código de barras..."
    )

    if nrordem_bipado:
        nrordem_bipado = nrordem_bipado.strip()
        idx_lista = df.index[df['NRORDEM'] == nrordem_bipado].tolist()

        if not idx_lista:
            st.error(f"❌ NRORDEM **{nrordem_bipado}** não encontrado no sistema.")
        else:
            # Verifica capacidade do pallet
            info_dest = resumo.get(pallet_bipe, {})
            qtd_dest  = info_dest.get('qtd', 0)

            if qtd_dest >= CAP_PALLET:
                st.error(f"🛑 Pallet **{pallet_bipe}** está cheio! Escolha outro pallet.")
            else:
                # Mostra todos os pneus encontrados com esse NRORDEM
                df_os = df.loc[idx_lista, ['NRORDEM','CLIENTE','NRSERIE','DESENHO','STATUS','LOCAL_PALLET']].copy()

                # Converte LOCAL_PALLET para string segura antes de filtrar
                df_os['LOCAL_PALLET'] = df_os['LOCAL_PALLET'].astype(str).str.strip().replace('nan', '')
                sem_pallet = df_os[df_os['LOCAL_PALLET'] == '']
                com_pallet = df_os[df_os['LOCAL_PALLET'] != '']

                st.markdown(f"**OS encontrada — {len(df_os)} pneu(s) — {df.at[idx_lista[0], 'CLIENTE']}**")

                if not sem_pallet.empty:
                    st.dataframe(
                        sem_pallet[['NRORDEM','CLIENTE','NRSERIE','DESENHO','STATUS']],
                        use_container_width=True, hide_index=True
                    )

                    espaco_livre = CAP_PALLET - qtd_dest
                    vai_caber    = len(sem_pallet) <= espaco_livre

                    if not vai_caber:
                        st.warning(
                            f"⚠️ {len(sem_pallet)} pneus mas só cabem {espaco_livre} no Pallet {pallet_bipe}. "
                            f"Apenas os primeiros {espaco_livre} serão alocados."
                        )

                    if st.button(
                        f"📌 Alocar {min(len(sem_pallet), espaco_livre)} pneu(s) → Pallet {pallet_bipe}",
                        key="btn_confirmar_bipe",
                        type="primary"
                    ):
                        alocar_idx = sem_pallet.index[:espaco_livre]
                        st.session_state.bd_pneus.loc[alocar_idx, 'LOCAL_PALLET'] = pallet_bipe
                        _salvar()
                        st.session_state.msg_bipe_receb = (
                            f"✅ {len(alocar_idx)} pneu(s) de **{df.at[idx_lista[0], 'CLIENTE']}** "
                            f"alocado(s) no **Pallet {pallet_bipe}**!"
                        )
                        st.session_state.receb_bipe_key += 1
                        st.rerun()

                if not com_pallet.empty:
                    pallets_ja = ', '.join(
                        str(p) for p in com_pallet['LOCAL_PALLET'].unique()
                        if str(p).strip() not in ('', 'nan')
                    )
                    st.caption(
                        f"ℹ️ {len(com_pallet)} pneu(s) desta OS já estão alocados: {pallets_ja}"
                    )

    # Feedback após bipe
    if st.session_state.get('msg_bipe_receb'):
        st.success(st.session_state.msg_bipe_receb)
        st.session_state.msg_bipe_receb = None


def _formulario_inserir_coleta(resumo: dict):
    """
    Formulário para registrar manualmente pneus recebidos,
    atribuindo diretamente ao pallet de destino.
    """
    import datetime
    from modules.database import COLUNAS

    df = st.session_state.bd_pneus

    with st.expander("➕ Preencher nova coleta manualmente", expanded=False):

        with st.form("form_nova_coleta", clear_on_submit=True):
            st.markdown("**Dados da coleta**")

            c1, c2 = st.columns(2)
            cliente  = c1.text_input("Cliente *", placeholder="Ex: BRASPRESS TRANSPORTES")
            nrordem  = c2.text_input("Nº Pedido (NRORDEM) *", placeholder="Ex: 366488")

            c3, c4 = st.columns(2)
            nrserie  = c3.text_input("Nº Série do Pneu *", placeholder="Ex: 17399")
            desenho  = c4.text_input("Desenho / Modelo", placeholder="Ex: DUNLOP SP176 DVUM-3B 275/80R22.5")

            c5, c6 = st.columns(2)
            data_coleta  = c5.date_input("Data da Coleta *",  value=datetime.date.today())
            data_entrega = c6.date_input("Data Entrega Prev.", value=datetime.date.today())

            st.markdown("**Destino no galpão**")

            # Monta opções de pallet com indicador de capacidade
            def _label_pallet(p):
                info = resumo.get(p)
                qtd  = info['qtd'] if info else 0
                flag = " ⚠️ CHEIO" if qtd >= CAP_PALLET else ""
                return f"Pallet {p}  [{qtd}/{CAP_PALLET}]{flag}"

            opcoes_pallets = TODOS_PALLETS
            pallet_destino = st.selectbox(
                "Pallet de destino *",
                opcoes_pallets,
                format_func=_label_pallet,
                key="form_pallet_dest"
            )

            observacao = st.text_input("Observação (opcional)", placeholder="Ex: Pneus de recapagem urgente")

            submitted = st.form_submit_button("📌 Registrar no Pallet", type="primary", use_container_width=True)

        if submitted:
            erros = []
            if not cliente.strip():  erros.append("Cliente obrigatório.")
            if not nrordem.strip():  erros.append("Nº Pedido obrigatório.")
            if not nrserie.strip():  erros.append("Nº Série obrigatório.")

            # Verifica capacidade
            info_dest = resumo.get(pallet_destino, {})
            if info_dest.get('qtd', 0) >= CAP_PALLET:
                erros.append(f"Pallet {pallet_destino} está cheio ({CAP_PALLET}/{CAP_PALLET}).")

            # Verifica duplicata NRORDEM + NRSERIE
            chave_existe = (
                (df['NRORDEM'] == nrordem.strip()) &
                (df['NRSERIE'] == nrserie.strip())
            ).any()
            if chave_existe:
                erros.append(f"Pneu com NRORDEM {nrordem} e série {nrserie} já está cadastrado.")

            if erros:
                for e in erros:
                    st.error(f"❌ {e}")
            else:
                nova_linha = {
                    'NRORDEM':       nrordem.strip(),
                    'CLIENTE':       cliente.strip(),
                    'NRSERIE':       nrserie.strip(),
                    'DESENHO':       desenho.strip(),
                    'STATUS':        'Aguardando',
                    'DATA_ENTRADA':  data_coleta.strftime("%d/%m/%Y"),
                    'DATA_SAIDA':    data_entrega.strftime("%d/%m/%Y"),
                    'LOCAL_PALLET':  pallet_destino,
                }
                # Garante todas as colunas
                for col in COLUNAS:
                    if col not in nova_linha:
                        nova_linha[col] = ''
                if 'LOCAL_PALLET' not in COLUNAS:
                    nova_linha['LOCAL_PALLET'] = pallet_destino

                st.session_state.bd_pneus = pd.concat(
                    [df, pd.DataFrame([nova_linha])],
                    ignore_index=True
                )
                _salvar()
                st.success(
                    f"✅ Pneu **{nrserie.strip()}** de **{cliente.strip()}** "
                    f"registrado no **Pallet {pallet_destino}**!"
                )
                st.rerun()


# ── Funções de impressão ──────────────────────────────────────────────────────

_CSS_BASE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Inter, Arial, sans-serif; font-size: 12px; color: #111; background: #fff; }
  h1  { font-size: 18px; margin-bottom: 4px; }
  h2  { font-size: 14px; margin: 12px 0 6px; border-bottom: 2px solid #003366; padding-bottom: 4px; }
  .sub { color: #555; font-size: 11px; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 11px; }
  th { background: #003366; color: #fff; padding: 5px 6px; text-align: left; }
  td { padding: 4px 6px; border-bottom: 1px solid #ddd; }
  tr:nth-child(even) td { background: #f5f7fa; }
  .grid { display: grid; gap: 6px; }
  .card { border-radius: 6px; padding: 8px; text-align: center; border: 2px solid; }
  .card-livre  { border-color: #ccc; background: #f8f8f8; color: #aaa; }
  .card-ocupado{ border-color: #003366; background: #e8f0fe; color: #003366; }
  .card-cheio  { border-color: #c00; background: #ffe8e8; color: #c00; }
  .barra       { font-family: monospace; letter-spacing: 1px; font-size: 11px; }
  .fileira-label { font-weight: 700; font-size: 14px; display: flex; align-items: center;
                   justify-content: center; background: #003366; color: #fff;
                   border-radius: 4px; padding: 6px; }
  @media print {
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .no-print { display: none !important; }
    @page { margin: 1cm; }
  }
</style>
"""

_HEADER_HTML = """
<div style="display:flex;justify-content:space-between;align-items:center;
            border-bottom:3px solid #003366;padding-bottom:8px;margin-bottom:12px;">
  <div>
    <h1 style="color:#003366;">NSA PNEUTEC — Controle de Pallets</h1>
    <div class="sub">{subtitulo} &nbsp;|&nbsp; Gerado em: {data}</div>
  </div>
  <div style="font-size:32px;color:#003366;">🔧</div>
</div>
"""


def _header(subtitulo: str) -> str:
    import datetime
    data = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    return _HEADER_HTML.format(subtitulo=subtitulo, data=data)


def _abrir_impressao(html: str, nome_arquivo: str = "relatorio_pallet"):
    """
    Gera o HTML completo e oferece como download + botão para abrir direto.
    Estratégia dupla:
      1. st.download_button — baixa o .html, usuário abre e imprime (Ctrl+P)
      2. Abre via os.startfile() no Windows — abre no navegador padrão direto
    """
    import datetime, os, tempfile

    full = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'>{_CSS_BASE}
<title>NSA Pneutec — {nome_arquivo}</title>
</head><body>
{html}
<script>window.onload = function(){{ window.print(); }}</script>
</body></html>"""

    # Salva em arquivo temporário e abre no navegador padrão do Windows
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.html',
        prefix=f'nsa_{nome_arquivo}_',
        mode='w',
        encoding='utf-8'
    )
    tmp.write(full)
    tmp.close()

    try:
        os.startfile(tmp.name)
        st.success("✅ Abrindo no navegador... Use **Ctrl+P** para imprimir ou salvar como PDF.")
    except Exception:
        # Fallback: download button
        st.download_button(
            label="⬇️ Baixar HTML para imprimir",
            data=full.encode('utf-8'),
            file_name=f"nsa_{nome_arquivo}_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}.html",
            mime="text/html",
            key=f"dl_{nome_arquivo}_{id(html)}"
        )
        st.info("Abra o arquivo baixado no navegador e use Ctrl+P para imprimir.")


def _html_pallet(pallet: str, df_pallet: pd.DataFrame) -> str:
    """HTML de um único pallet para impressão."""
    clientes = ', '.join(df_pallet['CLIENTE'].unique())
    qtd = len(df_pallet)
    barra = "█" * qtd + "░" * (CAP_PALLET - qtd)

    linhas = ""
    for idx, (_, row) in enumerate(df_pallet.iterrows(), 1):
        linhas += f"""
        <tr>
          <td>{idx}</td>
          <td>{row['NRORDEM']}</td>
          <td>{row['CLIENTE']}</td>
          <td>{row['NRSERIE']}</td>
          <td>{row['DESENHO']}</td>
          <td>{row['STATUS']}</td>
          <td>{row['DATA_ENTRADA']}</td>
          <td>{row['DATA_SAIDA']}</td>
        </tr>"""

    return f"""
    {_header(f"Pallet {pallet}")}
    <div style="display:flex;gap:24px;margin-bottom:16px;align-items:center;">
      <div style="background:#e8f0fe;border:2px solid #003366;border-radius:8px;
                  padding:16px 24px;text-align:center;min-width:120px;">
        <div style="font-size:28px;font-weight:700;color:#003366;">{pallet}</div>
        <div style="font-family:monospace;font-size:14px;color:#003366;">{barra}</div>
        <div style="color:#003366;">{qtd}/{CAP_PALLET} pneus</div>
      </div>
      <div>
        <div><b>Clientes:</b> {clientes}</div>
        <div><b>Ocupação:</b> {qtd}/{CAP_PALLET} ({qtd/CAP_PALLET*100:.0f}%)</div>
      </div>
    </div>
    <h2>Pneus no Pallet</h2>
    <table>
      <thead><tr>
        <th>#</th><th>NRORDEM</th><th>Cliente</th><th>Série</th>
        <th>Desenho</th><th>Status</th><th>Data Coleta</th><th>Entrega Prev.</th>
      </tr></thead>
      <tbody>{linhas}</tbody>
    </table>
    """


def _html_mapa_galpao(resumo: dict) -> str:
    """HTML do mapa completo do galpão (visão geral)."""
    # Cabeçalho colunas
    header_cols = "".join(
        f'<th style="text-align:center;">Pos. {p}</th>'
        for p in range(1, PALLETS_LINHA + 1)
    )

    linhas_grid = ""
    for fileira in FILEIRAS:
        cells = f'<td><div class="fileira-label">{fileira}</div></td>'
        for pos in range(1, PALLETS_LINHA + 1):
            pallet = f"{fileira}{pos}"
            info   = resumo.get(pallet)
            if info:
                qtd   = info['qtd']
                cheio = qtd >= CAP_PALLET
                cls   = "card-cheio" if cheio else "card-ocupado"
                barra = "█" * qtd + "░" * (CAP_PALLET - qtd)
                clts  = "<br>".join(sorted(info['clientes']))[:40]
                cells += f"""<td>
                  <div class="card {cls}">
                    <b>{pallet}</b><br>
                    <small>{clts}</small><br>
                    <span class="barra">{barra}</span><br>
                    <small>{qtd}/{CAP_PALLET}</small>
                  </div></td>"""
            else:
                cells += f"""<td>
                  <div class="card card-livre">
                    <b>{pallet}</b><br>
                    <small>Livre</small><br>
                    <span class="barra">{"░" * CAP_PALLET}</span><br>
                    <small>0/{CAP_PALLET}</small>
                  </div></td>"""
        linhas_grid += f"<tr>{cells}</tr>"

    ocupados = len(resumo)
    total_pneus = sum(v['qtd'] for v in resumo.values())

    return f"""
    {_header("Mapa do Galpão")}
    <div style="display:flex;gap:24px;margin-bottom:12px;">
      <span>📦 <b>Pallets ocupados:</b> {ocupados}/{TOTAL_PALLETS}</span>
      <span>🔵 <b>Pneus no galpão:</b> {total_pneus}/{TOTAL_PALLETS * CAP_PALLET}</span>
    </div>
    <table style="table-layout:fixed;">
      <thead><tr><th style="width:40px;">Fil.</th>{header_cols}</tr></thead>
      <tbody>{linhas_grid}</tbody>
    </table>
    <div style="margin-top:8px;font-size:11px;color:#555;">
      ■ Azul = Ocupado &nbsp;|&nbsp; ■ Vermelho = Cheio &nbsp;|&nbsp; □ Cinza = Livre
    </div>
    """


def _html_todos_pallets(df: pd.DataFrame, resumo: dict) -> str:
    """HTML com a lista detalhada de todos os pallets ocupados."""
    pallets_ord = sorted(
        resumo.keys(),
        key=lambda x: (x[0], int(x[1:]) if x[1:].isdigit() else 99)
    )

    blocos = ""
    for pallet in pallets_ord:
        df_p = df[df['LOCAL_PALLET'] == pallet][[
            'NRORDEM', 'CLIENTE', 'NRSERIE', 'DESENHO', 'STATUS', 'DATA_ENTRADA', 'DATA_SAIDA'
        ]]
        blocos += _html_pallet(pallet, df_p)
        blocos += '<div style="page-break-after:always;"></div>'

    total_pneus = sum(v['qtd'] for v in resumo.values())
    return f"""
    {_header(f"Todos os Pallets — {len(pallets_ord)} ocupados / {total_pneus} pneus")}
    {blocos}
    """


def _resumo_pallets(df: pd.DataFrame) -> dict:
    """Retorna {pallet: {clientes, qtd, status}} para pallets ocupados."""
    resumo = {}
    if 'LOCAL_PALLET' not in df.columns:
        return resumo
    # Converte para string antes de filtrar — evita TypeError com NaN (float)
    df = df.copy()
    df['LOCAL_PALLET'] = df['LOCAL_PALLET'].astype(str).str.strip()
    col = df[~df['LOCAL_PALLET'].isin(['', 'nan', 'None'])]
    for _, row in col.iterrows():
        p = row['LOCAL_PALLET']
        if not p:
            continue
        if p not in resumo:
            resumo[p] = {'clientes': set(), 'qtd': 0, 'status': set()}
        resumo[p]['clientes'].add(str(row['CLIENTE']))
        resumo[p]['qtd'] += 1
        resumo[p]['status'].add(str(row['STATUS']))
    return resumo


def tela_recebimento():
    _garantir_coluna()
    st.title("📥 Recebimento de Pneus")

    df = st.session_state.bd_pneus
    resumo = _resumo_pallets(df)

    # ── Rastreamento rápido ──────────────────────────────────────────────────
    st.subheader("🔍 Rastrear OS")
    _rastrear_os()

    # ── Indicadores gerais ───────────────────────────────────────────────────
    total_pneus_em_pallet = sum(v['qtd'] for v in resumo.values())
    pallets_ocupados = len(resumo)
    pallets_livres   = TOTAL_PALLETS - pallets_ocupados
    capacidade_usada = total_pneus_em_pallet
    capacidade_total = TOTAL_PALLETS * CAP_PALLET

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pallets Ocupados",  f"{pallets_ocupados} / {TOTAL_PALLETS}")
    c2.metric("Pallets Livres",    pallets_livres)
    c3.metric("Pneus no Galpão",   f"{capacidade_usada} / {capacidade_total}")
    c4.metric("Capacidade Livre",  f"{capacidade_total - capacidade_usada} pneus")

    st.markdown("---")

    # ── Mapa visual ──────────────────────────────────────────────────────────
    st.subheader("🗺️ Mapa do Galpão")
    st.caption(f"8 fileiras (A–H) × 5 pallets × {CAP_PALLET} pneus = {capacidade_total} pneus")

    # Cabeçalho das colunas
    header = st.columns([1] + [2] * PALLETS_LINHA)
    header[0].markdown("**Fileira**")
    for p in range(1, PALLETS_LINHA + 1):
        header[p].markdown(f"<center><b>Pos. {p}</b></center>", unsafe_allow_html=True)

    for fileira in FILEIRAS:
        cols = st.columns([1] + [2] * PALLETS_LINHA)
        cols[0].markdown(f"<div style='padding-top:12px;font-weight:bold;font-size:18px;'>{fileira}</div>",
                         unsafe_allow_html=True)

        for pos in range(1, PALLETS_LINHA + 1):
            pallet = f"{fileira}{pos}"
            info   = resumo.get(pallet)

            if info:
                qtd  = info['qtd']
                perc = qtd / CAP_PALLET

                # Cor baseada na ocupação e status
                if perc >= 1.0:
                    cor, borda, txt = "#dc3545", "#721c24", "#fff"   # vermelho = cheio
                elif 'Em Produção' in info['status']:
                    cor, borda, txt = "#cce5ff", "#004085", "#004085"
                elif 'Expedido' in info['status'] and len(info['status']) == 1:
                    cor, borda, txt = "#d4edda", "#155724", "#155724"
                else:
                    cor, borda, txt = "#fff3cd", "#856404", "#856404"  # amarelo = aguardando

                clientes_str = "<br>".join(sorted(info['clientes']))[:50]
                barra = "█" * qtd + "░" * (CAP_PALLET - qtd)

                cols[pos].markdown(
                    f"""<div style="background:{cor};border:2px solid {borda};border-radius:6px;
                                    padding:8px 6px;text-align:center;min-height:80px;">
                        <b style="color:{txt};font-size:13px;">{pallet}</b><br>
                        <small style="color:{txt};">{clientes_str}</small><br>
                        <small style="color:{txt};font-family:monospace;">{barra}</small><br>
                        <small style="color:{txt};">{qtd}/{CAP_PALLET}</small>
                    </div>""",
                    unsafe_allow_html=True
                )
            else:
                cols[pos].markdown(
                    f"""<div style="background:#1e1e1e;border:2px dashed #444;border-radius:6px;
                                    padding:8px 6px;text-align:center;min-height:80px;">
                        <b style="color:#666;">{pallet}</b><br>
                        <small style="color:#444;">Livre</small><br>
                        <small style="color:#333;font-family:monospace;">{"░" * CAP_PALLET}</small><br>
                        <small style="color:#444;">0/{CAP_PALLET}</small>
                    </div>""",
                    unsafe_allow_html=True
                )

    # Legenda
    st.markdown("""
    <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap;">
      <span>⬜ Livre</span>
      <span style="color:#856404;">🟡 Aguardando</span>
      <span style="color:#004085;">🔵 Em Produção</span>
      <span style="color:#155724;">🟢 Expedido</span>
      <span style="color:#dc3545;">🔴 Cheio</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Bipe de QR Code / Código de Barras ──────────────────────────────────
    st.subheader("📷 Receber por QR Code / Código de Barras")
    _bipe_recebimento(resumo)

    st.markdown("---")

    # ── Inserir coleta manualmente ───────────────────────────────────────────
    st.subheader("➕ Inserir Coleta Manualmente")
    _formulario_inserir_coleta(resumo)

    st.markdown("---")

    # ── Direcionar coleta para pallet ────────────────────────────────────────
    st.subheader("📦 Direcionar Coleta Importada para Pallet")

    aguardando = df[df['STATUS'] == 'Aguardando'].copy()

    if aguardando.empty:
        st.info("Nenhuma coleta aguardando recebimento.")
    else:
        coletas = aguardando.groupby(['CLIENTE', 'NRORDEM']).agg(
            Pneus        =('NRSERIE',      'count'),
            Data_Coleta  =('DATA_ENTRADA', 'first'),
            Entrega      =('DATA_SAIDA',   'first'),
            Pallet_Atual =('LOCAL_PALLET', 'first')
        ).reset_index()

        for _, coleta in coletas.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 2])

                pallet_atual = str(coleta['Pallet_Atual']).strip() \
                    if pd.notna(coleta['Pallet_Atual']) else ''
                tag_pallet = f" → **{pallet_atual}**" if pallet_atual else ""

                c1.markdown(
                    f"**{coleta['CLIENTE']}**{tag_pallet}  \n"
                    f"OS: `{coleta['NRORDEM']}` | {coleta['Pneus']} pneu(s)"
                )
                c2.markdown(f"<small>Coleta:<br>{coleta['Data_Coleta']}</small>", unsafe_allow_html=True)
                c3.markdown(f"<small>Entrega:<br>{coleta['Entrega']}</small>",    unsafe_allow_html=True)

                # Monta opções com indicação de ocupação
                def _label(p):
                    info = resumo.get(p)
                    if info:
                        qtd = info['qtd']
                        return f"{p}  [{qtd}/{CAP_PALLET}]" + (" ⚠️ CHEIO" if qtd >= CAP_PALLET else "")
                    return f"{p}  [0/{CAP_PALLET}]"

                opcoes = ['-- Selecione --'] + [_label(p) for p in TODOS_PALLETS]
                idx_atual = 0
                if pallet_atual:
                    for idx, op in enumerate(opcoes):
                        if op.startswith(pallet_atual):
                            idx_atual = idx
                            break

                key_sel = f"sel_{coleta['CLIENTE']}_{coleta['NRORDEM']}".replace(' ', '_').replace('.', '')
                escolha = c4.selectbox("Pallet:", opcoes, index=idx_atual, key=key_sel)

                if escolha != '-- Selecione --':
                    pallet_cod = escolha.split()[0]   # ex: "A3" de "A3  [2/8]"
                    info_dest  = resumo.get(pallet_cod, {})
                    qtd_dest   = info_dest.get('qtd', 0)
                    sobra      = CAP_PALLET - qtd_dest

                    if qtd_dest >= CAP_PALLET:
                        c4.error("Pallet cheio!")
                    elif coleta['Pneus'] > sobra:
                        c4.warning(f"Cabem só {sobra} pneus neste pallet.")

                    if pallet_cod != pallet_atual:
                        key_btn = f"btn_{coleta['CLIENTE']}_{coleta['NRORDEM']}".replace(' ', '_').replace('.', '')
                        if c4.button("📌 Confirmar", key=key_btn):
                            mask = (
                                (df['CLIENTE'] == coleta['CLIENTE']) &
                                (df['NRORDEM'] == coleta['NRORDEM']) &
                                (df['STATUS']  == 'Aguardando')
                            )
                            st.session_state.bd_pneus.loc[mask, 'LOCAL_PALLET'] = pallet_cod
                            _salvar()
                            st.success(f"✅ {coleta['CLIENTE']} → Pallet **{pallet_cod}**")
                            st.rerun()

                st.markdown("<hr style='margin:4px 0;opacity:0.15'>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Detalhamento por pallet ──────────────────────────────────────────────
    st.subheader("📋 Ver conteúdo de um pallet")

    pallets_com_pneus = sorted(
        resumo.keys(),
        key=lambda x: (x[0], int(x[1:]) if x[1:].isdigit() else 99)
    )

    if not pallets_com_pneus:
        st.info("Nenhum pallet ocupado ainda.")
    else:
        pallet_ver = st.selectbox(
            "Selecione o pallet:",
            pallets_com_pneus,
            format_func=lambda p: f"{p}  —  {resumo[p]['qtd']}/{CAP_PALLET} pneus  |  "
                                  + ', '.join(sorted(resumo[p]['clientes'])),
            key="sel_ver_pallet"
        )

        df_pallet = df[df['LOCAL_PALLET'] == pallet_ver][[
            'NRORDEM', 'CLIENTE', 'NRSERIE', 'DESENHO', 'STATUS', 'DATA_ENTRADA', 'DATA_SAIDA'
        ]].copy()

        st.dataframe(df_pallet, use_container_width=True, hide_index=True)

        qtd = len(df_pallet)
        perc = qtd / CAP_PALLET * 100
        st.progress(int(perc), text=f"Ocupação: {qtd}/{CAP_PALLET} pneus ({perc:.0f}%)")

        col_lib, col_imp = st.columns(2)

        if col_lib.button(f"🔓 Liberar Pallet {pallet_ver}", key="btn_liberar", type="secondary"):
            st.session_state.bd_pneus.loc[
                st.session_state.bd_pneus['LOCAL_PALLET'] == pallet_ver, 'LOCAL_PALLET'
            ] = ''
            _salvar()
            st.success(f"Pallet {pallet_ver} liberado!")
            st.rerun()

        if col_imp.button(f"🖨️ Imprimir Pallet {pallet_ver}", key="btn_imp_pallet"):
            html = _html_pallet(pallet_ver, df_pallet)
            _abrir_impressao(html, nome_arquivo=f"pallet_{pallet_ver}")

    st.markdown("---")

    # ── Impressão geral do mapa ──────────────────────────────────────────────
    st.subheader("🖨️ Impressão")
    c1, c2 = st.columns(2)

    if c1.button("🖨️ Imprimir Mapa do Galpão", key="btn_imp_mapa", type="primary"):
        html = _html_mapa_galpao(resumo)
        _abrir_impressao(html, nome_arquivo="mapa_galpao")

    if c2.button("🖨️ Imprimir Todos os Pallets", key="btn_imp_todos", type="primary"):
        html = _html_todos_pallets(df, resumo)
        _abrir_impressao(html, nome_arquivo="todos_pallets")
