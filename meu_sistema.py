import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Niyati", layout="wide")

# --- 2. CONEXÃO CORRIGIDA (PEGA AUTOMATICAMENTE DO SEU FORMATO) ---
def conectar():
    # Tenta pegar do formato [connections.postgresql] (padrão Streamlit)
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        # Se você configurou como url = "..." dentro de [connections.postgresql]
        if "url" in st.secrets["connections"]["postgresql"]:
            url = st.secrets["connections"]["postgresql"]["url"]
        else:
            # Se você usou o formato de campos separados (host, port, etc)
            c = st.secrets["connections"]["postgresql"]
            url = f"postgresql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}"
    
    # Tenta pegar do seu formato antigo [database] se o de cima falhar
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Erro: Credenciais do banco de dados não encontradas nos Secrets!")
        st.stop()

    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return create_engine(url, pool_pre_ping=True, connect_args={"sslmode": "require"})

# --- O RESTANTE DO CÓDIGO SEGUE IGUAL AO ANTERIOR ---

def inicializar_banco():
    engine = conectar()
    with engine.begin() as conn:
        # Se for Postgres (Supabase), usa SERIAL. Se for SQLite (local), usa AUTOINCREMENT.
        id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
        
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS usuarios (id {id_tipo}, nome_loja TEXT UNIQUE, senha TEXT, nivel_acesso TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT "Pendente")'))
        
        # Verifica se precisa criar o Admin padrão
        res = conn.execute(text("SELECT COUNT(*) FROM usuarios")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES ('Admin', 'admin123', 'admin')"))

# Chama a inicialização
inicializar_banco()
engine = conectar()

# --- 3. LÓGICA DE LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.menu = "Pedidos"

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Usuário (Loja)")
    s = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        with engine.connect() as conn:
            user = conn.execute(text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :u AND senha = :s"), {"u": u, "s": s}).fetchone()
            if user:
                st.session_state.logado = True
                st.session_state.nivel = user[0]
                st.session_state.loja_atual = u
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")
    st.stop()

# --- 4. FUNÇÕES PDF ---
def gerar_pdf_niyati(dados_df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in dados_df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, txt=f"PEDIDO: {row['loja'].upper()}", ln=True)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, txt=f"Fornecedor: {row['fornecedor']} | Data: {row['data']}", ln=True)
        pdf.ln(5)
        for item in str(row['itens']).split(", "):
            pdf.cell(0, 8, txt=f"- {item}", border="B", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. MENU LATERAL ---
st.sidebar.title("NIYATI")
st.sidebar.write(f"Loja: **{st.session_state.loja_atual}**")
st.sidebar.divider()

if st.sidebar.button("🛒 PEDIDOS"): st.session_state.menu = "Pedidos"
if st.session_state.nivel == 'admin':
    if st.sidebar.button("⚙️ ADM"): st.session_state.menu = "ADM"
    if st.sidebar.button("🍎 PRODUTOS"): st.session_state.menu = "Produtos"
    if st.sidebar.button("🛠️ CONFIGS"): st.session_state.menu = "Config"

if st.sidebar.button("🚪 Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS ---

if st.session_state.menu == "Pedidos":
    st.header("🛒 Novo Pedido")
    with engine.connect() as conn:
        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]

    f_sel = st.selectbox("Fornecedor", forns)
    key_c = f"car_{st.session_state.loja_atual}_{f_sel}"
    if key_c not in st.session_state: st.session_state[key_c] = []

    c1, c2 = st.columns([3, 1])
    it = c1.selectbox("Produto", [""] + prods)
    qt = c2.number_input("Qtd", min_value=1)
    if st.button("Adicionar"):
        if it: st.session_state[key_c].append({"Item": it, "Qtd": qt}); st.rerun()

    for idx, v in enumerate(st.session_state[key_c]):
        col1, col2, col3 = st.columns([3, 1, 0.5])
        col1.write(v['Item'])
        col2.write(f"{v['Qtd']} un")
        if col3.button("❌", key=f"del_{idx}"): st.session_state[key_c].pop(idx); st.rerun()

    if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
        txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,"Pendente")'), 
                         {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
        st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento")
    tab_p, tab_a = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    
    with tab_p:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' ORDER BY id DESC"), engine)
        if 'sel' not in st.session_state: st.session_state.sel = []
        
        if not df_p.empty:
            if st.button("✔️ Marcar como Atendido"):
                if st.session_state.sel:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.sel)})
                    st.session_state.sel = []; st.rerun()

            for _, r in df_p.iterrows():
                col_c, col_e = st.columns([0.1, 0.9])
                if col_c.checkbox("", key=f"chk_{r['id']}"):
                    if r['id'] not in st.session_state.sel: st.session_state.sel.append(r['id'])
                with col_e.expander(f"Pedido #{r['id']} - {r['loja']} - {r['fornecedor']}"):
                    st.write(r['itens'])
                    st.download_button("PDF", data=gerar_pdf_niyati(pd.DataFrame([r])), file_name=f"pedido_{r['id']}.pdf")

    with tab_a:
        df_a = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_a, use_container_width=True)

elif st.session_state.menu == "Produtos":
    st.header("🍎 Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar") and np:
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
        st.rerun()
    df_prods = pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine)
    st.dataframe(df_prods, use_container_width=True)

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
        st.subheader("Fornecedores")
        nf = st.text_input("Novo Forn")
        if st.button("Add Forn") and nf:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
            st.rerun()

