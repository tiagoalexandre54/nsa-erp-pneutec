"""
ERP Reformadora de Pneus — MES (Manufacturing Execution System)
Ponto de entrada da aplicação Streamlit.
"""
import streamlit as st

import os
from modules.database import carregar_dados
from modules.painel_pcp import tela_painel_pcp
from modules.entrada import tela_entrada
from modules.expedicao import tela_expedicao
from modules.relatorios import tela_relatorios
from modules.acesso_mobile import painel_acesso_mobile
from modules.recebimento import tela_recebimento

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")

# ── Configuração da página (deve ser o PRIMEIRO comando Streamlit) ───────────
st.set_page_config(
    page_title="ERP Reformadora — PPCP & Expedição",
    page_icon="🔧",
    layout="wide"
)

# ── Inicialização do banco de dados na sessão ────────────────────────────────
# Só carrega do disco na primeira execução da sessão; após isso usa a memória.
if 'bd_pneus' not in st.session_state:
    st.session_state.bd_pneus = carregar_dados()

# ── Sidebar ───────────────────────────────────────────────────────────────────
if os.path.exists(_LOGO_PATH):
    st.sidebar.image(_LOGO_PATH, use_container_width=True)
else:
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3063/3063822.png", width=100)
st.sidebar.markdown("### PPCP\nPlanejamento, Programação\ne Controle da Produção")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Selecione a Tela:",
    ["📊 Painel PPCP", "📥 Recebimento", "🏭 Entrada (Chão de Fábrica)", "🚚 Expedição (Carga)", "📈 Relatórios"]
)

st.sidebar.markdown("---")

total = len(st.session_state.bd_pneus)
aguard = len(st.session_state.bd_pneus[st.session_state.bd_pneus['STATUS'] == 'Aguardando'])
prod   = len(st.session_state.bd_pneus[st.session_state.bd_pneus['STATUS'] == 'Em Produção'])
exped  = len(st.session_state.bd_pneus[st.session_state.bd_pneus['STATUS'] == 'Expedido'])

st.sidebar.markdown(
    f"**OS Total:** {total}  \n"
    f"🟡 Aguardando: {aguard}  \n"
    f"🔵 Em Produção: {prod}  \n"
    f"🟢 Expedidos: {exped}"
)

painel_acesso_mobile(porta=3001)

# ── Roteamento ────────────────────────────────────────────────────────────────
if menu == "📊 Painel PPCP":
    tela_painel_pcp()
elif menu == "📥 Recebimento":
    tela_recebimento()
elif menu == "🏭 Entrada (Chão de Fábrica)":
    tela_entrada()
elif menu == "🚚 Expedição (Carga)":
    tela_expedicao()
elif menu == "📈 Relatórios":
    tela_relatorios()
