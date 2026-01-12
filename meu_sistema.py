import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO E CONEXÃO (BLINDADA) ---
st.set_page_config(page_title="SISTEMA NIYATI", layout="wide")

def conectar():
    # Procura a URL nos segredos (formato flexível)
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configuração de banco de dados não encontrada!")
        st.stop()
    
    # Limpa parâmetros que dão erro no Streamlit Cloud
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return create_engine(f"{url}?sslmode=require", pool_pre_ping=True)

# --- 2. VERIFICAÇÃO DE LOGIN ---
def verificar_login(loja, senha):
    engine = conectar()
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

# --- 3. INICIALIZAÇÃO DO BANCO (ESTRUTURA ORIGINAL) ---
engine = conectar()
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS fornecedores (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS produtos (id SERIAL PRIMARY KEY, nome TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS pedidos (id SERIAL PRIMARY KEY, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT 'Enviado')"))

# --- 4. FUNÇÕES DE APOIO (PDF) ---
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
        pdf.ln(5)
        pdf.set_fill_color(200, 220, 255); pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 10, txt="QTD", border=1, align='C', fill=True)
        pdf.cell(160, 10, txt="DESCRIÇÃO", border=1, align='C', fill=True); pdf.ln()
        pdf.set_font("Arial", '', 10)
        for item in str(row['itens']).split(", "):
            try:
                q, n = item.split("x ", 1)
                pdf.cell(30, 8, txt=q, border=1, align='C')
                pdf.cell(160, 8, txt=f" {n}", border=1); pdf.ln()
            except: pass
    return pdf.output(dest='S').encode('latin-1')

# --- 5. NAVEGAÇÃO LATERAL (ESTILO ORIGINAL) ---
def navegar(destino): st.session_state.menu = destino

st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>SISTEMA NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.divider()
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True, type="primary" if st.session_state.menu == "Lojas" else "secondary")
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True, type="primary" if st.session_state.menu == "ADM" else "secondary")
    st.sidebar.button("📝 GERAR PEDIDOS (AVULSO)", on_click=navegar, args=("Gerar",), use_container_width=True, type="primary" if st.session_state.menu == "Gerar" else "secondary")
    st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True, type="primary" if st.session_state.menu == "Produtos" else "secondary")
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True, type="primary" if st.session_state.menu == "Config" else "secondary")

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# --- TELA: LOJAS ---
if st.session_state.menu == "Lojas":
    st.header("🛒 Pedidos de Compra")
    with engine.connect() as conn:
        lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()] if st.session_state.nivel == 'admin' else [st.session_state.loja_atual]
    
    tabs = st.tabs(lojas_db)
    for i, nome_l in enumerate(lojas_db):
        with tabs[i]:
            guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_l}", horizontal=True)
            if guia == "Novo Pedido":
                with engine.connect() as conn:
                    forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                    prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
                
                f_sel = st.selectbox("Fornecedor", forns, key=f"f_{nome_l}")
                key_c = f"car_{nome_l}_{f_sel}"
                if key_c not in st.session_state: st.session_state[key_c] = []

                with st.container(border=True):
                    cp, cq = st.columns([4, 1])
                    it = cp.selectbox("Produto", [""] + prods, key=f"it_{nome_l}")
                    qt = cq.number_input("Qtd", min_value=1, key=f"qt_{nome_l}")
                    if st.button("Adicionar Item", key=f"add_{nome_l}"):
                        if it: st.session_state[key_c].append(f"{qt}x {it}"); st.rerun()

                for idx, v in enumerate(st.session_state[key_c]):
                    c_txt, c_del = st.columns([4, 1])
                    c_txt.write(v)
                    if c_del.button("❌", key=f"del_{nome_l}_{idx}"): st.session_state[key_c].pop(idx); st.rerun()
                
                if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", key=f"env_{nome_l}", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                                     {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_l, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
                    st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()
            else:
                df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_l}' ORDER BY id DESC"), engine)
                for _, row in df_h.iterrows():
                    with st.expander(f"Pedido #{row['id']} - {row['fornecedor']} ({row['data']})"):
                        st.write(row['itens'])

