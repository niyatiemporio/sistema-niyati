import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io
import re

# --- 1. FUNÇÕES DE LOGIN ---
def verificar_login(loja, senha):
    conn = st.connection("postgresql", type="sql")
    query = f"SELECT nivel_acesso FROM usuarios WHERE nome_loja = '{loja}' AND senha = '{senha}'"
    resultado = conn.query(query)
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
            else: st.error("Utilizador ou senha incorretos")
else:
    st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
    opcoes_menu = ["Lista de Pedidos"]
    if st.session_state.nivel == 'admin':
        opcoes_menu += ["Gerenciamento", "Gerar Pedidos", "Produtos", "Configurações"]
    escolha = st.sidebar.radio("Navegação", opcoes_menu)
    if st.sidebar.button("Sair"):
        st.session_state.logado = False
        st.rerun()

    # --- 2. GESTÃO DO BANCO (LIMPEZA AGRESSIVA DE URL) ---
    def conectar():
        if "database" in st.secrets:
            db_url = st.secrets["database"]["url"].strip()
            # Remove TUDO o que vier depois do ponto de interrogação (limpa prepare_threshold)
            db_url = db_url.split("?")[0]
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            # Força apenas o sslmode necessário
            final_url = f"{db_url}?sslmode=require"
            return create_engine(final_url, pool_pre_ping=True)
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

    # --- 3. EXPORTAÇÃO ---
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
            pdf.cell(30, 10, txt="QTD", border=1, align='C', fill=True)
            pdf.cell(160, 10, txt="PRODUTO", border=1, align='C', fill=True); pdf.ln()
            for item in str(row['itens']).split(", "):
                try:
                    q, n = item.split("x ", 1)
                    pdf.cell(30, 8, txt=q, border=1, align='C')
                    pdf.cell(160, 8, txt=f" {n}", border=1); pdf.ln()
                except: pass
        return pdf.output(dest='S').encode('latin-1')

    # --- 4. TELAS ---
    if escolha == "Lista de Pedidos":
        st.header("🛒 PEDIDOS")
        with engine.connect() as conn:
            lojas = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()] if st.session_state.nivel == 'admin' else [st.session_state.loja_atual]
        
        tabs = st.tabs(lojas)
        for i, nome_loja in enumerate(lojas):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo", "Histórico"], key=f"guia_{nome_loja}", horizontal=True)
                if guia == "Novo":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
                    f = st.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                    key_c = f"car_{nome_loja}_{f}"
                    if key_c not in st.session_state: st.session_state[key_c] = []
                    
                    c1, c2 = st.columns([4, 1])
                    it = c1.text_input("Produto", key=f"it_{nome_loja}")
                    qt = c2.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                    if st.button("Add", key=f"btn_{nome_loja}"):
                        if it: st.session_state[key_c].append({"Item": it, "Qtd": qt}); st.rerun()
                    
                    for idx, v in enumerate(st.session_state[key_c]):
                        cc1, cc2, cc3 = st.columns([3, 1, 1])
                        cc1.write(v['Item'])
                        cc2.write(f"{v['Qtd']} un")
                        if cc3.button("❌", key=f"del_{nome_loja}_{idx}"): st.session_state[key_c].pop(idx); st.rerun()
                        
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
                    if c1.button("✔️ ATENDER SELECIONADOS"):
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
            st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine), use_container_width=True)

    elif escolha == "Produtos":
        st.header("🍎 PRODUTOS")
        np = st.text_input("Novo")
        if st.button("Salvar") and np:
            with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
            st.rerun()
        st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

    elif escolha == "Configurações":
        st.header("🛠️ CONFIG")
        st.write("Gerencie Lojas e Fornecedores aqui.")
