import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema Niyati", layout="wide")

# --- 2. GESTÃO DO BANCO DE DADOS ---
def conectar():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        # Usa a conexão configurada nos Secrets do Streamlit
        return st.connection("postgresql", type="sql").engine
    elif "database" in st.secrets:
        db_url = st.secrets["database"]["url"].strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
    else:
        return create_engine('sqlite:///compras_niyati.db')

def inicializar_banco():
    engine = conectar()
    with engine.begin() as conn:
        id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS usuarios (id {id_tipo}, nome_loja TEXT UNIQUE, senha TEXT, nivel_acesso TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))
        
        # Criar usuário admin padrão se não existir
        res = conn.execute(text("SELECT COUNT(*) FROM usuarios")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES ('Admin', 'admin123', 'admin')"))
            conn.execute(text("INSERT INTO lojas (nome) VALUES ('Junqueirópolis'), ('Tupi Paulista'), ('Pres. Venceslau')"))
            conn.execute(text("INSERT INTO fornecedores (nome) VALUES ('Max Titanium'), ('Unilife'), ('Herbamed')"))

engine = conectar()
inicializar_banco()

# --- 3. LOGICA DE LOGIN ---
def verificar_login(loja, senha):
    with engine.connect() as conn:
        query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :loja AND senha = :senha")
        return conn.execute(query, {"loja": loja, "senha": senha}).fetchone()

if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.loja_atual = None
    st.session_state.menu_selecionado = "Lojas"

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    col_l1, col_l2 = st.columns([1, 2])
    with col_l1:
        u = st.text_input("Nome da Loja (ou Admin)")
        s = st.text_input("Senha", type="password")
        if st.button("Entrar", use_container_width=True):
            user_data = verificar_login(u, s)
            if user_data:
                st.session_state.logado = True
                st.session_state.nivel = user_data[0]
                st.session_state.loja_atual = u
                st.rerun()
            else:
                st.error("Credenciais inválidas")
    st.stop() # Interrompe o código aqui se não estiver logado

# --- 4. FUNÇÕES DE EXPORTAÇÃO (PDF/EXCEL) ---
def gerar_pdf_niyati(dados_df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in dados_df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 22); pdf.set_text_color(0, 51, 102) 
        pdf.cell(200, 15, txt=f"LOJA: {str(row['loja']).upper()}", ln=True, align='L')
        pdf.set_font("Arial", 'B', 12); pdf.set_text_color(0, 0, 0)
        pdf.cell(100, 8, txt=f"FORNECEDOR: {row['fornecedor']}", ln=False)
        pdf.cell(100, 8, txt=f"DATA: {row['data']}", ln=True, align='R')
        pdf.cell(0, 8, txt=f"PEDIDO Nº: {row['id']}", ln=True); pdf.ln(5)
        pdf.set_fill_color(200, 220, 255); pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 10, txt="QUANTIDADE", border=1, align='C', fill=True)
        pdf.cell(160, 10, txt="DESCRIÇÃO DO PRODUTO", border=1, align='C', fill=True); pdf.ln()
        pdf.set_font("Arial", '', 10)
        for item in str(row['itens']).split(", "):
            try:
                q_p, n_p = item.split("x ", 1)
                pdf.cell(30, 8, txt=q_p, border=1, align='C')
                pdf.cell(160, 8, txt=f" {n_p}", border=1); pdf.ln()
            except: pdf.cell(190, 8, txt=item, border=1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def gerar_excel_niyati(dados_df):
    rows = []
    for _, row in dados_df.iterrows():
        for item in str(row['itens']).split(", "):
            try:
                q_v, n_v = item.split("x ", 1)
                rows.append({"ID Pedido": row['id'], "Data": row['data'], "Loja": row['loja'], "Fornecedor": row['fornecedor'], "Quantidade": q_v, "Produto": n_v})
            except: rows.append({"ID Pedido": row['id'], "Data": row['data'], "Loja": row['loja'], "Fornecedor": row['fornecedor'], "Quantidade": "1", "Produto": item})
    df_excel = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df_excel.to_excel(writer, index=False)
    return output.getvalue()

# --- 5. NAVEGAÇÃO LATERAL ---
st.sidebar.markdown(f"<h3 style='text-align: center;'>SISTEMA NIYATI</h3>", unsafe_allow_html=True)
st.sidebar.write(f"📍 Loja: **{st.session_state.loja_atual}**")
st.sidebar.divider()

def navegar(destino): st.session_state.menu_selecionado = destino

# Menu dinâmico baseado no nível
st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Lojas" else "secondary")

if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "ADM" else "secondary")
    st.sidebar.button("📝 GERAR PEDIDOS (AVULSO)", on_click=navegar, args=("Gerar",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Gerar" else "secondary")
    st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Produtos" else "secondary")
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Config" else "secondary")

st.sidebar.divider()
if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# TELA: LISTA DE PEDIDOS (LOJAS)
if st.session_state.menu_selecionado == "Lojas":
    st.header("🛒 LISTA DE PEDIDOS DE COMPRA")
    
    # Se for vendedor, ele só vê a própria loja. Se for Admin, vê todas em abas.
    with engine.connect() as conn:
        if st.session_state.nivel == 'admin':
            lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
        else:
            lojas_db = [st.session_state.loja_atual]

    tabs = st.tabs(lojas_db)
    for i, nome_loja in enumerate(lojas_db):
        with tabs[i]:
            guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_loja}", horizontal=True)
            if guia == "Novo Pedido":
                with engine.connect() as conn:
                    forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
                    prods_db = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
                
                c1, c2 = st.columns([3, 1])
                f_sel = c1.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                
                key_c = f"car_{nome_loja}_{f_sel}"
                if key_c not in st.session_state: st.session_state[key_c] = []
                
                with st.container(border=True):
                    cp, cq = st.columns([4, 1])
                    it = cp.selectbox("Produto", [""] + prods_db, key=f"it_{nome_loja}") if prods_db else cp.text_input("Produto", key=f"it_{nome_loja}")
                    qt = cq.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                    if st.button("Adicionar Linha", key=f"add_{nome_loja}"):
                        if it: 
                            st.session_state[key_c].append({"Item": it, "Qtd": qt})
                            st.rerun()

                for idx, v in enumerate(st.session_state[key_c]):
                    cc1, cc2, cc3 = st.columns([3, 1, 1])
                    cc1.write(f"🔹 {v['Item']}")
                    cc2.write(f"{v['Qtd']} un")
                    if cc3.button("❌", key=f"del_{nome_loja}_{idx}"):
                        st.session_state[key_c].pop(idx)
                        st.rerun()

                if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO FINAL", type="primary", key=f"env_{nome_loja}"):
                    txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
                    with engine.begin() as conn:
                        conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,:s)'), 
                                     {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": nome_loja, "f": f_sel, "i": txt, "s": "Enviado"})
                    st.session_state[key_c] = []
                    st.success("Pedido Enviado com Sucesso!")
                    st.rerun()
            
            else: # HISTÓRICO
                df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_loja}' ORDER BY id DESC"), engine)
                if df_h.empty: st.info("Nenhum pedido encontrado.")
                for _, row in df_h.iterrows():
                    with st.expander(f"Pedido #{row['id']} - {row['fornecedor']} ({row['data']})"):
                        st.write(row['itens'])

