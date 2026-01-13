import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="NIYATI - SISTEMA", layout="wide")

@st.cache_resource
def get_engine():
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configure os Secrets!")
        st.stop()
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_pre_ping=True)

engine = get_engine()

# --- 2. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Pedidos"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u_login = st.text_input("Login")
    u_senha = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT nivel_acesso, nome_loja FROM usuarios WHERE login = :u AND senha = :s"), {"u": u_login, "s": u_senha}).fetchone()
            if res:
                st.session_state.update({'logado': True, 'nivel': res[0], 'loja_atual': res[1]})
                st.rerun()
            else: st.error("Login ou Senha incorretos")
    st.stop()

# --- 3. NAVEGAÇÃO ---
def navegar(d): st.session_state.menu = d

st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.info(f"Loja: {st.session_state.loja_atual}")

st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Avulsos",), use_container_width=True)
    st.sidebar.button("🍎 LISTA DE PRODUTOS", on_click=navegar, args=("Prods",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 SAIR", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. FUNÇÃO PDF BONITINHO (TABELADO) ---
def gerar_pdf_bonito(df, titulo="ORDEM DE PEDIDO"):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    for _, r in df.iterrows():
        pdf.add_page()
        # Cabeçalho Destacado
        pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 15, f"LOJA: {str(r['loja']).upper()}", ln=True, align='C', fill=True)
        
        # Info do Pedido
        pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", 'B', 10); pdf.ln(5)
        pdf.cell(95, 8, f"FORNECEDOR: {r['fornecedor']}", border='B')
        pdf.cell(95, 8, f"DATA: {r['data']} | N: {r['id']}", border='B', ln=True, align='R')
        pdf.ln(5)
        
        # Cabeçalho da Tabela
        pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 10, "QTD", border=1, align='C', fill=True)
        pdf.cell(160, 10, "DESCRIÇÃO DO PRODUTO", border=1, align='C', fill=True); pdf.ln()
        
        # Linhas da Tabela
        pdf.set_font("Arial", '', 10)
        itens = r['itens'].split(", ")
        for it in itens:
            if "x " in it:
                q, n = it.split("x ", 1)
                pdf.cell(30, 8, q, border=1, align='C')
                pdf.cell(160, 8, f" {n}", border=1); pdf.ln()
            else:
                pdf.cell(190, 8, it, border=1); pdf.ln()
                
    return pdf.output(dest='S').encode('latin-1')

# --- 5. TELAS ---

if st.session_state.menu == "Pedidos":
    st.header(f"🛒 Área de Pedidos")
    t1, t2, t3 = st.tabs(["🛒 Novo Pedido", "📦 Pedidos Granel", "⏳ Histórico"])

    with t1: # NOVO PEDIDO
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        f_sel = st.selectbox("Selecione Fornecedor", forns, key="f_norm")
        key_c = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []

        with st.container(border=True):
            ci, cq = st.columns([3, 1])
            it_n = ci.text_input("Produto", key="in_it_n")
            it_q = cq.text_input("Qtd", key="in_qt_n")
            if st.button("➕ Adicionar Linha"):
                if it_n: st.session_state[key_c].append({"item": it_n, "qtd": it_q}); st.rerun()

        for i, v in enumerate(st.session_state[key_c]):
            c1, c2, c3 = st.columns([3, 1, 0.5])
            v['item'] = c1.text_input(f"Item {i}", v['item'], key=f"ei_{i}")
            v['qtd'] = c2.text_input(f"Qtd {i}", v['qtd'], key=f"eq_{i}")
            if c3.button("❌", key=f"di_{i}"): st.session_state[key_c].pop(i); st.rerun()

        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
            txt = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_c]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,:f,:i,'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
            st.session_state[key_c] = []; st.success("Enviado!"); st.rerun()

    with t2: # PEDIDO GRANEL
        st.subheader("🌾 Pedidos Granel")
        if 'g_cart' not in st.session_state: st.session_state.g_cart = []
        with st.container(border=True):
            cg1, cg2 = st.columns([3, 1])
            git = cg1.text_input("Produto Granel", key="in_it_g")
            gqt = cg2.text_input("Qtd", key="in_qt_g")
            if st.button("➕ Adicionar Item Granel"):
                if git: st.session_state.g_cart.append({"item": git, "qtd": gqt}); st.rerun()
        
        for i, g in enumerate(st.session_state.g_cart):
            col1, col2, col3 = st.columns([3,1,0.5])
            g['item'] = col1.text_input(f"G_it_{i}", g['item'])
            g['qtd'] = col2.text_input(f"G_qt_{i}", g['qtd'])
            if col3.button("❌", key=f"dg_{i}"): st.session_state.g_cart.pop(i); st.rerun()

        if st.session_state.g_cart and st.button("Enviar Granel", type="primary"):
            txt_g = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.g_cart])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,'GRANEL',:i,'Granel')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "i": txt_g})
            st.session_state.g_cart = []; st.success("Granel Enviado!"); st.rerun()

    with t3: # HISTÓRICO
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        for _, r in df_h.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['data']} - {r['status']}"):
                novo_t = st.text_area("Reeditar Pedido", r['itens'], key=f"hi_{r['id']}")
                if st.button("Salvar Alteração", key=f"h_sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": novo_t, "id": r['id']})
                    st.rerun()

