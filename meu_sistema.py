import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO E CONEXÃO OTIMIZADA ---
st.set_page_config(page_title="SISTEMA NIYATI", layout="wide")

@st.cache_resource
def get_engine():
    # Detecta automaticamente a chave correta nos Secrets
    if "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
        url = st.secrets["connections"]["postgresql"]["url"]
    elif "database" in st.secrets:
        url = st.secrets["database"]["url"]
    else:
        st.error("Configure o Banco de Dados nos Secrets do Streamlit!")
        st.stop()
    url = url.strip().split("?")[0]
    if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(f"{url}?sslmode=require", pool_size=20, max_overflow=0)

engine = get_engine()

# --- 2. GESTÃO DE LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'nivel': None, 'loja_atual': None, 'menu': "Lojas"})

if not st.session_state.logado:
    st.title("🔑 Login - Sistema Niyati")
    u = st.text_input("Usuário (Nome da Loja)")
    s = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        with engine.connect() as conn:
            user = conn.execute(text("SELECT nivel_acesso FROM usuarios WHERE nome_loja = :u AND senha = :s"), {"u": u, "s": s}).fetchone()
            if user:
                st.session_state.update({'logado': True, 'nivel': user[0], 'loja_atual': u})
                st.rerun()
            else: st.error("Usuário ou senha incorretos")
    st.stop()

# --- 3. NAVEGAÇÃO LATERAL ---
def navegar(destino): st.session_state.menu = destino

st.sidebar.markdown("<h1 style='text-align: center; color: #007bff;'>NIYATI</h1>", unsafe_allow_html=True)
st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
st.sidebar.divider()

st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True)
if st.session_state.nivel == 'admin':
    st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True)
    st.sidebar.button("📝 PEDIDOS AVULSOS", on_click=navegar, args=("Gerar",), use_container_width=True)
    st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True)

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

# --- 4. FUNÇÕES PDF ---
def gerar_pdf(df):
    pdf = FPDF()
    for _, r in df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 20); pdf.cell(0, 15, txt=f"LOJA: {str(r['loja']).upper()}", ln=True)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, txt=f"Forn: {r['fornecedor']} | Data: {r['data']}", ln=True)
        pdf.ln(5); pdf.multi_cell(0, 10, txt=f"ITENS:\n{r['itens']}", border=1)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. TELAS ---

# --- LISTA DE PEDIDOS (Lojas) ---
if st.session_state.menu == "Lojas":
    st.header("🛒 Painel de Pedidos")
    with engine.connect() as conn:
        if st.session_state.nivel == 'admin':
            lojas_lista = [r[0] for r in conn.execute(text('SELECT nome FROM lojas ORDER BY nome')).fetchall()]
        else:
            lojas_lista = [st.session_state.loja_atual]
    
    if not lojas_lista: st.warning("Nenhuma loja cadastrada no sistema.")
    else:
        tabs = st.tabs(lojas_lista)
        for i, nome_l in enumerate(lojas_lista):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_l}", horizontal=True)
                if guia == "Novo Pedido":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
                        prods_sugestao = [r[0] for r in conn.execute(text('SELECT nome FROM produtos ORDER BY nome')).fetchall()]
                    
                    f_sel = st.selectbox("Selecione o Fornecedor", forns, key=f"f_{nome_l}")
                    
                    key_c = f"car_{nome_l}_{f_sel}"
                    if key_c not in st.session_state: st.session_state[key_c] = []

                    with st.container(border=True):
                        st.write("### Adicionar Produto")
                        # O campo ÚNICO que aceita digitar ou selecionar sugestões
                        it = st.selectbox("Sugestões de Produtos (ou digite abaixo)", [""] + prods_sugestao, key=f"sel_{nome_l}")
                        it_manual = st.text_input("Digite o produto aqui (se não estiver na lista)", key=f"man_{nome_l}")
                        
                        produto_final = it_manual if it_manual else it
                        qt = st.number_input("Qtd", min_value=1, key=f"qt_{nome_l}")
                        
                        if st.button("➕ Adicionar Linha", key=f"add_{nome_l}"):
                            if produto_final:
                                st.session_state[key_c].append(f"{qt}x {produto_final}")
                                st.rerun()

                    for idx, v in enumerate(st.session_state[key_c]):
                        c_txt, c_del = st.columns([4, 1])
                        c_txt.info(v)
                        if c_del.button("❌", key=f"del_{nome_l}_{idx}"): 
                            st.session_state[key_c].pop(idx); st.rerun()
                    
                    if st.session_state[key_c] and st.button("🚀 FINALIZAR E ENVIAR", type="primary", key=f"env_{nome_l}"):
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO pedidos (data, loja, fornecedor, itens) VALUES (:d,:l,:f,:i)"),
                                         {"d": datetime.now().strftime("%d/%m/%Y"), "l": nome_l, "f": f_sel, "i": ", ".join(st.session_state[key_c])})
                        st.session_state[key_c] = []; st.success("Pedido Enviado!"); st.rerun()
                else:
                    df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_l}' ORDER BY id DESC"), engine)
                    st.dataframe(df_h, use_container_width=True)

