import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="SISTEMA NIYATI", layout="wide", initial_sidebar_state="expanded")

# --- 2. GESTÃO DO BANCO DE DADOS ---
def conectar():
    if "database" in st.secrets:
        db_url = st.secrets["database"]["url"]
        # Esta linha abaixo é essencial para converter a URL do Supabase para o SQLAlchemy
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True)
    else:
        return create_engine('sqlite:///compras_niyati.db')

def inicializar_banco():
    engine = conectar()
    with engine.connect() as conn:
        id_tipo = "SERIAL PRIMARY KEY" if engine.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS lojas (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS fornecedores (id {id_tipo}, nome TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS pedidos (id {id_tipo}, data TEXT, loja TEXT, fornecedor TEXT, itens TEXT, status TEXT)'))
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS produtos (id {id_tipo}, nome TEXT)'))
        
        res = conn.execute(text('SELECT COUNT(*) FROM lojas')).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO lojas (nome) VALUES ('Junqueirópolis'), ('Tupi Paulista'), ('Pres. Venceslau')"))
            conn.execute(text("INSERT INTO fornecedores (nome) VALUES ('Max Titanium'), ('Unilife'), ('Herbamed'), ('Flora Caps')"))
        conn.commit()

inicializar_banco()

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

def gerar_excel_niyati(dados_df):
    rows = []
    for _, row in dados_df.iterrows():
        for item in str(row['itens']).split(", "):
            try:
                q_v, n_v = item.split("x ", 1)
                rows.append({"ID Pedido": row['id'], "Data": row['data'], "Loja": row['loja'], "Fornecedor": row['fornecedor'], "Quantidade": q_v, "Produto": n_v})
            except: rows.append({"ID Pedido": row['id'], "Data": row['data'], "Loja": row['loja'], "Fornecedor": row['fornecedor'], "Quantidade": "1", "Produto": item})
    df_excel = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df_excel.to_excel(writer, index=False)
    return output.getvalue()

# --- 4. NAVEGAÇÃO ---
if 'menu_selecionado' not in st.session_state: st.session_state.menu_selecionado = "Lojas"
def navegar(destino): st.session_state.menu_selecionado = destino

st.sidebar.markdown("<h2 style='text-align: center; color: #007bff;'>SISTEMA NIYATI</h2>", unsafe_allow_html=True)
st.sidebar.divider()
st.sidebar.button("🛒 LISTA DE PEDIDOS", on_click=navegar, args=("Lojas",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Lojas" else "secondary")
st.sidebar.button("⚙️ GERENCIAMENTO (ADM)", on_click=navegar, args=("ADM",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "ADM" else "secondary")
st.sidebar.button("📝 GERAR PEDIDOS (AVULSO)", on_click=navegar, args=("Gerar",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Gerar" else "secondary")
st.sidebar.button("🍎 PRODUTOS", on_click=navegar, args=("Produtos",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Produtos" else "secondary")
st.sidebar.button("🛠️ CONFIGURAÇÕES", on_click=navegar, args=("Config",), use_container_width=True, type="primary" if st.session_state.menu_selecionado == "Config" else "secondary")

engine = conectar()

# --- 5. TELA: LOJAS ---
if st.session_state.menu_selecionado == "Lojas":
    st.header("🛒 LISTA DE PEDIDOS DE COMPRA")
    with engine.connect() as conn:
        lojas_db = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
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
                        if st.button(f"✏️ Editar #{row['id']}", key=f"re_{row['id']}"):
                            k_re = f"car_{nome_loja}_{row['fornecedor']}"
                            if k_re not in st.session_state: st.session_state[k_re] = []
                            for i_s in row['itens'].split(", "):
                                try: qv, nv = i_s.split("x ", 1); st.session_state[k_re].append({"Item": nv, "Qtd": int(qv)})
                                except: pass
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": row['id']}); conn.commit()
                            st.rerun()

# --- 6. TELA: ADM ---
elif st.session_state.menu_selecionado == "ADM":
    st.header("⚙️ GERENCIAMENTO DE PEDIDOS (ADM)")
    df_adm = pd.read_sql(text("SELECT * FROM pedidos ORDER BY id DESC"), engine)
    if not df_adm.empty:
        if 'ids_sel' not in st.session_state: st.session_state.ids_sel = []
        if st.session_state.ids_sel:
            df_sel = df_adm[df_adm['id'].isin(st.session_state.ids_sel)]
            c1, c2, c3 = st.columns(3)
            c1.download_button("📄 PDF", data=gerar_pdf_niyati(df_sel), file_name="pedidos.pdf", use_container_width=True)
            c2.download_button("📊 Excel", data=gerar_excel_niyati(df_sel), file_name="pedidos.xlsx", use_container_width=True)
            if c3.button("Limpar Seleção", use_container_width=True): st.session_state.ids_sel = []; st.rerun()
        
        with engine.connect() as conn:
            lojas_adm = [r[0] for r in conn.execute(text('SELECT nome FROM lojas')).fetchall()]
        tabs_adm = st.tabs(lojas_adm)
        for idx_a, nome_a in enumerate(lojas_adm):
            with tabs_adm[idx_a]:
                df_l = df_adm[df_adm['loja'] == nome_a]
                for _, r_adm in df_l.iterrows():
                    c_ch, c_ex = st.columns([0.05, 0.95])
                    chk = c_ch.checkbox("", key=f"chk_adm_{r_adm['id']}", value=(r_adm['id'] in st.session_state.ids_sel))
                    if chk and r_adm['id'] not in st.session_state.ids_sel: st.session_state.ids_sel.append(r_adm['id']); st.rerun()
                    elif not chk and r_adm['id'] in st.session_state.ids_sel: st.session_state.ids_sel.remove(r_adm['id']); st.rerun()
                    
                    with c_ex.expander(f"📦 Pedido #{r_adm['id']} | {r_adm['fornecedor']} | {r_adm['data']}"):
                        lista_itens = r_adm['itens'].split(", "); itens_atuais = []
                        for idx_it, item_str in enumerate(lista_itens):
                            try:
                                q_o, n_o = item_str.split("x ", 1)
                                col_nome, col_qtd, col_x = st.columns([3, 1, 0.5])
                                ed_n = col_nome.text_input("Produto", n_o, key=f"n_{r_adm['id']}_{idx_it}", label_visibility="collapsed")
                                ed_q = col_qtd.number_input("Qtd", value=int(q_o), key=f"q_{r_adm['id']}_{idx_it}", label_visibility="collapsed")
                                itens_atuais.append(f"{ed_q}x {ed_n}")
                                if col_x.button("❌", key=f"x_it_{r_adm['id']}_{idx_it}"):
                                    itens_atuais.pop()
                                    txt_novo = ", ".join(itens_atuais + lista_itens[idx_it+1:])
                                    with engine.connect() as conn:
                                        conn.execute(text("UPDATE pedidos SET itens = :i WHERE id = :id"), {"i": txt_novo, "id": r_adm['id']}); conn.commit(); st.rerun()
                            except: pass
                        
                        st.write("---")
                        c_an, c_aq, c_ab = st.columns([3, 1, 1])
                        n_it = c_an.text_input("Novo Item", key=f"an_{r_adm['id']}")
                        q_it = c_aq.number_input("Qtd", min_value=1, key=f"aq_{r_adm['id']}")
                        if c_ab.button("➕ Add", key=f"ab_{r_adm['id']}"):
                            if n_it:
                                itens_atuais.append(f"{q_it}x {n_it}")
                                txt_novo = ", ".join(itens_atuais)
                                with engine.connect() as conn:
                                    conn.execute(text("UPDATE pedidos SET itens = :i WHERE id = :id"), {"i": txt_novo, "id": r_adm['id']}); conn.commit(); st.rerun()

                        st.divider()
                        c_sv, c_dl = st.columns(2)
                        if c_sv.button("💾 Salvar Alterações", key=f"sv_{r_adm['id']}", type="primary"):
                            txt_novo = ", ".join(itens_atuais)
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE pedidos SET itens = :i WHERE id = :id"), {"i": txt_novo, "id": r_adm['id']}); conn.commit(); st.rerun()
                        if c_dl.button("Deletar Pedido", key=f"dl_{r_adm['id']}"):
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM pedidos WHERE id=:id"), {"id": r_adm['id']}); conn.commit(); st.rerun()
    else: st.info("Vazio.")

# --- OUTRAS TELAS ---
elif st.session_state.menu_selecionado == "Gerar":
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
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO produtos (nome) VALUES (:n)"), {"n": np}); conn.commit(); st.rerun()
    st.dataframe(pd.read_sql(text("SELECT * FROM produtos ORDER BY nome"), engine), use_container_width=True)

elif st.session_state.menu_selecionado == "Config":
    st.header("🛠️ CONFIGURAÇÕES")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Lojas")
        nl = st.text_input("Nova Loja")
        if st.button("Add Loja") and nl:
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO lojas (nome) VALUES (:n)"), {"n": nl}); conn.commit(); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM lojas"), engine).iterrows():
            col1, col2 = st.columns([3, 1]); col1.write(r['nome'])
            if col2.button("X", key=f"l_{r['id']}"):
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM lojas WHERE id=:id"), {"id": r['id']}); conn.commit(); st.rerun()
    with c2:
        st.subheader("Fornecedores")
        nf = st.text_input("Novo Forn")
        if st.button("Add Forn") and nf:
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO fornecedores (nome) VALUES (:n)"), {"n": nf}); conn.commit(); st.rerun()
        for _, r in pd.read_sql(text("SELECT * FROM fornecedores"), engine).iterrows():
            col1, col2 = st.columns([3, 1]); col1.write(r['nome'])
            if col2.button("X", key=f"f_{r['id']}"):
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM fornecedores WHERE id=:id"), {"id": r['id']}); conn.commit(); st.rerun()