# TELA: ADM
elif st.session_state.menu_selecionado == "ADM":
    st.header("⚙️ GERENCIAMENTO DE PEDIDOS (ADM)")
    df_adm = pd.read_sql(text("SELECT * FROM pedidos ORDER BY id DESC"), engine)
    if not df_adm.empty:
        if 'ids_sel' not in st.session_state: st.session_state.ids_sel = []
        
        c1, c2, c3 = st.columns(3)
        if st.session_state.ids_sel:
            df_sel = df_adm[df_adm['id'].isin(st.session_state.ids_sel)]
            c1.download_button("📄 PDF dos Selecionados", data=gerar_pdf_niyati(df_sel), file_name="pedidos.pdf", use_container_width=True)
            c2.download_button("📊 Excel dos Selecionados", data=gerar_excel_niyati(df_sel), file_name="pedidos.xlsx", use_container_width=True)
            if c3.button("Limpar Seleção", use_container_width=True): 
                st.session_state.ids_sel = []
                st.rerun()
        
        for _, r_adm in df_adm.iterrows():
            c_ch, c_ex = st.columns([0.05, 0.95])
            is_checked = r_adm['id'] in st.session_state.ids_sel
            if c_ch.checkbox("", key=f"chk_{r_adm['id']}", value=is_checked):
                if r_adm['id'] not in st.session_state.ids_sel:
                    st.session_state.ids_sel.append(r_adm['id'])
                    st.rerun()
            else:
                if r_adm['id'] in st.session_state.ids_sel:
                    st.session_state.ids_sel.remove(r_adm['id'])
                    st.rerun()
            
            c_ex.write(f"**Pedido #{r_adm['id']}** | {r_adm['loja']} | {r_adm['fornecedor']} | {r_adm['data']}")

# TELA: PRODUTOS
elif st.session_state.menu_selecionado == "Produtos":
    st.header("🍎 CADASTRO DE PRODUTOS")
    with st.form("form_prod"):
        np = st.text_input("Nome do Produto:")
        if st.form_submit_button("Salvar Produto") and np:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
            st.success("Produto adicionado!")
            st.rerun()
    st.dataframe(pd.read_sql(text("SELECT nome FROM produtos ORDER BY nome"), engine), use_container_width=True)

# TELA: CONFIGURAÇÕES (GERENCIAR LOJAS/SENHAS)
elif st.session_state.menu_selecionado == "Config":
    st.header("🛠️ CONFIGURAÇÕES DO SISTEMA")
    
    tab_lojas, tab_usuarios = st.tabs(["Lojas", "Usuários/Senhas"])
    
    with tab_lojas:
        nl = st.text_input("Nova Loja:")
        if st.button("Adicionar Loja") and nl:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        
    with tab_usuarios:
        st.subheader("Cadastrar Acesso para Loja")
        with st.form("novo_user"):
            u_n = st.text_input("Nome da Loja (Login)")
            u_s = st.text_input("Senha")
            u_a = st.selectbox("Acesso", ["vendedor", "admin"])
            if st.form_submit_button("Criar Usuário"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :a)"), {"n": u_n, "s": u_s, "a": u_a})
                st.success("Usuário criado!")
