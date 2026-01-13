import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="NIYATI - SISTEMA", layout="wide")

@st.cache_resource
def get_engine():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configure os Secrets!")
        st.stop()
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_pre_ping=True)

engine = get_engine()

# --- 2. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Pedidos"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u_login = st.text_input("Login")
    u_senha = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT nivel_acesso, nome_loja FROM usuarios WHERE login = :u AND senha = :s"), {"u": u_login, "s": u_senha}).fetchone()
            if res:
                st.session_state.update({'logado': True, 'nivel': res[0], 'loja_atual': res[1]})
                st.rerun()
            else: st.error("Login ou Senha incorretos")
    st.stop()

# --- 3. NAVEGAÇÃO ---
def navegar(d): st.session_state.menu = d

st.sidebar.markdown("<h2 style='text-align: center;'>NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.info(f"Conectado: {st.session_state.loja_atual}")

st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ ADM (GERENCIAMENTO)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Avulsos",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 SAIR", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. FUNÇÃO PDF ---
def gerar_pdf(df):
    pdf = FPDF()
    for _, r in df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, f"LOJA: {r['loja']}", ln=True)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, f"Forn: {r['fornecedor']} | Data: {r['data']}", ln=True)
        pdf.ln(5); pdf.multi_cell(0, 10, f"ITENS:\n{r['itens']}")
    return pdf.output(dest='S').encode('latin-1')

# --- 5. TELAS ---

if st.session_state.menu == "Pedidos":
    st.header(f"🛒 Área de Pedidos")
    t1, t2, t3 = st.tabs(["🛒 Novo Pedido", "📦 Pedidos Granel", "⏳ Histórico"])

    with t1:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        f_sel = st.selectbox("Selecione o Fornecedor", forns)
        key_c = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []

        with st.container(border=True):
            c_it, c_qt = st.columns([3, 1])
            # CAMPO DE DIGITAR NORMALMENTE
            it_nome = c_it.text_input("Digite o Produto", key="input_it")
            it_qtd = c_qt.text_input("Qtd", key="input_qt")
            if st.button("➕ Adicionar na Lista"):
                if it_nome:
                    st.session_state[key_c].append({"item": it_nome, "qtd": it_qtd})
                    st.rerun()

        for i, v in enumerate(st.session_state[key_c]):
            col1, col2, col3 = st.columns([3, 1, 0.5])
            v['item'] = col1.text_input(f"Item {i}", v['item'], key=f"e_it_{i}")
            v['qtd'] = col2.text_input(f"Qtd {i}", v['qtd'], key=f"e_qt_{i}")
            if col3.button("❌", key=f"d_{i}"): st.session_state[key_c].pop(i); st.rerun()

        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO FINAL", type="primary"):
            txt = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_c]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,'Pendente')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
            st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()

    with t2:
        st.subheader("🌾 Pedidos Granel")
        # Logica similar de digitar livremente
        it_g = st.text_input("Produto Granel")
        qt_g = st.text_input("Quantidade")
        if st.button("Enviar Granel"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,'GRANEL',:i,'Pendente')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "i": f"{qt_g}x {it_g}"})
            st.success("Granel enviado!")

    with t3:
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        st.dataframe(df_h, use_container_width=True)

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    tp, ta = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with tp:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status='Pendente'"), engine)
        for _, r in df_p.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['loja']}"):
                st.write(r['itens'])
                if st.button("Marcar Atendido", key=f"at_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                    st.rerun()
    with ta:
        st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status='Atendido'"), engine), use_container_width=True)

elif st.session_state.menu == "Avulsos":
    st.header("📝 Pedidos Avulsos")
    f_av = st.text_input("Fornecedor")
    it_av = st.text_area("Itens (Ex: 10x Arroz, 5x Feijão)")
    if st.button("Gerar PDF"):
        df_v = pd.DataFrame([{"loja": "AVULSO", "fornecedor": f_av, "data": datetime.now().strftime("%d/%m/%Y"), "itens": it_av}])
        st.download_button("Baixar PDF", data=gerar_pdf(df_v), file_name="avulso.pdf")

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    tab_l, tab_f, tab_u = st.tabs(["Lojas", "Fornecedores", "Logins"])
    with tab_l:
        nl = st.text_input("Nova Loja")
        if st.button("Salvar Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl.upper()})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4, 1]); c1.write(r['nome'])
            if c2.button("Excluir", key=f"dl_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); st.rerun()
    with tab_f:
        nf = st.text_input("Novo Fornecedor")
        if st.button("Salvar Fornecedor"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM fornecedores"), engine).iterrows():
            c1, c2 = st.columns([4, 1]); c1.write(r['nome'])
            if c2.button("Excluir Forn", key=f"df_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE id=:id"), {"id": r['id']}); st.rerun()
    with tab_u:
        with st.form("user"):
            ul, us = st.text_input("Login"), st.text_input("Senha")
            uv = st.selectbox("Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()])
            if st.form_submit_button("Criar Login"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u,:s,:l,'vendedor')"), {"u": ul, "s": us, "l": uv})
                st.rerun()
