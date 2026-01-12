import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. FUNÇÃO DE CONEXÃO (BLINDADA) ---
def conectar_direto():
    try:
        # Tenta buscar a URL em diferentes locais possíveis dos Secrets
        if "database" in st.secrets:
            url = st.secrets["database"]["url"].strip()
        elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
            url = st.secrets["connections"]["postgresql"]["url"].strip()
        else:
            st.error("Configuração de banco de dados não encontrada!")
            st.stop()

        # Limpa a URL de parâmetros que dão erro no Streamlit Cloud
        if "?" in url:
            url = url.split("?")[0]
        
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        url_final = f"{url}?sslmode=require"
        return create_engine(url_final, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Erro de configuração: {e}")
        st.stop()

# --- 2. FUNÇÃO DE LOGIN ---
def verificar_login(loja, senha):
    engine = conectar_direto()
    with engine.connect() as conn:
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        resultado = conn.execute(query, {"loja": loja, "senha": senha}).fetchone()
        return resultado

# --- 3. CONTROLE DE ACESSO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.loja_atual = None
    st.session_state.menu = "Pedidos"

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Nome da Loja")
    s = st.text_input("Senha", type="password")
    
    if st.button("Entrar", type="primary"):
        user = verificar_login(u, s)
        if user:
            st.session_state.logado = True
            st.session_state.nivel = user[0]
            st.session_state.loja_atual = u
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# --- 4. INICIALIZAÇÃO DO BANCO ---
def inicializar_banco():
    engine = conectar_direto()
    with engine.begin() as conn:
        id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT "Enviado")'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))

inicializar_banco()
engine = conectar_direto()

# --- 5. FUNÇÕES DE APOIO (PDF) ---
def gerar_pdf_niyati(dados_df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in dados_df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, txt=f"LOJA: {row['loja'].upper()}", ln=True)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, txt=f"Forn: {row['fornecedor']} | {row['data']}", ln=True)
        pdf.ln(5)
        for item in str(row['itens']).split(", "):
            pdf.cell(0, 8, txt=f"- {item}", border="B", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 6. MENU LATERAL ---
st.sidebar.title("NIYATI")
st.sidebar.write(f"Logado: **{st.session_state.loja_atual}**")
st.sidebar.divider()

if st.sidebar.button("🛒 PEDIDOS", use_container_width=True): st.session_state.menu = "Pedidos"
if st.session_state.nivel == 'admin':
    if st.sidebar.button("⚙️ ADM", use_container_width=True): st.session_state.menu = "ADM"
    if st.sidebar.button("🍎 PRODUTOS", use_container_width=True): st.session_state.menu = "Produtos"
    if st.sidebar.button("🛠️ CONFIGS", use_container_width=True): st.session_state.menu = "Config"

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 7. TELAS ---
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
    if st.button("Adicionar Item"):
        if it: st.session_state[key_c].append({"Item": it, "Qtd": qt}); st.rerun()

    for idx, v in enumerate(st.session_state[key_c]):
        col1, col2, col3 = st.columns([3, 1, 0.5])
        col1.write(v['Item'])
        col2.write(f"{v['Qtd']} un")
        if col3.button("❌", key=f"del_{idx}"): st.session_state[key_c].pop(idx); st.rerun()

    if st.session_state[key_c] and st.button("🚀 FINALIZAR PEDIDO", type="primary"):
        txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,"Enviado")'), 
                         {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
        st.session_state[key_c] = []; st.success("Pedido enviado!"); st.rerun()

elif st.session_state.menu == "ADM":
    st.header("⚙️ Área Administrativa")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with t1:
        df = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        if not df.empty:
            if 'sel_ids' not in st.session_state: st.session_state.sel_ids = []
            if st.button("✔️ Marcar como Atendidos"):
                if st.session_state.sel_ids:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.sel_ids)})
                    st.session_state.sel_ids = []; st.rerun()
            for _, r in df.iterrows():
                c_ch, c_ex = st.columns([0.1, 0.9])
                if c_ch.checkbox("", key=f"chk_{r['id']}"):
                    if r['id'] not in st.session_state.sel_ids: st.session_state.sel_ids.append(r['id'])
                with c_ex.expander(f"Pedido #{r['id']} - {r['loja']} - {r['fornecedor']}"):
                    st.write(r['itens'])
        else: st.info("Tudo em dia!")

    with t2:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_at, use_container_width=True)

elif st.session_state.menu == "Produtos":
    st.header("🍎 Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar") and np:
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
        st.rerun()
    st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

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
        nf = st.text_input("Novo Fornecedor")
        if st.button("Add Forn") and nf:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
            st.rerun()
