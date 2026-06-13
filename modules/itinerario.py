"""
Tela — Itinerário de Entrega e Coleta.
Roteirização do caminhão integrada ao PPCP.
"""
import streamlit as st
import pandas as pd
import datetime
import json
from pathlib import Path

_BASE_DIR    = Path(__file__).resolve().parent.parent
_ITIN_JSON   = _BASE_DIR / "data" / "itinerario.json"
_SCHEMA_ITIN = 1


def _itin_valido(it: dict) -> bool:
    if not isinstance(it, dict):
        return False
    if it.get('_schema') != _SCHEMA_ITIN:
        return False
    if 'paradas' not in it or not isinstance(it['paradas'], list):
        return False
    return True


def _salvar_itinerario(it: dict) -> None:
    it = dict(it)
    it['_schema'] = _SCHEMA_ITIN
    conteudo = json.dumps(it, ensure_ascii=False, indent=2)
    try:
        _ITIN_JSON.parent.mkdir(parents=True, exist_ok=True)
        _ITIN_JSON.write_text(conteudo, encoding='utf-8')
    except Exception:
        pass
    try:
        from modules.database import _modo_github, _github_cfg
        if not _modo_github():
            return
        import requests, base64
        token, repo, branch, _ = _github_cfg()
        url = f"https://api.github.com/repos/{repo}/contents/data/itinerario.json"
        headers = {'Authorization': f'token {token}'}
        conteudo_b64 = base64.b64encode(conteudo.encode('utf-8')).decode()
        r = requests.get(url, headers=headers, timeout=5)
        sha = r.json().get('sha') if r.status_code == 200 else None
        payload = {'message': 'Atualiza itinerario', 'content': conteudo_b64, 'branch': branch}
        if sha:
            payload['sha'] = sha
        requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


def _carregar_itinerario() -> dict | None:
    try:
        from modules.database import _modo_github, _github_cfg
        if _modo_github():
            import requests, base64
            token, repo, branch, _ = _github_cfg()
            url = f"https://api.github.com/repos/{repo}/contents/data/itinerario.json?ref={branch}"
            r = requests.get(url, headers={'Authorization': f'token {token}'}, timeout=5)
            if r.status_code == 200:
                conteudo = base64.b64decode(r.json()['content']).decode('utf-8')
                it = json.loads(conteudo)
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


def carregar_mapa_prioridade() -> dict[str, int]:
    """Retorna {nome_cliente: ordem_parada} do itinerário salvo.
    Usado por outros módulos (ex.: producao_diaria) para exibir prioridade."""
    it = _carregar_itinerario()
    if not it:
        return {}
    return {p['cliente']: i + 1 for i, p in enumerate(it.get('paradas', []))}


# ── Tela Principal ────────────────────────────────────────────────────────────

def tela_itinerario():
    st.title("🗺️ Itinerário de Entrega e Coleta")

    aba1, aba2 = st.tabs([
        "📋 Criar / Editar Itinerário",
        "📊 Painel do Dia",
    ])

    with aba1:
        _aba_editar()
    with aba2:
        _aba_painel()


# ── Aba 1: Criar / Editar ─────────────────────────────────────────────────────

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
    motorista = col_m.text_input("Motorista:", value=it_salvo.get('motorista', '') if it_salvo else '')
    veiculo   = col_v.text_input("Veículo / Placa:", value=it_salvo.get('veiculo', '') if it_salvo else '')

    st.markdown("---")
    st.subheader("Paradas do Roteiro")

    # Inicializa paradas na session_state a partir do JSON salvo (somente uma vez)
    if 'itin_paradas' not in st.session_state:
        st.session_state.itin_paradas = list(it_salvo.get('paradas', [])) if it_salvo else []

    paradas = st.session_state.itin_paradas

    clientes_disponiveis = sorted(
        df_banco['CLIENTE'].replace('', pd.NA).dropna().unique().tolist()
    )

    with st.expander("➕ Adicionar Parada", expanded=(len(paradas) == 0)):
        col_c, col_t, col_h = st.columns([3, 2, 2])
        novo_cliente = col_c.selectbox("Cliente:", [''] + clientes_disponiveis, key='itin_novo_cliente')
        novo_tipo    = col_t.selectbox("Tipo:", ['Entrega', 'Coleta', 'Entrega e Coleta'], key='itin_novo_tipo')
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
        st.info("Nenhuma parada adicionada. Use o formulário acima para montar o roteiro.")
    else:
        st.markdown(f"**{len(paradas)} parada(s) no roteiro** — use ↑↓ para reordenar:")

        for i, p in enumerate(paradas):
            col_n, col_c, col_t, col_h, col_up, col_dn, col_rm = st.columns(
                [0.5, 3, 2, 1.5, 0.5, 0.5, 0.5]
            )
            col_n.markdown(f"**{i + 1}.**")
            col_c.write(p['cliente'])
            col_t.write(p.get('tipo', ''))
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
        try:
            from modules.database import _modo_github, _github_cfg
            if _modo_github():
                import requests
                token, repo, branch, _ = _github_cfg()
                url = f"https://api.github.com/repos/{repo}/contents/data/itinerario.json"
                headers = {'Authorization': f'token {token}'}
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code == 200:
                    sha = r.json().get('sha')
                    requests.delete(
                        url,
                        json={'message': 'Remove itinerario', 'sha': sha, 'branch': branch},
                        headers=headers, timeout=10
                    )
        except Exception:
            pass
        st.rerun()


