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
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configuração de banco não encontrada!")
        st.stop()
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_size=10, max_overflow=20)

engine = get_engine()

# --- 2. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lojas"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Usuário")
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
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
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
    st.header("🛒 Pedidos")
    with engine.connect() as conn:
        lojas = [r[0] for r in conn.execute(text('SELECT nome FROM lojas ORDER BY nome')).fetchall()] if st.session_state.nivel == 'admin' else [st.session_state.loja_atual]
    
    tabs = st.tabs(lojas) if lojas else [st.container()]
    for i, nome_l in enumerate(lojas):
        with tabs[i]:
            guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_l}", horizontal=True)
            if guia == "Novo Pedido":
                with engine.connect() as conn:
                    forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                    prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]

                c_f, c_add_f = st.columns([3, 1])
                f_sel = c_f.selectbox("Fornecedor", forns, key=f"f_{nome_l}")
                if c_add_f.button("➕/➖ Fornecedores", key=f"manage_f_{nome_l}"):
                    st.session_state[f'pop_{nome_l}'] = not st.session_state.get(f'pop_{nome_l}', False)

                if st.session_state.get(f'pop_{nome_l}'):
                    with st.expander("Gerenciar Fornecedores", expanded=True):
                        nf = st.text_input("Novo Fornecedor", key=f"inf_{nome_l}")
                        if st.button("Gravar", key=f"svf_{nome_l}"):
                            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
                            st.rerun()
                        for f in forns:
                            col_n, col_d = st.columns([4, 1])
                            col_n.write(f)
                            if col_d.button("X", key=f"df_{nome_l}_{f}"):
                                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE nome=:n"), {"n": f})
                                st.rerun()

                key_c = f"car_{nome_l}_{f_sel}"
                if key_c not in st.session_state: st.session_state[key_c] = []

                with st.container(border=True):
                    # CAMPO ÚNICO INTELIGENTE (DATALIST)
                    st.write("Descrição do Produto")
                    produto_final = st.selectbox("Selecione da lista ou comece a digitar para filtrar", [""] + prods, key=f"sel_{nome_l}", help="Para itens novos, cadastre em 'Produtos' no menu lateral ou digite aqui")
                    
                    # Se não estiver na lista, o sistema aceita o que foi digitado na busca do selectbox
                    # Nota: O selectbox do Streamlit permite busca, mas para itens TOTALMENTE novos o ideal é o Admin cadastrar em 'Produtos' ou usamos um text_input alternativo. 
                    # Para manter o campo ÚNICO e aceitar novos, usamos o text_input com as sugestões como legenda:
                    
                    it_final = st.text_input("Digite o produto (Sugestões: " + ", ".join(prods[:5]) + "...)", key=f"it_man_{nome_l}")
                    qt = st.number_input("Qtd", min_value=1, key=f"qt_{nome_l}")
                    
                    if st.button("Adicionar Linha", key=f"add_{nome_l}"):
                        p_nome = it_final if it_final else produto_final
                        if p_nome: 
                            st.session_state[key_c].append(f"{qt}x {p_nome}")
                            st.rerun()

                for idx, v in enumerate(st.session_state[key_c]):
                    c1, c2 = st.columns([4, 1])
                    c1.write(v)
                    if c2.button("❌", key=f"del_{nome_l}_{idx}"): 
                        st.session_state[key_c].pop(idx); st.rerun()
                
                if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", key=f"env_{nome_l}", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                                     {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_l, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
                    st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()
            else:
                df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_l}' ORDER BY id DESC"), engine)
                st.dataframe(df_h, use_container_width=True)

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    t1, t2 = st.tabs(["Gerenciar Lojas", "Gerenciar Logins"])
    
    with t1:
        nl = st.text_input("Nova Loja")
        if st.button("Adicionar Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(r['nome'])
            if c2.button("Excluir", key=f"dl_loja_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()

    with t2:
        st.subheader("Controle de Acessos")
        with st.form("novo_login"):
            ul = st.text_input("Nome da Loja (Login)")
            us = st.text_input("Senha")
            un = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Criar Usuário"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :a)"), {"n": ul, "s": us, "a": un})
                st.rerun()
        
        usuarios = pd.read_sql(text("SELECT * FROM usuarios"), engine)
        for _, r in usuarios.iterrows():
            with st.expander(f"👤 {r['nome_loja']} ({r['nivel_acesso']})"):
                nova_senha = st.text_input("Nova Senha", key=f"pw_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar Senha", key=f"sv_pw_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": nova_senha, "id": r['id']})
                    st.success("Alterado!")
                if c2.button("Excluir Login", key=f"del_us_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()
