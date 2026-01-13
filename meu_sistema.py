import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="NIYATI - SISTEMA", layout="wide")

@st.cache_resource
def get_engine():
    url = st.secrets["connections"]["postgresql"]["url"] if "connections" in st.secrets else st.secrets["database"]["url"]
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_size=20)

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
            else: st.error("Senha ou Usuário Inválido")
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

# --- 4. FUNÇÃO PDF ---
def exportar_pdf(df, titulo="Relatório de Pedidos"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, titulo, ln=True, align='C'); pdf.ln(10)
    for _, r in df.iterrows():
        pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, f"Loja: {r['loja']} | Pedido: {r['id']} | Data: {r['data']}", ln=True)
        pdf.set_font("Arial", '', 10); pdf.multi_cell(0, 8, f"Itens:\n{r['itens']}"); pdf.ln(5)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. TELAS ---

# --- TELA PEDIDOS ---
if st.session_state.menu == "Pedidos":
    st.header(f"Área de Pedidos - {st.session_state.loja_atual}")
    t1, t2, t3 = st.tabs(["🛒 Novo Pedido", "📦 Pedidos Granel", "⏳ Histórico"])

    with t1:
        with engine.connect() as conn:
            forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
        
        c1, c2 = st.columns([3, 1])
        f_sel = c1.selectbox("Selecione Fornecedor", forns)
        if c2.button("➕/➖ Fornecedor"): st.session_state.show_f = not st.session_state.get('show_f', False)
        
        if st.session_state.get('show_f'):
            with st.expander("Gerenciar Fornecedores"):
                nf = st.text_input("Novo Fornecedor")
                if st.button("Gravar"):
                    with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf}); st.rerun()
        
        key_c = f"cart_{st.session_state.loja_atual}_{f_sel}"
        if key_c not in st.session_state: st.session_state[key_c] = []

        with st.container(border=True):
            ci, cq = st.columns([3, 1])
            it = ci.text_input("Digite o Produto")
            qt = cq.text_input("Qtd")
            if st.button("➕ Adicionar Item"):
                if it and qt: st.session_state[key_c].append({"item": it, "qtd": qt}); st.rerun()

        for i, v in enumerate(st.session_state[key_c]):
            cc1, cc2, cc3, cc4 = st.columns([2, 1, 1, 1])
            v['item'] = cc1.text_input(f"Item {i}", v['item'], key=f"edit_it_{i}")
            v['qtd'] = cc2.text_input(f"Qtd {i}", v['qtd'], key=f"edit_qt_{i}")
            if cc3.button("🗑️", key=f"del_{i}"): st.session_state[key_c].pop(i); st.rerun()

        if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO FINAL", type="primary"):
            txt = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state[key_c]])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,:f,:i,'Normal')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "f": f_sel, "i": txt})
            st.session_state[key_c] = []; st.success("Enviado!"); st.rerun()

    with t2:
        st.subheader("Pedidos Granel")
        if 'granel_cart' not in st.session_state: st.session_state.granel_cart = []
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            it_g = col1.text_input("Item Granel")
            qt_g = col2.text_input("Qtd Granel")
            dt_g = col3.date_input("Data Entrega")
            if st.button("Add Granel"):
                st.session_state.granel_cart.append({"item": it_g, "qtd": qt_g, "data": dt_g.strftime("%d/%m/%Y")})
                st.rerun()
        
        for i, g in enumerate(st.session_state.granel_cart):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            g['item'] = c1.text_input(f"G_it_{i}", g['item'])
            g['qtd'] = c2.text_input(f"G_qt_{i}", g['qtd'])
            if c4.button("Excluir", key=f"del_g_{i}"): st.session_state.granel_cart.pop(i); st.rerun()
        
        if st.session_state.granel_cart and st.button("Enviar Granel", type="primary"):
            txt_g = ", ".join([f"{x['qtd']}x {x['item']}" for x in st.session_state.granel_cart])
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens, tipo) VALUES (:d,:l,'GRANEL',:i,'Granel')"),
                             {"d": datetime.now().strftime("%d/%m/%Y"), "l": st.session_state.loja_atual, "i": txt_g})
            st.session_state.granel_cart = []; st.success("Granel Enviado!"); st.rerun()

    with t3:
        df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{st.session_state.loja_atual}' ORDER BY id DESC"), engine)
        for _, r in df_h.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['data']} - {r['status']}"):
                novo_it = st.text_area("Editar Pedido Enviado", r['itens'], key=f"hist_{r['id']}")
                if st.button("Salvar Alteração", key=f"btn_h_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": novo_it, "id": r['id']})
                    st.rerun()

