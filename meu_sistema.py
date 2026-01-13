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

st.sidebar.title("NIYATI")
st.sidebar.info(f"Loja: {st.session_state.loja_atual}")

st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ ADM (GERENCIAMENTO)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Avulsos",), use_container_width=True)
    st.sidebar.button("🍎 LISTA DE PRODUTOS", on_click=navegar, args=("Prods",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 SAIR", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. FUNÇÕES PDF/EXCEL ---
def gerar_pdf(df, titulo="Relatório de Pedidos"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, titulo, ln=True, align='C'); pdf.ln(10)
    for _, r in df.iterrows():
        pdf.set_font("Arial", 'B', 12); pdf.set_fill_color(240,240,240)
        pdf.cell(0, 10, f"Loja: {r['loja']} | Pedido: {r['id']} | Data: {r['data']}", ln=True, fill=True)
        pdf.set_font("Arial", '', 10); pdf.multi_cell(0, 8, f"Itens:\n{r['itens']}"); pdf.ln(5)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. TELAS ---

# --- TELA PEDIDOS ---
if st.session_state.menu == "Pedidos":
    st.header(f"🛒 Área de Pedidos - {st.session_state.loja_atual}")
    t1, t2, t3 = st.tabs(["🛒 Novo Pedido", "📦 Pedidos Granel", "⏳ Histórico"])

    with t1:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        c1, c2 = st.columns([3, 1])
        f_sel = c1.selectbox("Selecione Fornecedor", forns)
        if c2.button("➕/➖ Fornecedor"): st.session_state.show_f = not st.session_state.get('show_f', False)
        
        if st.session_state.get('show_f'):
            with st.expander("Gerenciar Fornecedores", expanded=True):
                nf = st.text_input("Novo Fornecedor")
                if st.button("Gravar Forn"):
                    with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()}); st.rerun()
                for f in forns:
                    cc1, cc2 = st.columns([4, 1])
                    cc1.write(f)
                    if cc2.button("X", key=f"df_{f}"):
                        with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE nome=:n"), {"n": f}); st.rerun()
        
        key_c = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []

        with st.container(border=True):
            ci, cq = st.columns([3, 1])
            it_nome = ci.text_input("Digite o Produto", key="in_it")
            it_qtd = cq.text_input("Qtd", key="in_qt")
            if st.button("➕ Adicionar Linha"):
                if it_nome: st.session_state[key_c].append({"item": it_nome, "qtd": it_qtd}); st.rerun()

        for i, v in enumerate(st.session_state[key_c]):
            c1, c2, c3 = st.columns([3, 1, 0.5])
            v['item'] = c1.text_input(f"Item {i}", v['item'], key=f"ei_{i}")
            v['qtd'] = c2.text_input(f"Qtd {i}", v['qtd'], key=f"eq_{i}")
            if c3.button("🗑️", key=f"di_{i}"): st.session_state[key_c].pop(i); st.rerun()

        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
            txt = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_c]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,:f,:i,'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
            st.session_state[key_c] = []; st.success("Enviado!"); st.rerun()

    with t2:
        st.subheader("🌾 Pedidos Granel")
        if 'g_cart' not in st.session_state: st.session_state.g_cart = []
        with st.container(border=True):
            cg1, cg2, cg3 = st.columns([2, 1, 1])
            git = cg1.text_input("Produto Granel")
            gqt = cg2.text_input("Qtd")
            gdt = cg3.date_input("Data Entrega")
            if st.button("Adicionar Granel"):
                st.session_state.g_cart.append({"item": git, "qtd": gqt, "data": gdt.strftime("%d/%m/%Y")})
                st.rerun()
        
        for i, g in enumerate(st.session_state.g_cart):
            col1, col2, col3, col4 = st.columns([2,1,1,0.5])
            g['item'] = col1.text_input(f"G_it_{i}", g['item'])
            g['qtd'] = col2.text_input(f"G_qt_{i}", g['qtd'])
            if col4.button("X", key=f"dg_{i}"): st.session_state.g_cart.pop(i); st.rerun()

        if st.session_state.g_cart and st.button("Enviar Granel", type="primary"):
            txt_g = ", ".join([f"{x['qtd']}x {x['item']} (Entrega: {x['data']})" for x in st.session_state.g_cart])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,'GRANEL',:i,'Granel')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "i": txt_g})
            st.session_state.g_cart = []; st.success("Granel Enviado!"); st.rerun()

    with t3:
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        for _, r in df_h.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['data']} - {r['status']}"):
                novo_txt = st.text_area("Reeditar Pedido", r['itens'], key=f"hi_{r['id']}")
                if st.button("Salvar Alteração", key=f"h_sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": novo_txt, "id": r['id']})
                    st.rerun()

