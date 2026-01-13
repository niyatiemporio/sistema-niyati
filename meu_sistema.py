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
    # Busca a URL nos segredos (Streamlit Cloud)
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configure a URL do banco nos Secrets!")
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
st.sidebar.title("NIYATI")
st.sidebar.info(f"Loja: {st.session_state.loja_atual}")

def navegar(d): st.session_state.menu = d

st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Avulsos",), use_container_width=True)
    st.sidebar.button("🍎 LISTA DE PRODUTOS", on_click=navegar, args=("Prods",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 SAIR", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. TELAS ---

if st.session_state.menu == "Config":
    st.header("🛠️ Configurações e Gestão")
    tab_lojas, tab_logins, tab_forns = st.tabs(["🏢 Lojas", "🔐 Logins/Acessos", "🚚 Fornecedores"])
    
    with tab_lojas:
        st.subheader("Cadastrar Nova Loja")
        nova_loja_nome = st.text_input("Digite o nome da loja (Ex: JUNQUEIRÓPOLIS)")
        if st.button("Gravar Loja", type="primary"):
            if nova_loja_nome:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nova_loja_nome.upper()})
                    st.success(f"Loja {nova_loja_nome} salva com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: Nome já existe ou erro de conexão.")
        
        st.divider()
        st.subheader("Lojas Cadastradas")
        df_lojas = pd.read_sql(text("SELECT * FROM lojas ORDER BY nome"), engine)
        for _, loja in df_lojas.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"📍 {loja['nome']}")
            if c2.button("Excluir", key=f"del_l_{loja['id']}"):
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM lojas WHERE id = :id"), {"id": loja['id']})
                st.rerun()

    with tab_logins:
        st.subheader("Criar Acesso para Funcionário")
        with st.form("form_login"):
            novo_log = st.text_input("Login (Ex: junqueira_login)")
            nova_sen = st.text_input("Senha", type="password")
            # Aqui buscamos as lojas reais cadastradas para vincular
            with engine.connect() as conn:
                lista_lojas = [r[0] for r in conn.execute(text("SELECT nome FROM lojas")).fetchall()]
            loja_vinc = st.selectbox("Vincular à Loja", lista_lojas + ["ADMINISTRAÇÃO"])
            nivel_vinc = st.selectbox("Nível", ["vendedor", "admin"])
            
            if st.form_submit_button("Gerar Acesso"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u, :s, :l, :n)"),
                                 {"u": novo_log, "s": nova_sen, "l": loja_vinc, "n": nivel_vinc})
                st.success("Login criado!")
                st.rerun()
        
        st.divider()
        st.subheader("Gerenciar Logins")
        df_users = pd.read_sql(text("SELECT * FROM usuarios"), engine)
        for _, user in df_users.iterrows():
            with st.expander(f"Usuário: {user['login']} (Loja: {user['nome_loja']})"):
                nova_s = st.text_input("Nova Senha", key=f"s_{user['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar Senha", key=f"btn_s_{user['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE usuarios SET senha = :s WHERE id = :id"), {"s": nova_s, "id": user['id']})
                    st.rerun()
                if c2.button("Excluir Login", key=f"btn_e_{user['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM usuarios WHERE id = :id"), {"id": user['id']})
                    st.rerun()

    with tab_forns:
        st.subheader("Gestão de Fornecedores")
        nf = st.text_input("Nome do Fornecedor")
        if st.button("Adicionar Fornecedor"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()})
            st.rerun()
        
        df_f = pd.read_sql(text("SELECT * FROM fornecedores ORDER BY nome"), engine)
        for _, forn in df_f.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"🚚 {forn['nome']}")
            if c2.button("Excluir", key=f"del_f_{forn['id']}"):
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM fornecedores WHERE id = :id"), {"id": forn['id']})
                st.rerun()

# --- TELA PEDIDOS (Onde a mágica acontece) ---
elif st.session_state.menu == "Pedidos":
    st.header(f"🛒 Pedidos - {st.session_state.loja_atual}")
    t_novo, t_granel, t_hist = st.tabs(["🛒 Novo Pedido", "🌾 Granel", "⏳ Histórico"])

    with t_novo:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        f_sel = st.selectbox("Escolha o Fornecedor", forns)
        
        key_cart = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_cart not in st.session_state: st.session_state[key_cart] = []

        with st.container(border=True):
            ci, cq = st.columns([3, 1])
            it_nome = ci.text_input("Digite o Produto", key="input_item")
            it_qtd = cq.text_input("Qtd", key="input_qtd")
            if st.button("➕ Adicionar Item na Lista"):
                if it_nome and it_qtd:
                    st.session_state[key_cart].append({"item": it_nome, "qtd": it_qtd})
                    st.rerun()

        for i, item in enumerate(st.session_state[key_cart]):
            cc1, cc2, cc3 = st.columns([3, 1, 0.5])
            item['item'] = cc1.text_input(f"Produto {i}", item['item'], key=f"edit_i_{i}")
            item['qtd'] = cc2.text_input(f"Qtd {i}", item['qtd'], key=f"edit_q_{i}")
            if cc3.button("🗑️", key=f"del_it_{i}"):
                st.session_state[key_cart].pop(i)
                st.rerun()

        if st.session_state[key_cart] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
            itens_texto = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_cart]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d, :l, :f, :i, 'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": itens_texto})
            st.session_state[key_cart] = []
            st.success("Pedido enviado!")
            st.rerun()

# --- CONTINUAÇÃO DAS OUTRAS TELAS (ADM, AVULSOS, PRODS) ---
# (As outras telas seguem a mesma lógica de edição e limpeza que você aprovou)