# ── Aba 2: Painel do Dia ──────────────────────────────────────────────────────

def _aba_painel():
    it = _carregar_itinerario()
    if not it:
        st.info(
            "Nenhum itinerário salvo. Monte o roteiro na aba "
            "**📋 Criar / Editar Itinerário**."
        )
        return

    df = st.session_state.bd_pneus

    st.markdown(f"### 🗓️ Roteiro de **{it.get('data', '—')}**")
    col_m, col_v = st.columns(2)
    if it.get('motorista'):
        col_m.markdown(f"**Motorista:** {it['motorista']}")
    if it.get('veiculo'):
        col_v.markdown(f"**Veículo:** {it['veiculo']}")

    st.markdown("---")

    paradas = it.get('paradas', [])
    if not paradas:
        st.warning("Itinerário sem paradas. Edite na aba anterior.")
        return

    # ── Tabela-resumo de todas as paradas ────────────────────────────────────
    resumo = []
    tot_aguard = tot_prod = tot_exped = 0

    for i, p in enumerate(paradas):
        cli    = p['cliente']
        os_cli = df[df['CLIENTE'] == cli]
        aguard = len(os_cli[os_cli['STATUS'] == 'Aguardando'])
        prod   = len(os_cli[os_cli['STATUS'] == 'Em Produção'])
        exped  = len(os_cli[os_cli['STATUS'] == 'Expedido'])
        total  = aguard + prod + exped

        pct = round((prod + exped) / total * 100) if total > 0 else 0

        if total == 0:
            situ = '❌ Sem OS no banco'
        elif pct == 100:
            situ = '✅ Pronto p/ expedir'
        elif prod > 0 and aguard == 0:
            situ = '🔄 Todos na linha'
        elif prod > 0:
            situ = '🔄 Em produção'
        else:
            situ = '⏳ Aguardando'

        tot_aguard += aguard
        tot_prod   += prod
        tot_exped  += exped

        resumo.append({
            'Parada':     i + 1,
            'Hora':       p.get('hora', '') or '—',
            'Cliente':    cli,
            'Tipo':       p.get('tipo', ''),
            'Aguard.':    aguard,
            'Na linha':   prod,
            'Expedido':   exped,
            '% Pronto':   f"{pct}%",
            'Situação':   situ,
        })

    st.dataframe(
        pd.DataFrame(resumo),
        hide_index=True,
        use_container_width=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("⏳ Total Aguardando", tot_aguard)
    c2.metric("🔄 Total Na Linha",   tot_prod)
    c3.metric("✅ Total Expedido",   tot_exped)

    # ── Detalhe por parada ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Detalhe por Parada")

    for i, p in enumerate(paradas):
        cli  = p['cliente']
        hora = p.get('hora', '') or ''
        tipo = p.get('tipo', '')
        obs  = p.get('obs', '') or ''

        os_cli = df[df['CLIENTE'] == cli]
        aguard = os_cli[os_cli['STATUS'] == 'Aguardando']
        prod   = os_cli[os_cli['STATUS'] == 'Em Produção']
        exped  = os_cli[os_cli['STATUS'] == 'Expedido']
        total  = len(os_cli)

        pct    = round((len(prod) + len(exped)) / total * 100) if total > 0 else 0
        emoji  = '✅' if pct == 100 else ('🔄' if pct >= 50 else '⏳')
        titulo = f"{emoji} Parada {i + 1}"
        if hora:
            titulo += f" — {hora}"
        titulo += f" | {cli} ({tipo})"

        with st.expander(titulo, expanded=(pct < 100)):
            if obs:
                st.caption(f"📝 {obs}")

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total de OS",    total)
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
