"""
Módulo de Acesso Mobile — gera QR Code e link para Android/celular.
"""
import streamlit as st
import socket
import os
from io import BytesIO


def _get_ip_local() -> str:
    """Retorna o IP local da máquina na rede Wi-Fi/LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _gerar_qr(url: str) -> bytes:
    """Gera imagem PNG do QR Code para a URL."""
    import qrcode
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#003366", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _iniciar_tunel_serveo(porta: int) -> str | None:
    """
    Inicia túnel via serveo.net usando SSH — sem conta, sem instalação extra.
    Usa arquivos temporários para capturar o output de forma confiável.
    """
    import subprocess, re, time, tempfile, os

    _encerrar_tunel()

    try:
        out_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w')
        err_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w')
        out_path = out_file.name
        err_path = err_file.name
        out_file.close()
        err_file.close()

        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ServerAliveInterval=30",
             "-o", "LogLevel=VERBOSE",
             "-R", f"80:localhost:{porta}", "serveo.net"],
            stdout=open(out_path, 'w'),
            stderr=open(err_path, 'w'),
        )

        # Aguarda e busca a URL nos arquivos de saída
        url = None
        for _ in range(15):  # até 15 segundos
            time.sleep(1)
            for path in [out_path, err_path]:
                try:
                    conteudo = open(path, 'r', errors='ignore').read()
                    m = re.search(r'https://\S+\.serveousercontent\.com', conteudo)
                    if m:
                        url = m.group(0).strip()
                        break
                except Exception:
                    pass
            if url:
                break

        if url:
            import streamlit as st
            st.session_state['_tunel_proc']     = proc
            st.session_state['_tunel_out_path'] = out_path
            st.session_state['_tunel_err_path'] = err_path
            return url
        else:
            proc.kill()
            return None

    except Exception:
        return None


def _encerrar_tunel():
    """Encerra o processo SSH do túnel se estiver rodando."""
    try:
        import streamlit as st
        proc = st.session_state.get('_tunel_proc')
        if proc:
            proc.kill()
            del st.session_state['_tunel_proc']
    except Exception:
        pass


def _esta_na_nuvem() -> bool:
    """Detecta se está rodando no Streamlit Cloud (Linux sem Wi-Fi local)."""
    try:
        import streamlit as st
        token = st.secrets.get("github", {}).get("token", "")
        return bool(token and token.strip())
    except Exception:
        return False


def painel_acesso_mobile(porta: int = 3001):
    """
    Exibe no sidebar o QR Code e links para acesso pelo celular.
    Na nuvem: mostra só a URL do próprio app.
    Local: mostra IP da rede + opção de link público.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📱 Acesso pelo Celular")

    # Na nuvem: mostra a própria URL pública do Streamlit Cloud
    if _esta_na_nuvem():
        try:
            url_nuvem = st.context.url if hasattr(st, 'context') else "Verifique a URL do seu navegador"
        except Exception:
            url_nuvem = "Acesse pela URL do seu navegador"
        st.sidebar.success("🌐 App rodando na nuvem!")
        st.sidebar.markdown("Acesse de qualquer lugar com a URL do navegador.")
        try:
            qr_bytes = _gerar_qr(url_nuvem if url_nuvem.startswith("http") else "https://nsa-erp-pneutec.streamlit.app")
            st.sidebar.image(qr_bytes, caption="QR Code do app", use_container_width=True)
        except Exception:
            pass
        return

    ip_local = _get_ip_local()
    url_local = f"http://{ip_local}:{porta}"

    # ── Opção 1: Wi-Fi local ────────────────────────────────────────────────
    st.sidebar.markdown("**📶 Mesma rede Wi-Fi:**")
    st.sidebar.code(url_local, language=None)

    try:
        qr_bytes = _gerar_qr(url_local)
        st.sidebar.image(qr_bytes, caption="Escaneie com o celular", use_container_width=True)
    except Exception:
        st.sidebar.info("Instale 'qrcode[pil]' para ver o QR Code.")

    # ── Opção 2: Link público via ngrok ─────────────────────────────────────
    st.sidebar.markdown("**🌐 Acesso externo (qualquer rede):**")

    chave_tunel = "ngrok_url"

    if st.sidebar.button("🔗 Gerar link público", key="btn_ngrok"):
        with st.sidebar:
            with st.spinner("Criando link... (aguarde ~10s)"):
                url_publica = _iniciar_tunel_serveo(porta)
        if url_publica:
            st.session_state[chave_tunel] = url_publica
        else:
            st.session_state[chave_tunel] = "ERRO"

    if chave_tunel in st.session_state:
        url_pub = st.session_state[chave_tunel]
        if url_pub == "ERRO":
            st.sidebar.warning(
                "Não foi possível criar o link público.\n\n"
                "Use o link Wi-Fi se estiver na mesma rede."
            )
        else:
            st.sidebar.success("Link ativo!")
            st.sidebar.code(url_pub, language=None)
            try:
                qr_pub = _gerar_qr(url_pub)
                st.sidebar.image(qr_pub, caption="Link externo — qualquer rede", use_container_width=True)
            except Exception:
                pass
            st.sidebar.caption("⚠️ Link expira quando o app for fechado.")

        if st.sidebar.button("❌ Encerrar link público", key="btn_stop_ngrok"):
            _encerrar_tunel()
            del st.session_state[chave_tunel]
            st.rerun()