# --- GERENCIAMENTO ADM ---
elif st.session_state.menu == "ADM":
    st.header("⚙️ Gerenciamento de Pedidos (ADM)")
    t1, t2 = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
    with t1:
        df_p = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' ORDER BY id DESC"), engine)
        if df_p.empty: st.info("Nenhum pedido pendente.")
        for _, r in df_p.iterrows():
            with st.expander(f"Pedido #{r['id']} - {r['loja']} - {r['fornecedor']}"):
                txt_edit = st.text_area("Itens do Pedido", r['itens'], key=f"ed_{r['id']}")
                c1, c2, c3 = st.columns(3)
                if c1.button("💾 Salvar Alteração", key=f"sv_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET itens=:i WHERE id=:id"), {"i": txt_edit, "id": r['id']})
                    st.rerun()
                if c2.button("✅ Finalizar/Atendido", key=f"at_{r['id']}", type="primary"):
                    with engine.begin() as conn: conn.execute(text("UPDATE pedidos SET status='Atendido' WHERE id=:id"), {"id": r['id']})
                    st.rerun()
                if c3.button("🗑️ Excluir", key=f"del_p_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r['id']})
                    st.rerun()
    with t2:
        st.dataframe(pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine), use_container_width=True)

# --- PEDIDOS AVULSOS ---
elif st.session_state.menu == "Gerar":
    st.header("📝 Gerar Pedidos Avulsos (Unificados)")
    if 'car_av' not in st.session_state: st.session_state.car_av = []
    
    with engine.connect() as conn:
        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores ORDER BY nome')).fetchall()]
    
    f_av = st.selectbox("Fornecedor do Pedido Avulso", forns)
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        it_av = c1.text_input("Item / Produto")
        qt_av = c2.number_input("Qtd", min_value=1, key="q_av")
        if st.button("Adicionar à Lista"):
            if it_av: st.session_state.car_av.append(f"{qt_av}x {it_av}"); st.rerun()

    for idx, v in enumerate(st.session_state.car_av):
        cx, cd = st.columns([4, 1])
        cx.write(v)
        if cd.button("Remover", key=f"rav_{idx}"): st.session_state.car_av.pop(idx); st.rerun()
    
    if st.session_state.car_av:
        if st.button("📄 Gerar e Baixar PDF", type="primary"):
            df_v = pd.DataFrame([{"loja": "AVULSO", "fornecedor": f_av, "data": datetime.now().strftime("%d/%m/%Y"), "itens": ", ".join(st.session_state.car_av)}])
            st.download_button("Clique aqui para baixar", data=gerar_pdf(df_v), file_name="pedido_avulso.pdf")

# --- CONFIGURAÇÕES ---
elif st.session_state.menu == "Config":
    st.header("🛠️ Configurações do Sistema")
    tab1, tab2, tab3 = st.tabs(["Lojas", "Fornecedores", "Logins/Acessos"])
    
    with tab1:
        nl = st.text_input("Novo Nome de Loja")
        if st.button("Salvar Loja") and nl:
            with engine.begin() as conn: conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl})
            st.rerun()
        for r in pd.read_sql(text("SELECT * FROM lojas"), engine).to_dict('records'):
            c1, c2 = st.columns([4, 1]); c1.write(f"🏢 {r['nome']}")
            if c2.button("Excluir", key=f"dl_l_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']})
                st.rerun()

    with tab2:
        nf = st.text_input("Novo Fornecedor")
        if st.button("Salvar Fornecedor") and nf:
            with engine.begin() as conn: conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf})
            st.rerun()
        for r in pd.read_sql(text("SELECT * FROM fornecedores"), engine).to_dict('records'):
            c1, c2 = st.columns([4, 1]); c1.write(f"🚚 {r['nome']}")
            if c2.button("Excluir", key=f"dl_f_{r['id']}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM fornecedores WHERE id=:id"), {"id": r['id']})
                st.rerun()

    with tab3:
        st.subheader("Gerenciar Usuários")
        with st.form("f_user"):
            u_loja = st.selectbox("Selecione a Loja", [r[0] for r in engine.connect().execute(text("SELECT nome FROM lojas")).fetchall()] + ["ADMIN"])
            u_senha = st.text_input("Defina a Senha")
            u_nivel = st.selectbox("Nível", ["vendedor", "admin"])
            if st.form_submit_button("Criar Login"):
                with engine.begin() as conn: conn.execute(text("INSERT INTO usuarios (nome_loja, senha, nivel_acesso) VALUES (:n, :s, :a)"), {"n": u_loja, "s": u_senha, "a": u_nivel})
                st.rerun()
        
        for r in pd.read_sql(text("SELECT * FROM usuarios"), engine).to_dict('records'):
            with st.expander(f"👤 Login: {r['nome_loja']}"):
                ns = st.text_input("Nova Senha", key=f"ns_{r['id']}")
                if st.button("Atualizar Senha", key=f"btn_s_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("UPDATE usuarios SET senha=:s WHERE id=:id"), {"s": ns, "id": r['id']})
                    st.rerun()
                if st.button("Excluir Acesso", key=f"btn_d_{r['id']}"):
                    with engine.begin() as conn: conn.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": r['id']})
                    st.rerun()
