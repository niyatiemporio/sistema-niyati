import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# --- 1. CONEXÃO DIRETA E RÁPIDA ---
def conectar():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configuração não encontrada!")
        st.stop()
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_pre_ping=True)

# --- 2. LOGIN ---
def verificar_login(loja, senha):
    engine = conectar()
    with engine.connect() as conn:
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        return conn.execute(query, {"loja": loja, "senha": senha}).fetchone()

if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lista de Pedidos"})

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

# --- 3. INTERFACE E NAVEGAÇÃO ---
engine = conectar()
st.sidebar.title("NIYATI")
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")

# Menu Simplificado para evitar lentidão
opcoes = ["Lista de Pedidos"]
if st.session_state.nivel == 'admin':
    opcoes += ["Gerenciamento", "Produtos", "Configurações"]

escolha = st.sidebar.radio("Navegação", opcoes)

if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 4. TELAS ---

if escolha == "Lista de Pedidos":
    st.header("🛒 Pedidos")
    with engine.connect() as conn:
        if st.session_state.nivel == 'admin':
            lojas = [r[0] for r in conn.execute(text('SELECT nome FROM lojas ORDER BY nome')).fetchall()]
        else:
            lojas = [st.session_state.loja_atual]
            
    if not lojas:
        st.info("Cadastre as lojas no menu Configurações.")
    else:
        tabs = st.tabs(lojas)
        for i, nome_l in enumerate(lojas):
            with tabs[i]:
                # Busca Fornecedores e Produtos
                with engine.connect() as conn:
                    forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                    prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
                
                f_sel = st.selectbox("Fornecedor", forns, key=f"f_{nome_l}")
                key_c = f"car_{nome_l}_{f_sel}"
                if key_c not in st.session_state: st.session_state[key_c] = []

                c1, c2 = st.columns([3, 1])
                it = c1.selectbox("Produto", [""] + prods, key=f"it_{nome_l}")
                qt = c2.number_input("Qtd", min_value=1, key=f"qt_{nome_l}")
                if st.button("Add Item", key=f"btn_{nome_l}"):
                    if it: st.session_state[key_c].append(f"{qt}x {it}"); st.rerun()

                for idx, v in enumerate(st.session_state[key_c]):
                    st.write(f"{v}")
                
                if st.session_state[key_c] and st.button("🚀 ENVIAR", key=f"env_{nome_l}", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                                     {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_l, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
                    st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()

elif escolha == "Gerenciamento":
    st.header("⚙️ ADM")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with t1:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        for _, r in df_p.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['loja']} ({r['fornecedor']})"):
                st.write(r['itens'])
                if st.button("Marcar como Atendido", key=f"at_{r['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id = :id"), {"id": r['id']})
                    st.rerun()
    with t2:
        st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine), use_container_width=True)

elif escolha == "Produtos":
    st.header("🍎 Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar") and np:
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
        st.rerun()
    st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

elif escolha == "Configurações":
    st.header("🛠️ Configurações")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Lojas")
        nl = st.text_input("Nova Loja")
        if st.button("Add Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        st.write(pd.read_sql(text("SELECT nome FROM lojas"), engine))
    with c2:
        st.subheader("Fornecedores")
        nf = st.text_input("Novo Fornecedor")
        if st.button("Add Forn") and nf:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
            st.rerun()
        st.write(pd.read_sql(text("SELECT nome FROM fornecedores"), engine))