# --- TELA ADM ---
elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento de Pedidos")
    tab_p, tab_g, tab_at = st.tabs(["⏳ Pendentes", "🌾 Granel", "✅ Atendidos"])
    
    with tab_p:
        df = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Normal' ORDER BY id DESC"), engine)
        sel_pedidos = []
        for _, r in df.iterrows():
            col_sel, col_exp = st.columns([0.1, 0.9])
            if col_sel.checkbox("", key=f"sel_{r['id']}"): sel_pedidos.append(r['id'])
            with col_exp.expander(f"LOJA: {r['loja']} | Nº: {r['id']} | DATA: {r['data']}"):
                # Mostrar itens um abaixo do outro com QTD colorida
                itens_lista = r['itens'].split(", ")
                for it in itens_lista:
                    q, n = it.split("x ", 1) if "x " in it else ("?", it)
                    st.markdown(f"**<span style='color:red'>{q}</span>** - {n}", unsafe_allow_html=True)
                
                edit_itens = st.text_area("Editar Itens (Texto Bruto)", r['itens'], key=f"adm_ed_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("💾 Salvar", key=f"adm_sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": edit_itens, "id": r['id']})
                    st.rerun()
                if c2.button("❌ Excluir Pedido", key=f"adm_del_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()
        
        if sel_pedidos:
            c1, c2 = st.columns(2)
            if c1.button("✅ MARCAR COMO ATENDIDO"):
                with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id IN :ids"), {"ids": tuple(sel_pedidos)})
                st.rerun()
            c2.download_button("📄 Gerar PDF", data=exportar_pdf(df[df['id'].isin(sel_pedidos)]), file_name="pedidos_adm.pdf")

    with tab_g:
        df_g = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Pendente' AND tipo = 'Granel' ORDER BY id DESC"), engine)
        for _, r in df_g.iterrows():
            with st.expander(f"GRANEL: {r['loja']} - {r['data']}"):
                st.write(r['itens'])
                if st.button("Atender Granel", key=f"at_g_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                    st.rerun()

    with tab_at:
        df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
        st.dataframe(df_at, use_container_width=True)

# --- TELA CONFIGURAÇÕES ---
elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações Gerais")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Lojas")
        nl = st.text_input("Nova Loja")
        if st.button("Add Loja"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl}); st.rerun()
        for r in pd.read_sql(text("SELECT * FROM lojas"), engine).to_dict('records'):
            cc1, cc2 = st.columns([3, 1]); cc1.write(r['nome'])
            if cc2.button("X", key=f"l_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); st.rerun()
    
    st.divider()
    st.subheader("Gerenciar Logins")
    with st.form("f_login"):
        u_log = st.text_input("Login (Ex: user01)")
        u_sen = st.text_input("Senha")
        u_vinc = st.selectbox("Vincular à Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()])
        u_niv = st.selectbox("Nível", ["vendedor", "admin"])
        if st.form_submit_button("Criar Acesso"):
            with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (login, senha, nome_loja, nivel_acesso) VALUES (:u,:s,:l,:n)"), {"u": u_log, "s": u_sen, "l": u_vinc, "n": u_niv})
            st.rerun()

    for r in pd.read_sql(text("SELECT * FROM usuarios"), engine).to_dict('records'):
        with st.expander(f"Login: {r['login']} -> {r['nome_loja']}"):
            ns = st.text_input("Mudar Senha", key=f"pw_{r['id']}")
            if st.button("Salvar Senha", key=f"btn_pw_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": ns, "id": r['id']})
                st.rerun()
