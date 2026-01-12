import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. FUNÇÕES DE LOGIN (CORREÇÃO PARA O ERRO UNHASHABLE) ---
def verificar_login(loja, senha):
    conn = st.connection("postgresql", type="sql")
    # Removi o 'text()' e usei uma string simples com parâmetros nomeadosimport streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DE CONEXÃO BLINDADA ---
def conectar_direto():
    try:
        # Puxamos a URL bruta dos segredos
        if "database" in st.secrets:
            url = st.secrets["database"]["url"].strip()
        elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
            url = st.secrets["connections"]["postgresql"]["url"].strip()
        else:
            st.error("Configuração de banco de dados não encontrada nos Secrets!")
            st.stop()

        # Limpeza total da URL: remove parâmetros que dão erro no Streamlit Cloud
        if "?" in url:
            url = url.split("?")[0]
        
        # Garante o prefixo correto
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        # Adiciona apenas o necessário para segurança
        url_final = f"{url}?sslmode=require"
        
        # Cria o motor de conexão sem usar o cache problemático do st.connection
        return create_engine(url_final, pool_pre_ping=True)
    except Exception as e:
        st.error(f"Erro ao configurar conexão: {e}")
        st.stop()

# --- 2. FUNÇÕES DE LOGIN ---
def verificar_login(loja, senha):
    engine = conectar_direto()
    with engine.connect() as conn:
        # Consulta direta usando parâmetros seguros da SQLAlchemy
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        resultado = conn.execute(query, {"loja": loja, "senha": senha}).fetchone()
        return resultado

# Inicialização do estado
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
            st.session_state.nivel = user[0] # nivel_acesso
            st.session_state.loja_atual = u
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# --- 3. GESTÃO DO BANCO (CRIAÇÃO DE TABELAS) ---
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

# --- 4. FUNÇÕES DE EXPORTAÇÃO ---
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

# --- 5. INTERFACE LATERAL ---
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
                    st.download_button("Baixar PDF", data=gerar_pdf_niyati(pd.DataFrame([r])), file_name=f"pedido_{r['id']}.pdf")
        else: st.info("Tudo em dia!")

    with t2:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_at, use_container_width=True)

elif st.session_state.menu == "Produtos":
    st.header("🍎 Cadastro de Produtos")
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
    # Isso resolve o UnhashableParamError dos seus logs
    query = "SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha"
    resultado = conn.query(query, params={"loja": loja, "senha": senha})
    return resultado

if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.loja_atual = None

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    usuario = st.text_input("Nome da Loja")
    senha = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        if usuario and senha:
            check = verificar_login(usuario, senha)
            if not check.empty:
                st.session_state.logado = True
                st.session_state.nivel = check.iloc[0]['nivel_acesso']
                st.session_state.loja_atual = usuario
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")
        else:
            st.warning("Preencha o usuário e a senha.")
else:
    # --- LOGADO COM SUCESSO ---
    st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
    
    opcoes_menu = ["Lista de Pedidos"]
    if st.session_state.nivel == 'admin':
        opcoes_menu += ["Gerenciamento", "Gerar Pedidos", "Produtos", "Configurações"]
    
    escolha = st.sidebar.radio("Navegação", opcoes_menu)
    
    if st.sidebar.button("Sair"):
        st.session_state.logado = False
        st.rerun()

    # --- 2. GESTÃO DO BANCO DE DADOS (CONEXÃO BLINDADA) ---
    def conectar():
        if "database" in st.secrets:
            db_url = st.secrets["database"]["url"].strip()
            # Remove parâmetros de pooler que dão erro no driver do Streamlit Cloud
            if "?" in db_url:
                db_url = db_url.split("?")[0]
            
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            
            return create_engine(db_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
        return create_engine('sqlite:///compras_niyati.db')

    def inicializar_banco():
        engine = conectar()
        with engine.begin() as conn:
            id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT "Enviado")'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))

    inicializar_banco()
    engine = conectar()

    # --- 3. FUNÇÕES DE EXPORTAÇÃO ---
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

    # --- 4. TELAS ---
    if escolha == "Lista de Pedidos":
        st.header("🛒 Pedidos")
        with engine.connect() as conn:
            lojas = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()] if st.session_state.nivel == 'admin' else [st.session_state.loja_atual]
        
        tabs = st.tabs(lojas)
        for i, nome_loja in enumerate(lojas):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo", "Histórico"], key=f"g_{nome_loja}", horizontal=True)
                if guia == "Novo":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
                    f = st.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                    key_c = f"car_{nome_loja}_{f}"
                    if key_c not in st.session_state: st.session_state[key_c] = []
                    
                    c1, c2 = st.columns([4, 1])
                    it = c1.text_input("Produto", key=f"it_{nome_loja}")
                    qt = c2.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                    if st.button("Add", key=f"b_{nome_loja}"):
                        if it: st.session_state[key_c].append({"Item": it, "Qtd": qt}); st.rerun()
                    
                    for idx, v in enumerate(st.session_state[key_c]):
                        cc1, cc2, cc3 = st.columns([3, 1, 1])
                        cc1.write(v['Item'])
                        cc2.write(f"{v['Qtd']} un")
                        if cc3.button("❌", key=f"d_{nome_loja}_{idx}"): st.session_state[key_c].pop(idx); st.rerun()
                        
                    if st.session_state[key_c] and st.button("🚀 ENVIAR", type="primary", key=f"env_{nome_loja}"):
                        txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
                        with engine.begin() as conn:
                            conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,"Enviado")'), 
                                         {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": nome_loja, "f": f, "i": txt})
                        st.session_state[key_c] = []; st.success("Enviado!"); st.rerun()
                else:
                    df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_loja}' ORDER BY id DESC"), engine)
                    for _, row in df_h.iterrows():
                        with st.expander(f"Pedido #{row['id']} - {row['fornecedor']}"):
                            st.write(row['itens'])

    elif escolha == "Gerenciamento":
        st.header("⚙️ ADM")
        t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
        with t1:
            df = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' OR status IS NULL ORDER BY id DESC"), engine)
            if not df.empty:
                if 'sel' not in st.session_state: st.session_state.sel = []
                c1, c2 = st.columns(2)
                if st.session_state.sel:
                    if c1.button("✔️ MARCAR ATENDIDOS"):
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.sel)})
                        st.session_state.sel = []; st.rerun()
                    c2.download_button("📄 PDF", data=gerar_pdf_niyati(df[df['id'].isin(st.session_state.sel)]), file_name="pedidos.pdf")
                
                for _, r in df.iterrows():
                    col_c, col_e = st.columns([0.1, 0.9])
                    if col_c.checkbox("", key=f"chk_{r['id']}", value=(r['id'] in st.session_state.sel)):
                        if r['id'] not in st.session_state.sel: st.session_state.sel.append(r['id']); st.rerun()
                    elif r['id'] in st.session_state.sel: st.session_state.sel.remove(r['id']); st.rerun()
                    with col_e.expander(f"#{r['id']} - {r['loja']} - {r['fornecedor']}"): st.write(r['itens'])
        with t2:
            df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
            st.dataframe(df_at, use_container_width=True)

    elif escolha == "Produtos":
        st.header("🍎 PRODUTOS")
        np = st.text_input("Novo")
        if st.button("Salvar") and np:
            with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
            st.rerun()
        st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

    elif escolha == "Configurações":
        st.header("🛠️ CONFIG")
        st.write("Lojas e Fornecedores cadastrados.")

