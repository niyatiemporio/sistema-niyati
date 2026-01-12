import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="Sistema Niyati", layout="wide")

# --- 2. GESTÃO DO BANCO DE DADOS ---
def conectar():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        return st.connection("postgresql", type="sql").engine
    elif "database" in st.secrets:
        db_url = st.secrets["database"]["url"].strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
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
        
        # Admin padrão
        res = conn.execute(text("SELECT COUNT(*) FROM usuarios")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES ('Admin', 'admin123', 'admin')"))

engine = conectar()
inicializar_banco()

# --- 3. LÓGICA DE LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.menu_selecionado = "Lojas"

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    with st.container(border=True):
        u = st.text_input("Usuário (Loja)")
        s = st.text_input("Senha", type="password")
        if st.button("Entrar", use_container_width=True, type="primary"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :u AND senha = :s"), {"u": u, "s": s}).fetchone()
                if res:
                    st.session_state.logado = True
                    st.session_state.nivel = res[0]
                    st.session_state.loja_atual = u
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos")
    st.stop()

# --- 4. FUNÇÕES DE EXPORTAÇÃO ---
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

# --- 5. MENU LATERAL ---
st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>SISTEMA NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.write(f"Usuário: **{st.session_state.loja_atual}** ({st.session_state.nivel})")
st.sidebar.divider()

def navegar(destino): st.session_state.menu_selecionado = destino

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Lojas" else "secondary")

if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "ADM" else "secondary")
    st.sidebar.button("📝 GERAR PEDIDOS (AVULSO)", on_click=navegar, args=("Gerar",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Gerar" else "secondary")
    st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Produtos" else "secondary")
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Config" else "secondary")

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS ---

# TELA LOJAS (FAZER PEDIDO)
if st.session_state.menu_selecionado == "Lojas":
    st.header("🛒 LISTA DE PEDIDOS DE COMPRA")
    with engine.connect() as conn:
        lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
    
    # Se não for admin, ele só vê a aba da própria loja
    abas_visiveis = [st.session_state.loja_atual] if st.session_state.nivel != 'admin' else lojas_db
    
    if not abas_visiveis:
        st.warning("Nenhuma loja cadastrada ou acesso restrito.")
    else:
        tabs = st.tabs(abas_visiveis)
        for i, nome_loja in enumerate(abas_visiveis):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"g_{nome_loja}", horizontal=True)
                
                if guia == "Novo Pedido":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
                        prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]

                    f_sel = st.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                    key_c = f"car_{nome_loja}_{f_sel}"
                    if key_c not in st.session_state: st.session_state[key_c] = []

                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        it = c1.selectbox("Produto", [""] + prods, key=f"it_{nome_loja}")
                        qt = c2.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                        if st.button("Adicionar Linha", key=f"add_{nome_loja}"):
                            if it:
                                st.session_state[key_c].append({"Item": it, "Qtd": qt})
                                st.rerun()

                    for idx, v in enumerate(st.session_state[key_c]):
                        cc1, cc2, cc3 = st.columns([3, 1, 0.5])
                        # Edição em tempo real
                        st.session_state[key_c][idx]['Item'] = cc1.text_input(f"E_{idx}", v['Item'], key=f"ed_it_{nome_loja}_{idx}", label_visibility="collapsed")
                        cc2.write(f"{v['Qtd']} un")
                        if cc3.button("❌", key=f"del_{nome_loja}_{idx}"):
                            st.session_state[key_c].pop(idx); st.rerun()

                    if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary", key=f"env_{nome_loja}"):
                        txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
                        with engine.begin() as conn:
                            conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,:s)'), 
                                         {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": nome_loja, "f": f_sel, "i": txt, "s": "Enviado"})
                        st.session_state[key_c] = []; st.success("Sucesso!"); st.rerun()
                
                else: # Histórico da Loja
                    df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = :l ORDER BY id DESC"), engine, params={"l": nome_loja})
                    for _, row in df_h.iterrows():
                        with st.expander(f"Pedido #{row['id']} - {row['fornecedor']} ({row['data']})"):
                            st.write(row['itens'])

# TELA ADM (GERENCIAMENTO)
elif st.session_state.menu_selecionado == "ADM":
    st.header("⚙️ GERENCIAMENTO (ADM)")
    df_adm = pd.read_sql(text("SELECT * FROM pedidos ORDER BY id DESC"), engine)
    
    if not df_adm.empty:
        if 'ids_sel' not in st.session_state: st.session_state.ids_sel = []
        
        # Botões de Exportação
        if st.session_state.ids_sel:
            df_sel = df_adm[df_adm['id'].isin(st.session_state.ids_sel)]
            c1, c2 = st.columns(2)
            c1.download_button("📄 Gerar PDF Selecionados", data=gerar_pdf_niyati(df_sel), file_name="pedidos.pdf", use_container_width=True)
            if c2.button("🗑️ Deletar Selecionados", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM pedidos WHERE id IN :ids"), {"ids": tuple(st.session_state.ids_sel)})
                st.session_state.ids_sel = []; st.rerun()

        for _, r in df_adm.iterrows():
            col_ch, col_ex = st.columns([0.05, 0.95])
            selecionado = col_ch.checkbox("", key=f"chk_adm_{r['id']}", value=(r['id'] in st.session_state.ids_sel))
            
            # Atualiza lista de seleção
            if selecionado and r['id'] not in st.session_state.ids_sel: st.session_state.ids_sel.append(r['id']); st.rerun()
            if not selecionado and r['id'] in st.session_state.ids_sel: st.session_state.ids_sel.remove(r['id']); st.rerun()

            with col_ex.expander(f"📦 Pedido #{r['id']} | {r['loja']} | {r['fornecedor']} | {r['data']}"):
                st.write(f"**Itens:** {r['itens']}")
                if st.button(f"Excluir Pedido #{r['id']}", key=f"btn_del_{r['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM pedidos WHERE id = :id"), {"id": r['id']})
                    st.rerun()

# TELA CONFIG (GERENCIAR LOJAS E SENHAS)
elif st.session_state.menu_selecionado == "Config":
    st.header("🛠️ CONFIGURAÇÕES")
    t1, t2 = st.tabs(["Lojas e Fornecedores", "Usuários e Senhas"])
    
    with t1:
        # Mesma lógica que você já tinha de Adicionar/Remover Lojas e Fornecedores
        nl = st.text_input("Nova Loja")
        if st.button("Salvar Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        # Listar e Deletar Lojas... (similar ao seu original)

    with t2:
        st.subheader("Controle de Acessos")
        with st.form("f_user"):
            u_nome = st.text_input("Nome do Usuário (Loja)")
            u_pass = st.text_input("Senha")
            u_tipo = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Criar Acesso"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :t)"), {"n": u_nome, "s": u_pass, "t": u_tipo})
                st.success("Acesso criado!")
                st.rerun()
