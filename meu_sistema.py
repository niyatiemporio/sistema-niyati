import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONEXÃO E LOGIN (SEM ERROS DE HASH OU PARÂMETROS) ---
def conectar():
    # Procura a URL nos Secrets (formatos database ou connections)
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configuração de banco de dados não encontrada!")
        st.stop()

    # Limpa a URL de parâmetros que dão erro (prepare_threshold)
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return create_engine(f"{url}?sslmode=require", pool_pre_ping=True)

def verificar_login(loja, senha):
    engine = conectar()
    with engine.connect() as conn:
        # Consulta direta para evitar UnhashableParamError
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        return conn.execute(query, {"loja": loja, "senha": senha}).fetchone()

# Inicialização do Estado
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lojas"})

# --- 2. TELA DE LOGIN ---
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

# --- 3. INICIALIZAR TABELAS (PÓS-LOGIN) ---
engine = conectar()
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS fornecedores (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS produtos (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS pedidos (id SERIAL PRIMARY KEY, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT 'Enviado')"))

# --- 4. FUNÇÕES DE APOIO ---
def gerar_pdf_niyati(dados_df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in dados_df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, txt=f"PEDIDO: {row['loja'].upper()}", ln=True)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, txt=f"Forn: {row['fornecedor']} | Data: {row['data']}", ln=True)
        pdf.ln(5)
        pdf.multi_cell(0, 8, txt=f"ITENS:\n{row['itens']}", border=1)
    return pdf.output(dest='S').encode('latin-1')

def navegar(destino): 
    st.session_state.menu = destino

# --- 5. INTERFACE LATERAL ---
st.sidebar.title("NIYATI")
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
st.sidebar.divider()

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# TELA: LISTA DE PEDIDOS
if st.session_state.menu == "Lojas":
    st.header("🛒 Pedidos")
    with engine.connect() as conn:
        if st.session_state.nivel == 'admin':
            lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
        else:
            lojas_db = [st.session_state.loja_atual]
            
    if not lojas_db:
        st.info("Nenhuma loja cadastrada. Use o menu Configurações.")
    else:
        tabs = st.tabs(lojas_db)
        for i, nome_loja in enumerate(lojas_db):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"g_{nome_loja}", horizontal=True)
                if guia == "Novo Pedido":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                        prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
                    
                    f_sel = st.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                    key_c = f"car_{nome_loja}_{f_sel}"
                    if key_c not in st.session_state: st.session_state[key_c] = []

                    c1, c2 = st.columns([3, 1])
                    it = c1.selectbox("Produto", [""] + prods, key=f"it_{nome_loja}")
                    qt = c2.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                    if st.button("Adicionar Item", key=f"add_{nome_loja}"):
                        if it: st.session_state[key_c].append(f"{qt}x {it}"); st.rerun()

                    for idx, v in enumerate(st.session_state[key_c]):
                        col_txt, col_del = st.columns([4, 1])
                        col_txt.write(v)
                        if col_del.button("❌", key=f"del_{nome_loja}_{idx}"): 
                            st.session_state[key_c].pop(idx); st.rerun()

                    if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO FINAL", type="primary", key=f"env_{nome_loja}"):
                        txt_itens = ", ".join(st.session_state[key_c])
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"), 
                                         {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_loja, "f": f_sel, "i": txt_itens})
                        st.session_state[key_c] = []; st.success("Pedido enviado com sucesso!"); st.rerun()
                else:
                    df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_loja}' ORDER BY id DESC"), engine)
                    for _, row in df_h.iterrows():
                        with st.expander(f"Pedido #{row['id']} - {row['fornecedor']} ({row['data']}) - {row['status']}"):
                            st.write(row['itens'])

# TELA: ADM (PENDENTES E ATENDIDOS)
elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento Geral")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    
    with t1:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        if not df_p.empty:
            sel_ids = []
            c1, c2 = st.columns(2)
            if st.button("✔️ Marcar Selecionados como Atendidos", type="primary"):
                # Captura os IDs que foram marcados nos checkboxes abaixo
                ids_para_atualizar = [r['id'] for _, r in df_p.iterrows() if st.session_state.get(f"check_adm_{r['id']}")]
                if ids_para_atualizar:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(ids_para_atualizar)})
                    st.rerun()

            for _, r in df_p.iterrows():
                col_c, col_e = st.columns([0.1, 0.9])
                col_c.checkbox("", key=f"check_adm_{r['id']}")
                with col_e.expander(f"#{r['id']} | {r['loja']} | {r['fornecedor']} | {r['data']}"):
                    st.write(r['itens'])
                    st.download_button("PDF", data=gerar_pdf_niyati(pd.DataFrame([r])), file_name=f"pedido_{r['id']}.pdf", key=f"pdf_{r['id']}")
        else:
            st.info("Não há pedidos pendentes.")

    with t2:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_at, use_container_width=True)

# TELA: PRODUTOS
elif st.session_state.menu == "Produtos":
    st.header("🍎 Cadastro de Produtos")
    novo_p = st.text_input("Nome do Produto")
    if st.button("Salvar Produto") and novo_p:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": novo_p})
        st.success("Produto salvo!")
        st.rerun()
    st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

# TELA: CONFIGURAÇÕES (LOJAS, FORNECEDORES E ACESSOS)
elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Lojas")
        nl = st.text_input("Nova Loja")
        if st.button("Add Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
    with c2:
        st.subheader("Acessos (Login)")
        with st.form("add_user"):
            u_loja = st.text_input("Login Loja")
            u_senha = st.text_input("Senha")
            if st.form_submit_button("Criar Login"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, 'vendedor')"), {"n": u_loja, "s": u_senha})
                st.success("Acesso criado!")

    st.subheader("Fornecedores")
    nf = st.text_input("Novo Fornecedor")
    if st.button("Add Forn") and nf:
        with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
        st.rerun()