# --- TELA: ADM (GERENCIAMENTO) ---
elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with t1:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        if not df_p.empty:
            if 'ids_sel' not in st.session_state: st.session_state.ids_sel = []
            
            c1, c2 = st.columns(2)
            if st.session_state.ids_sel:
                df_res = df_p[df_p['id'].isin(st.session_state.ids_sel)]
                c1.download_button("📄 Gerar PDF", data=gerar_pdf_niyati(df_res), file_name="pedidos.pdf")
                if c2.button("✔️ Marcar Atendidos", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.ids_sel)})
                    st.session_state.ids_sel = []; st.rerun()

            for _, r in df_p.iterrows():
                col_c, col_e = st.columns([0.1, 0.9])
                if col_c.checkbox("", key=f"adm_p_{r['id']}", value=(r['id'] in st.session_state.ids_sel)):
                    if r['id'] not in st.session_state.ids_sel: st.session_state.ids_sel.append(r['id']); st.rerun()
                elif r['id'] in st.session_state.ids_sel: st.session_state.ids_sel.remove(r['id']); st.rerun()
                
                with col_e.expander(f"#{r['id']} - {r['loja']} - {r['fornecedor']}"):
                    st.write(r['itens'])
                    if st.button("Excluir", key=f"del_adm_{r['id']}"):
                        with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                        st.rerun()
        else: st.info("Sem pedidos pendentes.")
    with t2:
        st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine), use_container_width=True)

# --- TELA: GERAR (AVULSO/UNIFICADO) ---
elif st.session_state.menu == "Gerar":
    st.header("📝 Gerar Pedidos Avulsos")
    if 'car_av' not in st.session_state: st.session_state.car_av = []
    with engine.connect() as conn:
        forns_l = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
    
    f_av = st.selectbox("Fornecedor", forns_l)
    d_av = st.date_input("Data")
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        it = c1.text_input("Item")
        qt = c2.number_input("Qtd", min_value=1)
        if st.button("Adicionar"):
            if it: st.session_state.car_av.append({"Item": it, "Qtd": qt}); st.rerun()
            
    for idx, v in enumerate(st.session_state.car_av):
        cc1, cc2, cc3 = st.columns([3, 1, 1])
        cc1.write(v['Item'])
        cc2.write(f"{v['Qtd']} un")
        if cc3.button("Remover", key=f"rav_{idx}"): st.session_state.car_av.pop(idx); st.rerun()
        
    if st.session_state.car_av and st.button("📄 Gerar PDF Avulso"):
        tx = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state.car_av])
        df_v = pd.DataFrame([{"id": "AV", "loja": "AVULSO", "fornecedor": f_av, "data": d_av.strftime("%d/%m/%Y"), "itens": tx}])
        st.download_button("Baixar PDF", data=gerar_pdf_niyati(df_v), file_name="avulso.pdf")

# --- TELA: PRODUTOS ---
elif st.session_state.menu == "Produtos":
    st.header("🍎 Gerenciar Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar") and np:
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
        st.rerun()
    df_prods = pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine)
    for _, r in df_prods.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(r['nome'])
        if c2.button("X", key=f"del_p_{r['id']}"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM produtos WHERE id=:id"), {"id": r['id']})
            st.rerun()

# --- TELA: CONFIG ---
elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Gerenciar Lojas")
        nl = st.text_input("Nova Loja")
        if st.button("Add Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            col1, col2 = st.columns([3, 1]); col1.write(r['nome'])
            if col2.button("X", key=f"l_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()
    with c2:
        st.subheader("Fornecedores")
        nf = st.text_input("Novo Forn")
        if st.button("Add Forn") and nf:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
            st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM fornecedores"), engine).iterrows():
            col1, col2 = st.columns([3, 1]); col1.write(r['nome'])
            if col2.button("X", key=f"f_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE id=:id"), {"id": r['id']})
                st.rerun()
    
    st.divider()
    st.subheader("Acessos")
    with st.form("add_user"):
        u_loja = st.text_input("Login (Nome da Loja)")
        u_senha = st.text_input("Senha")
        if st.form_submit_button("Criar Acesso"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, 'vendedor')"), {"n": u_loja, "s": u_senha})
            st.success("Criado!")