elif st.session_state.menu == "Avulsos":
    st.header("📝 Pedidos Avulsos (ADM)")
    if 'av_cart' not in st.session_state: st.session_state.av_cart = []
    
    f_av = st.text_input("Digite o Fornecedor", key="f_av_man")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        it_av = c1.text_input("Produto")
        qt_av = c2.text_input("Qtd")
        if st.button("➕ Adicionar Linha"):
            if it_av: st.session_state.av_cart.append({"item": it_av, "qtd": qt_av}); st.rerun()

    for i, v in enumerate(st.session_state.av_cart):
        col1, col2, col3 = st.columns([3, 1, 0.5])
        v['item'] = col1.text_input(f"Av_it_{i}", v['item'])
        v['qtd'] = col2.text_input(f"Av_qt_{i}", v['qtd'])
        if col3.button("❌", key=f"dav_{i}"): st.session_state.av_cart.pop(i); st.rerun()
    
    if st.session_state.av_cart:
        c1, c2 = st.columns(2)
        txt_av = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.av_cart])
        df_v = pd.DataFrame([{"id": "AV", "loja": "AVULSO", "fornecedor": f_av, "data": datetime.now().strftime("%d/%m/%Y"), "itens": txt_av}])
        c1.download_button("📄 Gerar PDF Bonitinho", data=gerar_pdf_bonito(df_v), file_name="avulso.pdf")
        if c2.button("🚀 Enviar para Atendidos", type="primary"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,'AVULSO',:f,:i,'Atendido')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "f": f_av, "i": txt_av})
            st.session_state.av_cart = []; st.success("Finalizado!"); st.rerun()

elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    tp, tg, ta = st.tabs(["⏳ Pendentes", "🌾 Granel", "✅ Atendidos"])
    
    with tp:
        df = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Normal' ORDER BY id DESC"), engine)
        sel_ids = []
        for _, r in df.iterrows():
            c_sel, c_exp = st.columns([0.1, 0.9])
            if c_sel.checkbox("", key=f"sel_{r['id']}"): sel_ids.append(r['id'])
            with c_exp.expander(f"LOJA: {r['loja']} | Nº: {r['id']} | DATA: {r['data']}"):
                for it in r['itens'].split(", "):
                    q, n = it.split("x ", 1) if "x " in it else ("?", it)
                    st.markdown(f"**<span style='color:red'>{q}</span>** - {n}", unsafe_allow_html=True)
                edit_adm = st.text_area("Editar", r['itens'], key=f"adm_ed_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar", key=f"adm_s_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": edit_adm, "id": r['id']})
                    st.rerun()
                if c2.button("Excluir", key=f"adm_d_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()

        if sel_ids:
            c1, c2 = st.columns(2)
            if c1.button("✅ MARCAR COMO ATENDIDO", type="primary"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id IN :ids"), {"ids": tuple(sel_ids)})
                st.rerun()
            c2.download_button("📄 Gerar PDF Selecionados", data=gerar_pdf_bonito(df[df['id'].isin(sel_ids)]), file_name="pedidos.pdf")

    with tg: # GRANEL NO ADM
        df_g = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Granel' ORDER BY id DESC"), engine)
        for _, r in df_g.iterrows():
            with st.expander(f"GRANEL: {r['loja']} - {r['data']}"):
                st.write(r['itens'])
                if st.button("Atender Granel", key=f"at_g_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                    st.rerun()

    with ta:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_at, use_container_width=True)

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    t1, t2, t3 = st.tabs(["🏢 Lojas", "🚚 Fornecedores", "🔐 Logins"])
    
    with t1:
        nl = st.text_input("Nova Loja")
        if st.button("Gravar Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl.upper()}); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4,1]); c1.write(r['nome'])
            if c2.button("X", key=f"dl_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); st.rerun()

    with t2:
        nf = st.text_input("Novo Forn")
        if st.button("Add Forn"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()}); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM fornecedores"), engine).iterrows():
            c1, c2 = st.columns([4,1]); c1.write(r['nome'])
            if c2.button("X", key=f"dfn_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE id=:id"), {"id": r['id']}); st.rerun()

    with t3: # GERENCIAR LOGINS
        st.subheader("Novos Logins")
        with st.form("f_l"):
            ul, us = st.text_input("Login"), st.text_input("Senha")
            uv = st.selectbox("Vincular à Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()] + ["ADMINISTRAÇÃO"])
            un = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Gerar"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u,:s,:l,:n)"), {"u": ul, "s": us, "l": uv, "n": un})
                st.rerun()
        
        st.divider()
        st.subheader("Logins Existentes")
        df_u = pd.read_sql(text("SELECT * FROM usuarios"), engine)
        for _, r in df_u.iterrows():
            with st.expander(f"Login: {r['login']} (Loja: {r['nome_loja']})"):
                ns = st.text_input("Nova Senha", key=f"ns_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar", key=f"s_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": ns, "id": r['id']})
                    st.rerun()
                if c2.button("Excluir", key=f"e_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()
