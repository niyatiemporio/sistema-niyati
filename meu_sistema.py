import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema Niyati", layout="wide", page_icon="🍎")

# --- 2. GESTÃO DO BANCO DE DADOS (SUPABASE / POSTGRES) ---
def conectar():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        # Conexão recomendada pelo Streamlit Cloud via Secrets
        return st.connection("postgresql", type="sql").engine
    elif "database" in st.secrets:
        # Fallback para string de conexão manual
        db_url = st.secrets["database"]["url"].strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
    else:
        # Fallback local
        return create_engine('sqlite:///compras_niyati.db')

def inicializar_banco():
    engine = conectar()
    with engine.begin() as conn:
        id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
        # Tabela de Usuários (Login)
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS usuarios (id {id_tipo}, nome_loja TEXT UNIQUE, senha TEXT, nivel_acesso TEXT)'))
        # Tabelas de Apoio
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))
        # Tabela de Pedidos
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT "Pendente")'))
        
        # Criação do Admin Inicial se a tabela estiver vazia
        res = conn.execute(text("SELECT COUNT(*) FROM usuarios")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES ('Admin', 'admin123', 'admin')"))

engine = conectar()
inicializar_banco()

# --- 3. LÓGICA DE AUTENTICAÇÃO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.loja_atual = None
    st.session_state.menu_selecionado = "Pedidos"

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    with st.container(border=True):
        col_login, _ = st.columns([1, 2])
        with col_login:
            u = st.text_input("Usuário (Nome da Loja)")
            s = st.text_input("Senha", type="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                with engine.connect() as conn:
                    query = text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :u AND senha = :s")
                    user_res = conn.execute(query, {"u": u, "s": s}).fetchone()
                    if user_res:
                        st.session_state.logado = True
                        st.session_state.nivel = user_res[0]
                        st.session_state.loja_atual = u
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
    st.stop()

# --- 4. FUNÇÕES DE EXPORTAÇÃO (PDF) ---
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

# --- 5. INTERFACE LATERAL (MENU) ---
st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.write(f"Sessão: **{st.session_state.loja_atual}**")
st.sidebar.divider()

def navegar(destino): st.session_state.menu_selecionado = destino

st.sidebar.button("🛒 FAZER PEDIDO", on_click=navegar, args=("Pedidos",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Pedidos" else "secondary")

if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAR ADM", on_click=navegar, args=("ADM",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "ADM" else "secondary")
    st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Produtos" else "secondary")
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Config" else "secondary")

st.sidebar.divider()
if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# TELA PEDIDOS (CLIENTE/LOJA)
if st.session_state.menu_selecionado == "Pedidos":
    st.header(f"🛒 Pedidos - {st.session_state.loja_atual}")
    aba_novo, aba_hist = st.tabs(["Novo Pedido", "Meu Histórico"])
    
    with aba_novo:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
            prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
        
        if not forns: st.warning("Cadastre fornecedores no menu Configurações.")
        else:
            f_sel = st.selectbox("Selecione o Fornecedor", forns)
            key_c = f"car_{st.session_state.loja_atual}_{f_sel}"
            if key_c not in st.session_state: st.session_state[key_c] = []
            
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                it = c1.selectbox("Produto", [""] + prods, key=f"inp_it_{f_sel}")
                qt = c2.number_input("Qtd", min_value=1, key=f"inp_qt_{f_sel}")
                if st.button("Adicionar ao Carrinho"):
                    if it:
                        st.session_state[key_c].append({"Item": it, "Qtd": qt})
                        st.rerun()

            for idx, item_car in enumerate(st.session_state[key_c]):
                col1, col2, col3 = st.columns([3, 1, 0.5])
                col1.write(f"🔹 {item_car['Item']}")
                col2.write(f"{item_car['Qtd']} un")
                if col3.button("❌", key=f"del_c_{idx}"):
                    st.session_state[key_c].pop(idx)
                    st.rerun()
            
            if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
                txt_itens = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
                with engine.begin() as conn:
                    conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d, :l, :f, :i, :s)'),
                                 {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt_itens, "s": "Pendente"})
                st.session_state[key_c] = []
                st.success("Pedido enviado com sucesso!")
                st.rerun()

    with aba_hist:
        df_hist = pd.read_sql(text("SELECT * FROM pedidos WHERE loja = :l ORDER BY id DESC"), engine, params={"l": st.session_state.loja_atual})
        for _, row in df_hist.iterrows():
            cor_status = "🔵" if row['status'] == "Pendente" else "🟢"
            with st.expander(f"{cor_status} Pedido #{row['id']} - {row['fornecedor']} ({row['data']})"):
                st.write(f"**Status:** {row['status']}")
                st.write(f"**Itens:** {row['itens']}")

# TELA ADM (GERENCIAMENTO)
elif st.session_state.menu_selecionado == "ADM":
    st.header("⚙️ Gerenciamento Central")
    t_pend, t_aten = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    
    with t_pend:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' ORDER BY id DESC"), engine)
        if df_p.empty: st.info("Não há pedidos pendentes.")
        else:
            if 'selecao_adm' not in st.session_state: st.session_state.selecao_adm = []
            
            c_adm1, c_adm2, c_adm3 = st.columns(3)
            if st.session_state.selecao_adm:
                df_s = df_p[df_p['id'].isin(st.session_state.selecao_adm)]
                c_adm1.download_button("📄 PDF dos Selecionados", data=gerar_pdf_niyati(df_s), file_name="pedidos_niyati.pdf")
                if c_adm2.button("✔️ Marcar como Atendido", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.selecao_adm)})
                    st.session_state.selecao_adm = []; st.rerun()
                if c_adm3.button("🗑️ Deletar Selecionados"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM pedidos WHERE id IN :ids"), {"ids": tuple(st.session_state.selecao_adm)})
                    st.session_state.selecao_adm = []; st.rerun()

            for _, r in df_p.iterrows():
                col_c, col_e = st.columns([0.1, 0.9])
                is_sel = col_c.checkbox("", key=f"sel_{r['id']}", value=(r['id'] in st.session_state.selecao_adm))
                if is_sel and r['id'] not in st.session_state.selecao_adm: st.session_state.selecao_adm.append(r['id']); st.rerun()
                if not is_sel and r['id'] in st.session_state.selecao_adm: st.session_state.selecao_adm.remove(r['id']); st.rerun()
                
                with col_e.expander(f"📦 Pedido #{r['id']} | {r['loja']} | {r['fornecedor']}"):
                    st.write(f"Data: {r['data']}")
                    st.write(f"**Itens:** {r['itens']}")

    with t_aten:
        df_a = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        for _, r_a in df_a.iterrows():
            with st.expander(f"✅ Pedido #{r_a['id']} - {r_a['loja']} ({r_a['data']})"):
                st.write(r_a['itens'])
                if st.button("Reverter para Pendente", key=f"rev_{r_a['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedidos SET status = 'Pendente' WHERE id = :id"), {"id": r_a['id']})
                    st.rerun()

