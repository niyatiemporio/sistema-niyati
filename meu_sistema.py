import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. FUNÇÕES DE LOGIN (CORRIGIDA) ---
def verificar_login(loja, senha):
    conn = st.connection("postgresql", type="sql")
    # Usamos f-string para a query simples, evitando problemas de hash com o objeto text()
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
            else:
                st.error("Usuário ou senha incorretos")
        else:
            st.warning("Por favor, preencha o usuário e a senha.")
else:
    # --- LOGADO COM SUCESSO ---
    st.sidebar.write(f"Conectado: **{st.session_state.loja_atual}**")
    
    opcoes_menu = ["Lista de Pedidos"]
    if st.session_state.nivel == 'admin':
        opcoes_menu += ["Gerenciamento", "Gerar Pedidos", "Produtos", "Configurações"]
    
    escolha = st.sidebar.radio("Navegação", opcoes_menu)
    
    if st.sidebar.button("Sair"):
        st.session_state.logado = False
        st.rerun()

    # --- 2. GESTÃO DO BANCO DE DADOS (CONEXÃO LIMPA) ---
    def conectar():
        if "database" in st.secrets:
            db_url = st.secrets["database"]["url"].strip()
            
            # Remove o prepare_threshold se ele estiver na URL do segredo
            if "?" in db_url:
                base_url = db_url.split("?")[0]
                db_url = f"{base_url}?sslmode=require"
            
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            
            return create_engine(db_url, pool_pre_ping=True)
        else:
            return create_engine('sqlite:///compras_niyati.db')

    def inicializar_banco():
        engine = conectar()
        with engine.begin() as conn:
            id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT DEFAULT "Enviado")'))
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))
            
            res = conn.execute(text('SELECT COUNT(*) FROM lojas')).fetchone()[0]
            if res == 0:
                conn.execute(text("INSERT INTO lojas (nome) VALUES ('Junqueirópolis'), ('Tupi Paulista'), ('Pres. Venceslau')"))
                conn.execute(text("INSERT INTO fornecedores (nome) VALUES ('Max Titanium'), ('Unilife'), ('Herbamed'), ('Flora Caps')"))

    inicializar_banco()
    engine = conectar()

    # --- 3. FUNÇÕES DE EXPORTAÇÃO ---
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

    # --- 4. NAVEGAÇÃO ---
    st.session_state.menu_selecionado = escolha

    # --- 5. TELA: LOJAS ---
    if st.session_state.menu_selecionado == "Lista de Pedidos":
        st.header("🛒 LISTA DE PEDIDOS DE COMPRA")
        with engine.connect() as conn:
            if st.session_state.nivel == 'admin':
                lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
            else:
                lojas_db = [st.session_state.loja_atual]
                
        tabs = st.tabs(lojas_db)
        for i, nome_loja in enumerate(lojas_db):
            with tabs[i]:
                guia = st.radio("Ação", ["Novo Pedido", "Histórico"], key=f"guia_{nome_loja}", horizontal=True)
                if guia == "Novo Pedido":
                    with engine.connect() as conn:
                        forns = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
                    c1, c2 = st.columns([3, 1])
                    f_sel = c1.selectbox("Fornecedor", forns, key=f"f_{nome_loja}")
                    if c2.button("➕ Novo Forn.", key=f"af_{nome_loja}"): st.session_state[f'pop_{nome_loja}'] = True
                    if st.session_state.get(f'pop_{nome_loja}'):
                        nf = st.text_input("Nome:", key=f"inf_{nome_loja}")
                        if st.button("Gravar", key=f"svf_{nome_loja}"):
                            with engine.connect() as conn:
                                conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf}); conn.commit()
                            st.session_state[f'pop_{nome_loja}'] = False; st.rerun()
                    key_c = f"car_{nome_loja}_{f_sel}"
                    if key_c not in st.session_state: st.session_state[key_c] = []
                    with st.container(border=True):
                        cp, cq = st.columns([4, 1]); it = cp.text_input("Produto", key=f"it_{nome_loja}"); qt = cq.number_input("Qtd", min_value=1, key=f"qt_{nome_loja}")
                        if st.button("Adicionar Linha", key=f"add_{nome_loja}"):
                            if it: st.session_state[key_c].append({"Item": it, "Qtd": qt}); st.rerun()
                    for idx, v in enumerate(st.session_state[key_c]):
                        cc1, cc2, cc3 = st.columns([3, 1, 1]); st.session_state[key_c][idx]['Item'] = cc1.text_input(f"Item {idx}", v['Item'], key=f"ed_{nome_loja}_{idx}"); cc2.write(f"{v['Qtd']} un")
                        if cc3.button("❌", key=f"del_{nome_loja}_{idx}"): st.session_state[key_c].pop(idx); st.rerun()
                    if st.session_state[key_c] and st.button("🚀 ENVIAR PEDIDO FINAL", type="primary", key=f"env_{nome_loja}"):
                        txt = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state[key_c]])
                        with engine.connect() as conn:
                            conn.execute(text('INSERT INTO pedidos (data, loja, fornecedor, itens, status) VALUES (:d,:l,:f,:i,:s)'), 
                                         {"d": datetime.now().strftime("%d/%m/%Y %H:%M"), "l": nome_loja, "f": f_sel, "i": txt, "s": "Enviado"})
                            conn.commit()
                        st.session_state[key_c] = []; st.success("Enviado!"); st.rerun()
                else:
                    df_h = pd.read_sql(text(f"SELECT * FROM pedidos WHERE loja = '{nome_loja}' ORDER BY id DESC"), engine)
                    for _, row in df_h.iterrows():
                        with st.expander(f"Pedido #{row['id']} - {row['fornecedor']} ({row['data']})"):
                            st.write(row['itens'])

    # --- 6. TELA: ADM (PENDENTES E ATENDIDOS) ---
    elif st.session_state.menu_selecionado == "Gerenciamento":
        st.header("⚙️ GERENCIAMENTO DE PEDIDOS (ADM)")
        tab_p, tab_a = st.tabs(["⏳ Pendentes", "✅ Atendidos"])
        
        with tab_p:
            df_adm = pd.read_sql(text("SELECT * FROM pedidos WHERE status != 'Atendido' OR status IS NULL ORDER BY id DESC"), engine)
            if not df_adm.empty:
                if 'ids_sel' not in st.session_state: st.session_state.ids_sel = []
                c1, c2, c3 = st.columns(3)
                if st.session_state.ids_sel:
                    df_sel = df_adm[df_adm['id'].isin(st.session_state.ids_sel)]
                    c1.download_button("📄 PDF", data=gerar_pdf_niyati(df_sel), file_name="pedidos.pdf")
                    if c2.button("✔️ MARCAR ATENDIDO", type="primary"):
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE pedidos SET status = 'Atendido' WHERE id IN :ids"), {"ids": tuple(st.session_state.ids_sel)})
                        st.session_state.ids_sel = []; st.rerun()
                    if c3.button("Limpar Seleção"): st.session_state.ids_sel = []; st.rerun()

                with engine.connect() as conn:
                    lojas_adm = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
                t_lojas = st.tabs(lojas_adm)
                for idx, n_loja in enumerate(lojas_adm):
                    with t_lojas[idx]:
                        df_l = df_adm[df_adm['loja'] == n_loja]
                        for _, r in df_l.iterrows():
                            c_ch, c_ex = st.columns([0.05, 0.95])
                            checked = c_ch.checkbox("", key=f"adm_p_{r['id']}", value=(r['id'] in st.session_state.ids_sel))
                            if checked and r['id'] not in st.session_state.ids_sel:
                                st.session_state.ids_sel.append(r['id'])
                                st.rerun()
                            elif not checked and r['id'] in st.session_state.ids_sel:
                                st.session_state.ids_sel.remove(r['id'])
                                st.rerun()
                            with c_ex.expander(f"Pedido #{r['id']} | {r['fornecedor']} | {r['data']}"):
                                st.write(r['itens'])
            else: st.info("Sem pedidos pendentes.")

        with tab_a:
            df_at = pd.read_sql(text("SELECT * FROM pedidos WHERE status = 'Atendido' ORDER BY id DESC"), engine)
            if not df_at.empty:
                st.dataframe(df_at[["id", "data", "loja", "fornecedor", "itens"]], use_container_width=True)
            else: st.info("Histórico de atendidos vazio.")

    elif st.session_state.menu_selecionado == "Gerar Pedidos":
        st.header("📝 GERAR PEDIDOS AVULSOS")
        if 'car_av' not in st.session_state: st.session_state.car_av = []
        with engine.connect() as conn:
            forns_l = [r[0] for r in conn.execute(text('SELECT nome FROM fornecedores')).fetchall()]
        f_av = st.selectbox("Fornecedor", forns_l)
        d_av = st.date_input("Data")
        with st.container(border=True):
            c1, c2 = st.columns([4, 1]); it = c1.text_input("Item"); qt = c2.number_input("Qtd", min_value=1)
            if st.button("Adicionar"):
                if it: st.session_state.car_av.append({"Item": it, "Qtd": qt}); st.rerun()
        for idx, v in enumerate(st.session_state.car_av):
            cc1, cc2, cc3 = st.columns([3, 1, 1]); cc1.write(v['Item']); cc2.write(f"{v['Qtd']} un")
            if cc3.button("Remover", key=f"rav_{idx}"): st.session_state.car_av.pop(idx); st.rerun()
        if st.session_state.car_av and st.button("📄 PDF"):
            tx = ", ".join([f"{x['Qtd']}x {x['Item']}" for x in st.session_state.car_av])
            df = pd.DataFrame([{"id": "AVULSO", "loja": "MANUAL", "fornecedor": f_av, "data": d_av.strftime("%d/%m/%Y"), "itens": tx}])
            st.download_button("Baixar", data=gerar_pdf_niyati(df), file_name="avulso.pdf")

    elif st.session_state.menu_selecionado == "Produtos":
        st.header("🍎 PRODUTOS")
        np = st.text_input("Novo:")
        if st.button("Salvar") and np:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np})
            st.rerun()
        st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

    elif st.session_state.menu_selecionado == "Configurações":
        st.header("🛠️ CONFIGURAÇÕES")
        st.info("Configurações de Lojas e Fornecedores mantidas.")
