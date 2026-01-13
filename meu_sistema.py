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

# --- 3. SISTEMA DE ALERTA (BARRA LATERAL) ---
def verificar_alertas():
    if st.session_state.nivel == 'admin':
        with engine.connect() as conn:
            qtd = conn.execute(text("SELECT COUNT(*) FROM pedidos WHERE status = 'Pendente'")).scalar()
            if qtd > 0:
                st.sidebar.error(f"⚠️ {qtd} PEDIDOS PENDENTES!")

# --- 4. NAVEGAÇÃO ---
def navegar(d): st.session_state.menu = d

# Tenta carregar a logo. Se não conseguir, usa o texto NIYATI
try:
    # use_container_width=True faz com que ela se ajuste sozinha à largura da barra lateral
    st.sidebar.image("LOGO EM ALTA QUALIDADE niyati.jpg", use_container_width=True)
except:
    st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>NIYATI</h2>", unsafe_allow_html=True)

st.sidebar.info(f"Loja: {st.session_state.loja_atual}")

# Alerta de pedidos pendentes (logo abaixo da logo/info da loja)
verificar_alertas()

st.sidebar.divider() # Uma linha fina para separar a logo dos botões

# Botões de Navegação
st.sidebar.button("🛒 PEDIDOS", on_click=navegar, args=("Pedidos",), use_container_width=True)
# ... restante dos botões
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
    pdf = FPDF()
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
        
        # GERENCIAR FORNECEDORES (FIXO AGORA)
        with st.expander("➕/➖ Adicionar ou Excluir Fornecedores", expanded=False):
            nf = st.text_input("Nome do Novo Fornecedor")
            if st.button("Gravar Fornecedor", type="primary"):
                if nf:
                    with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf.upper()})
                    st.rerun()
            for f in forns:
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f)
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
                for it in r['itens'].split(", "):
                    q, n = it.split("x ", 1) if "x " in it else ("1", it)
                    st.markdown(f"**<span style='color:red'>{q}</span>** - {n}", unsafe_allow_html=True)
                edit_adm = st.text_area("Editar Texto", r['itens'], key=f"adm_ed_{r['id']}")
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
                st.write(r['itens'])
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
                st.write(r['itens'])
                if st.button("Excluir Histórico", key=f"dat_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()
        if sel_at:
            c1, c2 = st.columns(2)
            c1.download_button("📄 GERAR PDF ATENDIDOS", data=gerar_pdf_bonito(df_at[df_at['id'].isin(sel_at)]), file_name="atendidos.pdf")
            if c2.button("🗑️ EXCLUIR SELECIONADOS"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id IN :ids"), {"ids": tuple(sel_at)})
                st.rerun()

elif st.session_state.menu == "Avulsos":
    st.header("📝 Pedidos Avulsos")
    if 'av_cart' not in st.session_state: st.session_state.av_cart = []
    f_av = st.text_input("Fornecedor", key="f_av_man")
   with st.container(border=True):
            ci, cq = st.columns([3, 1])
            
            # CAMPO ÚNICO INTELIGENTE (ESTILO GOOGLE)
            # O usuário pode selecionar da lista ou digitar um novo e apertar ENTER
            lista_sugestoes = prods if 'prods' in locals() else []
            
            p_input = ci.multiselect(
                "Produto (Busca ou Digita novo + Enter)",
                options=lista_sugestoes,
                max_selections=1,
                placeholder="Comece a digitar o produto...",
                key=f"search_{st.session_state.loja_atual}"
            )
            
            # Se selecionou da lista, usa o selecionado. Se não, tenta pegar o que foi digitado
            produto_final = p_input[0] if p_input else ""
            
            # Caso o item seja totalmente novo e não esteja na lista de sugestões:
            if not produto_final:
                produto_final = ci.text_input("Ou digite o novo item aqui:", key=f"manual_{st.session_state.loja_atual}")

            it_q = cq.text_input("Qtd", key="qt_n")
            
            if st.button("➕ Adicionar Linha", key=f"btn_add_{st.session_state.loja_atual}"):
                if produto_final:
                    st.session_state[key_c].append({"item": produto_final, "qtd": it_q})
                    st.rerun()
    for i, v in enumerate(st.session_state.av_cart):
        c1, c2, c3 = st.columns([3, 1, 0.5])
        v['item'] = c1.text_input(f"Ai_{i}", v['item'])
        v['qtd'] = c2.text_input(f"Aq_{i}", v['qtd'])
        if c3.button("❌", key=f"dav_{i}"): st.session_state.av_cart.pop(i); st.rerun()
    if st.session_state.av_cart:
        txt_av = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.av_cart])
        df_v = pd.DataFrame([{"id": "AV", "loja": "AVULSO", "fornecedor": f_av, "data": datetime.now().strftime("%d/%m/%Y"), "itens": txt_av}])
        st.download_button("📄 GERAR PDF AVULSO", data=gerar_pdf_bonito(df_v), file_name="avulso.pdf")

elif st.session_state.menu == "Prods":
    st.header("🍎 Lista de Produtos")
    np = st.text_input("Novo Produto")
    if st.button("Salvar Produto"):
        with engine.begin() as conn: conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np.upper()}); st.rerun()
    df_p = pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine)
    if not df_p.empty:
        df_exp = pd.DataFrame([{"id":"-","loja":"LISTA GERAL","fornecedor":"NIYATI","data":"","itens":", ".join(df_p['nome'].tolist())}])
        st.download_button("📄 EXPORTAR PDF", data=gerar_pdf_bonito(df_exp), file_name="produtos.pdf")
        for _, r in df_p.iterrows():
            c1, c2 = st.columns([4, 1]); c1.write(r['nome'])
            if c2.button("X", key=f"dp_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM produtos WHERE id=:id"), {"id": r['id']}); st.rerun()

elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações")
    t1, t2 = st.tabs(["🏢 Lojas", "🔐 Logins"])
    with t1:
        nl = st.text_input("Nome da Loja")
        if st.button("Gravar Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl.upper()}); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            c1, c2 = st.columns([4,1]); c1.write(r['nome'])
            if c2.button("X", key=f"dl_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); st.rerun()
    with t2:
        df_u = pd.read_sql(text("SELECT * FROM usuarios"), engine)
        for _, r in df_u.iterrows():
            with st.expander(f"Login: {r['login']} (Loja: {r['nome_loja']})"):
                ns = st.text_input("Senha", r['senha'], key=f"ps_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Atualizar", key=f"bu_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": ns, "id": r['id']})
                    st.rerun()
                if c2.button("Excluir Login", key=f"be_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()




