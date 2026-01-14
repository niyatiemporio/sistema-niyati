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

# --- FUNÇÃO DE CORREÇÃO AUTOMÁTICA ---
def corrigir_tabela_produtos():
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE produtos ADD COLUMN IF NOT EXISTS fornecedor TEXT DEFAULT 'GERAL'"))
        st.success("Coluna de fornecedor verificada/adicionada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao atualizar banco: {e}")

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

# --- 3. ALERTA ---
def verificar_alertas():
    if st.session_state.nivel == 'admin':
        with engine.connect() as conn:
            qtd = conn.execute(text("SELECT COUNT(*) FROM pedidos WHERE status = 'Pendente'")).scalar()
            if qtd > 0:
                st.sidebar.error(f"⚠️ {qtd} PEDIDOS PENDENTES!")

# --- 4. NAVEGAÇÃO ---
def navegar(d): st.session_state.menu = d

st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.info(f"Loja: {st.session_state.loja_atual}")

verificar_alertas()

st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Avulsos",), use_container_width=True)
    st.sidebar.button("🍎 LISTA DE PRODUTOS", on_click=navegar, args=("Prods",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 SAIR", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 5. FUNÇÃO PDF ---
def gerar_pdf_bonito(df, titulo="ORDEM DE PEDIDO"):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, r in df.iterrows():
        pdf.add_page()
        pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 15, f"LOJA: {str(r['loja']).upper()}", ln=True, align='C', fill=True)
        pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", 'B', 10); pdf.ln(5)
        pdf.cell(95, 8, f"FORNECEDOR: {r['fornecedor']}", border='B')
        pdf.cell(95, 8, f"DATA: {r['data']} | N: {r['id']}", border='B', ln=True, align='R')
        pdf.ln(5); pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 10)
        pdf.cell(30, 10, "QTD", border=1, align='C', fill=True)
        pdf.cell(160, 10, "DESCRIÇÃO DO PRODUTO", border=1, align='C', fill=True); pdf.ln()
        pdf.set_font("Arial", '', 10)
        for it in str(r['itens']).split(", "):
            q, n = it.split("x ", 1) if "x " in it else ("1", it)
            pdf.cell(30, 8, q, border=1, align='C')
            pdf.cell(160, 8, f" {n}", border=1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- 6. TELAS ---

if st.session_state.menu == "Pedidos":
    st.header(f"🛒 Área de Pedidos")
    t1, t2, t3 = st.tabs(["🛒 Novo Pedido", "📦 Pedidos Granel", "⏳ Histórico"])

    with t1:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        # --- BLOCO RE-ADICIONADO: GERENCIAR FORNECEDORES ---
        with st.expander("➕/➖ Adicionar ou Excluir Fornecedores", expanded=False):
            nf = st.text_input("Nome do Novo Fornecedor")
            if st.button("Gravar Fornecedor", type="primary"):
                if nf:
                    with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()})
                    st.rerun()
            st.divider()
            for f in forns:
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f"🚚 {f}")
                if cc2.button("X", key=f"del_f_loja_{f}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE nome=:n"), {"n": f})
                    st.rerun()
        
        st.divider()
        f_sel = st.selectbox("Selecione o Fornecedor para o Pedido", forns)
        key_c = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []
        
        with st.container(border=True):
            ci, cq = st.columns([3, 1])
            it_n = ci.text_input("Produto", key="it_n")
            it_q = cq.text_input("Qtd", key="qt_n")
            if st.button("➕ Adicionar Linha"):
                if it_n: st.session_state[key_c].append({"item": it_n, "qtd": it_q}); st.rerun()

        for i, v in enumerate(st.session_state[key_c]):
            c1, c2, c3 = st.columns([3, 1, 0.5])
            v['item'] = c1.text_input(f"It_{i}", v['item'], key=f"ei_{i}")
            v['qtd'] = c2.text_input(f"Qt_{i}", v['qtd'], key=f"eq_{i}")
            if c3.button("❌", key=f"di_{i}"): st.session_state[key_c].pop(i); st.rerun()
        
        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO", type="primary"):
            txt = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_c]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,:f,:i,'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
            st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()

    with t2:
        st.subheader("🌾 Pedidos Granel")
        if 'g_cart' not in st.session_state: st.session_state.g_cart = []
        with st.container(border=True):
            cg1, cg2 = st.columns([3, 1])
            git = cg1.text_input("Produto Granel", key="git")
            gqt = cg2.text_input("Qtd", key="gqt")
            if st.button("➕ Adicionar Item Granel"):
                if git: st.session_state.g_cart.append({"item": git, "qtd": gqt}); st.rerun()
        for i, g in enumerate(st.session_state.g_cart):
            c1, c2, c3 = st.columns([3, 1, 0.5])
            g['item'] = c1.text_input(f"G_it_{i}", g['item'], key=f"edit_g_it_{i}")
            g['qtd'] = c2.text_input(f"G_qt_{i}", g['qtd'], key=f"edit_g_qt_{i}")
            if c3.button("❌", key=f"dg_{i}"): st.session_state.g_cart.pop(i); st.rerun()
        if st.session_state.g_cart and st.button("Enviar Granel", type="primary"):
            txt_g = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.g_cart])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,'GRANEL',:i,'Granel')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "i": txt_g})
            st.session_state.g_cart = []; st.success("Granel Enviado!"); st.rerun()

    with t3:
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        for _, r in df_h.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['data']} - {r['status']}"):
                novo_t = st.text_area("Reeditar", r['itens'], key=f"hi_{r['id']}")
                if st.button("Salvar Alteração", key=f"h_sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": novo_t, "id": r['id']})
                    st.rerun()

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
                lista_itens = r['itens'].split(", ")
                for it in lista_itens: st.markdown(f"• {it}")
                edit_adm = st.text_area("Editar Pedido", r['itens'], key=f"adm_ed_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Salvar", key=f"as_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": edit_adm, "id": r['id']})
                    st.rerun()
                if c2.button("Excluir", key=f"ad_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()
        if sel_ids:
            col1, col2 = st.columns(2)
            if col1.button("✅ ATENDER SELECIONADOS", type="primary"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id IN :ids"), {"ids": tuple(sel_ids)})
                st.rerun()
            col2.download_button("📄 GERAR PDF", data=gerar_pdf_bonito(df[df['id'].isin(sel_ids)]), file_name="pedidos.pdf")

    with tg:
        df_g = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Granel' ORDER BY id DESC"), engine)
        sel_g = []
        for _, r in df_g.iterrows():
            c_s, c_e = st.columns([0.1, 0.9])
            if c_s.checkbox("", key=f"sg_{r['id']}"): sel_g.append(r['id'])
            with c_e.expander(f"GRANEL: {r['loja']} - {r['data']}"):
                lista_g = r['itens'].split(", ")
                for item_g in lista_g: st.write(f"• {item_g}")
        if sel_g:
            c1, c2 = st.columns(2)
            if c1.button("✅ ATENDER GRANEL", type="primary"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id IN :ids"), {"ids": tuple(sel_g)})
                st.rerun()
            c2.download_button("📄 PDF GRANEL", data=gerar_pdf_bonito(df_g[df_g['id'].isin(sel_g)]), file_name="granel.pdf")

    with ta:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        sel_at = []
        for _, r in df_at.iterrows():
            c_s, c_e = st.columns([0.1, 0.9])
            if c_s.checkbox("", key=f"sat_{r['id']}"): sel_at.append(r['id'])
            with c_e.expander(f"LOJA: {r['loja']} | N: {r['id']} | DATA: {r['data']}"):
                lista_at = r['itens'].split(", ")
                for item_at in lista_at: st.write(f"• {item_at}")
                edit_at = st.text_area("Editar Histórico", r['itens'], key=f"at_ed_{r['id']}")
                col_at1, col_at2 = st.columns(2)
                if col_at1.button("Salvar Edição", key=f"at_sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": edit_at, "id": r['id']})
                    st.rerun()
                if col_at2.button("Excluir", key=f"dat_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()
        if sel_at:
            c1, c2 = st.columns(2)
            c1.download_button("📄 GERAR PDF", data=gerar_pdf_bonito(df_at[df_at['id'].isin(sel_at)]), file_name="atendidos.pdf")
            if c2.button("🗑️ EXCLUIR SELECIONADOS"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id IN :ids"), {"ids": tuple(sel_at)})
                st.rerun()

elif st.session_state.menu == "Avulsos":
    st.header("📝 Pedidos Avulsos")
    if 'av_cart' not in st.session_state: st.session_state.av_cart = []
    f_av = st.text_input("Fornecedor", key="f_av_man")
    
    with engine.connect() as conn:
        lista_prods = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
    
    with st.container(border=True):
        st.write("### Adicionar Item")
        col_bus, col_dig, col_q = st.columns([2, 2, 1])
        it_bus = col_bus.selectbox("Buscar Produto", [""] + lista_prods, key="bus_av")
        it_dig = col_dig.text_input("Ou Digite o Produto", key="dig_av")
        qt_av = col_q.text_input("Qtd", key="av_qt_new")
        if st.button("➕ Adicionar à Lista"):
            final_it = it_bus if it_bus != "" else it_dig
            if final_it:
                st.session_state.av_cart.append({"item": final_it, "qtd": qt_av})
                st.rerun()
    
    for i, v in enumerate(st.session_state.av_cart):
        col_it, col_qt, col_del = st.columns([3, 1, 0.5])
        v['item'] = col_it.text_input(f"Av_It_{i}", v['item'], key=f"edit_av_it_{i}")
        v['qtd'] = col_qt.text_input(f"Av_Qt_{i}", v['qtd'], key=f"edit_av_qt_{i}")
        if col_del.button("❌", key=f"dav_{i}"): st.session_state.av_cart.pop(i); st.rerun()
    
    if st.session_state.av_cart:
        col_pdf, col_atender = st.columns(2)
        txt_av = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.av_cart])
        df_v = pd.DataFrame([{"id": "AV", "loja": "AVULSO", "fornecedor": f_av, "data": datetime.now().strftime("%d/%m/%Y"), "itens": txt_av}])
        col_pdf.download_button("📄 GERAR PDF AVULSO", data=gerar_pdf_bonito(df_v), file_name="avulso.pdf")
        if col_atender.button("🚀 FINALIZAR E MOVER PARA ATENDIDOS", type="primary"):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, status, tipo) VALUES (:d, 'AVULSO', :f, :i, 'Atendido', 'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "f": f_av, "i": txt_av})
            st.session_state.av_cart = []; st.success("Pedido finalizado!"); st.rerun()

elif st.session_state.menu == "Prods":
    st.header("🍎 Lista de Produtos")
    with engine.connect() as conn:
        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
    
    with st.form("add_prod"):
        c1, c2 = st.columns([2,1])
        np = c1.text_input("Novo Produto")
        fp = c2.selectbox("Fornecedor", forns)
        if st.form_submit_button("Salvar Produto"):
            with engine.begin() as conn: 
                conn.execute(text("INSERT INTO produtos (nome, fornecedor) VALUES (:n, :f)"), {"n": np.upper(), "f": fp})
            st.rerun()
            
    try:
        df_p = pd.read_sql(text("SELECT * FROM produtos ORDER BY fornecedor, nome"), engine)
        for f in forns:
            with st.expander(f"📦 PRODUTOS: {f}"):
                df_f = df_p[df_p['fornecedor'] == f]
                for _, r in df_f.iterrows():
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"🔹 {r['nome']}")
                    if c2.button("Excluir", key=f"dp_{r['id']}"):
                        with engine.begin() as conn: conn.execute(text("DELETE FROM produtos WHERE id=:id"), {"id": r['id']})
                        st.rerun()
    except:
        st.warning("Clique no botão 'CORRIGIR BANCO DE DADOS' na aba Configurações.")

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    if st.button("🔧 CORRIGIR BANCO DE DADOS (CLIQUE AQUI UMA VEZ)", type="secondary"):
        corrigir_tabela_produtos()
        st.rerun()
        
    t1, t2 = st.tabs(["🏢 Lojas", "🔐 Logins"])
    with t1:
        nl = st.text_input("Nome da Loja")
        if st.button("Gravar Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl.upper()})
            st.rerun()
        df_lojas = pd.read_sql(text("SELECT * FROM lojas"), engine)
        for _, r in df_lojas.iterrows():
            c1, c2 = st.columns([4,1]); c1.write(r['nome'])
            if c2.button("X", key=f"dl_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()
    with t2:
        with st.form("form_novo_usuario"):
            c1, c2 = st.columns(2)
            novo_u = c1.text_input("Login")
            nova_s = c2.text_input("Senha", type="password")
            with engine.connect() as conn: lista_lojas = [r[0] for r in conn.execute(text("SELECT nome FROM lojas ORDER BY nome")).fetchall()]
            loja_sel = st.selectbox("Atribuir à Loja", options=["ADMIN"] + lista_lojas)
            nivel_sel = st.selectbox("Nível de Acesso", options=["vendedor", "admin"])
            if st.form_submit_button("Gerar Acesso"):
                if novo_u and nova_s:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u, :s, :l, :n)"),
                                     {"u": novo_u, "s": nova_s, "l": loja_sel, "n": nivel_sel})
                    st.success(f"Acesso para {novo_u} criado!"); st.rerun()
        st.divider()
        df_u = pd.read_sql(text("SELECT * FROM usuarios"), engine)
        for _, r in df_u.iterrows():
            with st.expander(f"👤 {r['login']} (Loja: {r['nome_loja']})"):
                ns = st.text_input("Senha", r['senha'], key=f"ps_{r['id']}")
                if st.button("Excluir Login", key=f"be_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()
