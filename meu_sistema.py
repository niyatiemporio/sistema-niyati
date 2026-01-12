import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO E CONEXÃO OTIMIZADA ---
st.set_page_config(page_title="SISTEMA NIYATI", layout="wide")

@st.cache_resource
def get_engine():
    url = st.secrets["connections"]["postgresql"]["url"] if "connections" in st.secrets else st.secrets["database"]["url"]
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_size=20, max_overflow=0)

engine = get_engine()

# --- 2. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lojas"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Usuário (Nome da Loja, ex: JUNQUEIRÓPOLIS)")
    s = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        with engine.connect() as conn:
            user = conn.execute(text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :u AND senha = :s"), {"u": u, "s": s}).fetchone()
            if user:
                st.session_state.update({'logado': True, 'nivel': user[0], 'loja_atual': u})
                st.rerun()
            else: st.error("Usuário ou senha incorretos")
    st.stop()

# --- 3. NAVEGAÇÃO ---
def navegar(destino): st.session_state.menu = destino

st.sidebar.markdown(f"<h2 style='text-align: center; color: #007bff;'>NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.write(f"Loja: **{st.session_state.loja_atual}**")
st.sidebar.divider()

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Gerar",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. TELAS ---

if st.session_state.menu == "Lojas":
    st.header(f"🛒 Pedidos - {st.session_state.loja_atual}")
    with engine.connect() as conn:
        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]

    guia = st.radio("Ação", ["Novo Pedido", "Histórico"], horizontal=True)
    
    if guia == "Novo Pedido":
        col_f, col_manage_f = st.columns([3, 1])
        f_sel = col_f.selectbox("Fornecedor", forns)
        if col_manage_f.button("➕/➖ Fornecedores"):
            st.session_state.show_f = not st.session_state.get('show_f', False)

        if st.session_state.get('show_f'):
            with st.expander("Gerenciar Fornecedores", expanded=True):
                nf = st.text_input("Novo Fornecedor")
                if st.button("Gravar Forn"):
                    with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
                    st.rerun()
                for f in forns:
                    c1, c2 = st.columns([4, 1])
                    c1.write(f); 
                    if c2.button("X", key=f"del_f_{f}"):
                        with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE nome=:n"), {"n": f})
                        st.rerun()

        key_c = f"car_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []

        with st.container(border=True):
            st.write("### Adicionar Item")
            # --- CAMPO ÚNICO INTELIGENTE ---
            # O multiselect permite digitar e criar novos itens se não existirem
            p_input = st.multiselect("Produto (Selecione ou digite um novo)", options=prods, max_selections=1, help="Comece a digitar. Se não existir, o sistema aceitará o que você escreveu.")
            
            # Pega o que foi escrito mesmo que não esteja na lista
            produto_final = p_input[0] if p_input else ""
            
            qt = st.number_input("Quantidade", min_value=1, step=1)
            if st.button("➕ Adicionar Linha", type="secondary"):
                if produto_final:
                    st.session_state[key_c].append(f"{qt}x {produto_final}")
                    st.rerun()

        for idx, v in enumerate(st.session_state[key_c]):
            c1, c2 = st.columns([4, 1])
            c1.info(v)
            if c2.button("❌", key=f"del_it_{idx}"): st.session_state[key_c].pop(idx); st.rerun()
        
        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
            st.session_state[key_c] = []; st.success("Sucesso!"); st.rerun()
    else:
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        st.dataframe(df_h, use_container_width=True)

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    t1, t2 = st.tabs(["Lojas", "Logins"])
    
    with t1:
        nl = st.text_input("Cadastrar Nome da Loja")
        if st.button("Salvar Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(r['nome'])
            if c2.button("X", key=f"dl_loja_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()

    with t2:
        with st.form("add_user"):
            st.subheader("Criar Acesso")
            ul = st.selectbox("Vincular à Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()] + ["ADMIN"])
            us = st.text_input("Definir Senha")
            un = st.selectbox("Tipo", ["vendedor", "admin"])
            if st.form_submit_button("Gerar Login"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :a)"), {"n": ul, "s": us, "a": un})
                st.rerun()
        
        st.subheader("Gerenciar Acessos Existentes")
        for _, r in pd.read_sql(text("SELECT * FROM usuarios"), engine).iterrows():
            with st.expander(f"Login: {r['nome_loja']}"):
                ns = st.text_input("Trocar Senha", key=f"ns_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar", key=f"s_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": ns, "id": r['id']})
                    st.success("Ok!")
                if c2.button("Excluir", key=f"e_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
    for _, r in df_p.iterrows():
        with st.expander(f"Pedido #{r['id']} - {r['loja']} - {r['fornecedor']}"):
            txt_edit = st.text_area("Itens", r['itens'], key=f"ed_{r['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Salvar Edição", key=f"sv_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": txt_edit, "id": r['id']})
                st.rerun()
            if c2.button("Finalizar/Atendido", key=f"at_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                st.rerun()
