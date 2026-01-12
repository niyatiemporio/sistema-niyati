import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONEXÃO INTELIGENTE (RESOLVE KEYERROR E PREPARE_THRESHOLD) ---
def conectar():
    # Tenta ler do formato que você configurou
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("ERRO: Configuração de banco de dados não encontrada nos Secrets!")
        st.stop()

    # Limpeza automática da URL para evitar erros de conexão
    url = url.strip()
    if "prepare_threshold" in url:
        url = url.split("?")[0] + "?sslmode=require"
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return create_engine(url, pool_pre_ping=True)

# --- 2. LOGIN ---
def verificar_login(loja, senha):
    engine = conectar()
    with engine.connect() as conn:
        # Consulta usando parâmetros para evitar erro de 'UnhashableParam'
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        res = conn.execute(query, {"loja": loja, "senha": senha}).fetchone()
        return res

if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Pedidos"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Usuário")
    s = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        user = verificar_login(u, s)
        if user:
            st.session_state.update({'logado': True, 'nivel': user[0], 'loja_atual': u})
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# --- 3. INICIALIZAÇÃO E TELAS ---
engine = conectar()
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS fornecedores (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS produtos (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS pedidos (id SERIAL PRIMARY KEY, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT 'Enviado')"))

st.sidebar.title("NIYATI")
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")

if st.sidebar.button("🛒 PEDIDOS"): st.session_state.menu = "Pedidos"
if st.session_state.nivel == 'admin':
    if st.sidebar.button("⚙️ ADM"): st.session_state.menu = "ADM"
    if st.sidebar.button("🛠️ CONFIGS"): st.session_state.menu = "Config"

if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- LÓGICA DAS TELAS (IGUAL AO ANTERIOR) ---
if st.session_state.menu == "Pedidos":
    st.header("🛒 Novo Pedido")
    with engine.connect() as conn:
        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
    
    f_sel = st.selectbox("Fornecedor", forns)
    key_c = f"car_{st.session_state.loja_atual}_{f_sel}"
    if key_c not in st.session_state: st.session_state[key_c] = []

    c1, c2 = st.columns([3, 1])
    it = c1.selectbox("Produto", [""] + prods) if prods else c1.text_input("Produto")
    qt = c2.number_input("Qtd", min_value=1)
    if st.button("Add Item"):
        if it: st.session_state[key_c].append(f"{qt}x {it}"); st.rerun()

    for i, v in enumerate(st.session_state[key_c]):
        col_t, col_b = st.columns([4, 1])
        col_t.write(v)
        if col_b.button("X", key=f"del_{i}"): st.session_state[key_c].pop(i); st.rerun()

    if st.session_state[key_c] and st.button("🚀 FINALIZAR"):
        txt = ", ".join(st.session_state[key_c])
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"), 
                         {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
        st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with t1:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        if not df_p.empty:
            sel_ids = []
            for _, r in df_p.iterrows():
                if st.checkbox(f"Pedido #{r['id']} - {r['loja']} ({r['fornecedor']})", key=f"p_{r['id']}"):
                    sel_ids.append(r['id'])
                st.write(f"Itens: {r['itens']}")
            if sel_ids and st.button("✔️ Marcar Atendidos"):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(sel_ids)})
                st.rerun()
        else: st.info("Sem pedidos pendentes.")
    with t2:
        st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine))

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    with st.form("new_user"):
        u_name = st.text_input("Login Loja")
        u_pass = st.text_input("Senha")
        if st.form_submit_button("Criar Login"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, 'vendedor')"), {"n": u_name, "s": u_pass})
            st.success("Criado!")
