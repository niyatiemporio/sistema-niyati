import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="SISTEMA NIYATI", layout="wide")

# --- CONEXÃO OTIMIZADA (CACHED) ---
@st.cache_resource
def get_engine():
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
    return create_engine(f"{url}?sslmode=require", pool_size=10, max_overflow=20)

engine = get_engine()

# --- LOGIN ---
def verificar_login(loja, senha):
    with engine.connect() as conn:
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        return conn.execute(query, {"loja": loja, "senha": senha}).fetchone()

if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lojas"})

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

# --- NAVEGAÇÃO ---
def navegar(destino): st.session_state.menu = destino

st.sidebar.title("NIYATI")
st.sidebar.write(f"Loja: **{st.session_state.loja_atual}**")
st.sidebar.divider()

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 GERAR PEDIDOS AVULSOS", on_click=navegar, args=("Gerar",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- TELAS ---

if st.session_state.menu == "Lojas":
    st.header("🛒 Lista de Pedidos")
    with engine.connect() as conn:
        if st.session_state.nivel == 'admin':
            lojas = [r[0] for r in conn.execute(text('SELECT nome FROM lojas ORDER BY nome')).fetchall()]
        else:
            lojas = [st.session_state.loja_atual]
    
    tabs = st.tabs(lojas) if lojas else [st.container()]
    for i, nome_l in enumerate(lojas):
        with tabs[i]:
            guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_l}", horizontal=True)
            if guia == "Novo Pedido":
                with engine.connect() as conn:
                    forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                    prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]

                col_f, col_manage = st.columns([3, 1])
                f_sel = col_f.selectbox("Fornecedor", forns, key=f"f_{nome_l}")
                if col_manage.button("⚙️ Gerenciar Fornecedores", key=f"manage_{nome_l}"):
                    st.session_state[f'pop_{nome_l}'] = not st.session_state.get(f'pop_{nome_l}', False)
                
                if st.session_state.get(f'pop_{nome_l}'):
                    with st.expander("Gerenciar Lista de Fornecedores", expanded=True):
                        nf = st.text_input("Novo Fornecedor", key=f"inf_{nome_l}")
                        if st.button("Salvar Forn", key=f"svf_{nome_l}"):
                            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
                            st.rerun()
                        for f in forns:
                            c1, c2 = st.columns([4, 1])
                            c1.write(f)
                            if c2.button("X", key=f"del_f_{nome_l}_{f}"):
                                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE nome=:n"), {"n": f})
                                st.rerun()

                key_c = f"car_{nome_l}_{f_sel}"
                if key_c not in st.session_state: st.session_state[key_c] = []

                with st.container(border=True):
                    cp, cq = st.columns([4, 1])
                    # INPUT INTELIGENTE: Digita ou Escolhe
                    it = cp.selectbox("Produto (Selecione ou digite abaixo)", [""] + prods, key=f"sel_it_{nome_l}")
                    it_manual = cp.text_input("Ou digite o produto manualmente", key=f"man_it_{nome_l}")
                    produto_final = it_manual if it_manual else it
                    qt = cq.number_input("Qtd", min_value=1, key=f"qt_{nome_l}")
                    if st.button("Adicionar Linha", key=f"add_{nome_l}"):
                        if produto_final: 
                            st.session_state[key_c].append(f"{qt}x {produto_final}")
                            st.rerun()

                for idx, v in enumerate(st.session_state[key_c]):
                    col1, col2 = st.columns([4, 1])
                    col1.write(v)
                    if col2.button("❌", key=f"del_it_{nome_l}_{idx}"): 
                        st.session_state[key_c].pop(idx); st.rerun()
                
                if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", key=f"env_{nome_l}", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                                     {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_l, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
                    st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()
            else:
                df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_l}' ORDER BY id DESC"), engine)
                st.dataframe(df_h, use_container_width=True)

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
    for _, r in df_p.iterrows():
        with st.expander(f"Pedido #{r['id']} - {r['loja']} ({r['fornecedor']})"):
            new_itens = st.text_area("Editar Itens", r['itens'], key=f"edit_{r['id']}")
            c1, c2 = st.columns(2)
            if c1.button("💾 Salvar Alteração", key=f"save_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": new_itens, "id": r['id']})
                st.rerun()
            if c2.button("✅ Marcar Atendido", key=f"at_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                st.rerun()

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações e Acessos")
    
    t1, t2 = st.tabs(["Gerenciar Lojas", "Gerenciar Logins"])
    
    with t1:
        nl = st.text_input("Cadastrar Nova Loja")
        if st.button("Add Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        df_l = pd.read_sql(text("SELECT * FROM lojas"), engine)
        for _, r in df_l.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(r['nome'])
            if c2.button("Excluir", key=f"dl_l_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()

    with t2:
        st.subheader("Controle de Usuários")
        with st.form("new_user"):
            u_loja = st.text_input("Login (Vincular à Loja)")
            u_pass = st.text_input("Senha")
            u_tipo = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Criar Login"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :a)"), {"n": u_loja, "s": u_pass, "a": u_tipo})
                st.rerun()
        
        df_u = pd.read_sql(text("SELECT id, nome_loja, nivel_acesso FROM usuarios"), engine)
        for _, r in df_u.iterrows():
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.write(f"👤 {r['nome_loja']}")
            c2.write(f"Nível: {r['nivel_acesso']}")
            if c3.button("Excluir Login", key=f"dl_u_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                st.rerun()