# --- TELA ADM ---
elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento ADM")
    tp, tg, ta = st.tabs(["⏳ Pendentes", "🌾 Granel", "✅ Atendidos"])
    
    with tp:
        df = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Normal' ORDER BY id DESC"), engine)
        sel_ids = []
        for _, r in df.iterrows():
            c_sel, c_exp = st.columns([0.1, 0.9])
            if c_sel.checkbox("", key=f"sel_{r['id']}"): sel_ids.append(r['id'])
            with c_exp.expander(f"LOJA: {r['loja']} | Pedido: {r['id']} | Data: {r['data']}"):
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
            if st.button("Marcar como Atendido", type="primary"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id IN :ids"), {"ids": tuple(sel_ids)})
                st.rerun()
            st.download_button("Gerar PDF Selecionados", data=gerar_pdf(df[df['id'].isin(sel_ids)]), file_name="pedidos.pdf")

    with tg:
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

# --- TELA PEDIDOS AVULSOS ---
elif st.session_state.menu == "Avulsos":
    st.header("📝 Pedidos Avulsos (Manual)")
    if 'av_cart' not in st.session_state: st.session_state.av_cart = []
    with st.form("f_av"):
        f_av = st.text_input("Fornecedor")
        d_av = st.date_input("Data")
        it_av = st.text_input("Item")
        qt_av = st.text_input("Qtd")
        if st.form_submit_button("Adicionar"):
            st.session_state.av_cart.append({"item": it_av, "qtd": qt_av, "forn": f_av, "data": d_av.strftime("%d/%m/%Y")})
    
    for i, x in enumerate(st.session_state.av_cart):
        st.write(f"{x['qtd']}x {x['item']} - {x['forn']}")
        if st.button("Remover", key=f"rav_{i}"): st.session_state.av_cart.pop(i); st.rerun()
    
    if st.session_state.av_cart and st.button("Gerar PDF e Finalizar"):
        txt_av = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.av_cart])
        df_v = pd.DataFrame([{"id": "AV", "loja": "AVULSO", "fornecedor": f_av, "data": d_av.strftime("%d/%m/%Y"), "itens": txt_av}])
        st.download_button("Baixar PDF", data=gerar_pdf(df_v), file_name="avulso.pdf")

# --- TELA LISTA DE PRODUTOS ---
elif st.session_state.menu == "Prods":
    st.header("🍎 Lista de Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar Produto"):
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np.upper()}); st.rerun()
    
    df_p = pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine)
    st.dataframe(df_p, use_container_width=True)
    for _, r in df_p.iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(r['nome'])
        if c2.button("X", key=f"dp_{r['id']}"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM produtos WHERE id=:id"), {"id": r['id']}); st.rerun()

# --- TELA CONFIG ---
elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    t_lojas, t_logins = st.tabs(["🏢 Lojas", "🔐 Logins"])
    
    with t_lojas:
        nl = st.text_input("Nome da Loja")
        if st.button("Gravar Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl.upper()}); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4,1]); c1.write(r['nome'])
            if c2.button("X", key=f"dl_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); st.rerun()
                
    with t_logins:
        with st.form("f_log"):
            u_l = st.text_input("Login")
            u_s = st.text_input("Senha")
            u_v = st.selectbox("Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()] + ["ADMINISTRAÇÃO"])
            u_n = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Gerar Login"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u,:s,:l,:n)"), {"u": u_l, "s": u_s, "l": u_v, "n": u_n})
                st.rerun()