# TELA PRODUTOS
elif st.session_state.menu_selecionado == "Produtos":
    st.header("🍎 Cadastro de Produtos")
    with st.form("add_produto"):
        novo_p = st.text_input("Nome do Produto")
        if st.form_submit_button("Salvar") and novo_p:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": novo_p})
            st.rerun()
    
    df_prods = pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine)
    for _, row in df_prods.iterrows():
        c_p1, c_p2 = st.columns([4, 1])
        c_p1.write(row['nome'])
        if c_p2.button("Excluir", key=f"del_p_{row['id']}"):
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM produtos WHERE id = :id"), {"id": row['id']})
            st.rerun()

# TELA CONFIGURAÇÕES
elif st.session_state.menu_selecionado == "Config":
    st.header("🛠️ Configurações Gerais")
    tab_conf1, tab_conf2, tab_conf3 = st.tabs(["Lojas", "Fornecedores", "Usuários/Senhas"])
    
    with tab_conf1:
        n_loja = st.text_input("Nova Loja")
        if st.button("Adicionar Loja") and n_loja:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": n_loja})
            st.rerun()
        df_l = pd.read_sql(text("SELECT * FROM lojas"), engine)
        st.table(df_l)

    with tab_conf2:
        n_forn = st.text_input("Novo Fornecedor")
        if st.button("Adicionar Fornecedor") and n_forn:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": n_forn})
            st.rerun()
        df_f = pd.read_sql(text("SELECT * FROM fornecedores"), engine)
        st.table(df_f)

    with tab_conf3:
        st.subheader("Cadastrar Acesso")
        with st.form("novo_acesso"):
            u_loja = st.text_input("Login (Nome da Loja)")
            u_pass = st.text_input("Senha")
            u_tipo = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Criar Usuário"):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :t)"), {"n": u_loja, "s": u_pass, "t": u_tipo})
                    st.success("Criado!")
                except: st.error("Este usuário já existe.")
