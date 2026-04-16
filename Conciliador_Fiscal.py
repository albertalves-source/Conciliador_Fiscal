import streamlit as st
import pandas as pd
import re
import io
import os
import warnings
from datetime import datetime

# Tenta importar bibliotecas extras
try:
    import pdfplumber
except ImportError:
    st.error("Erro: A biblioteca 'pdfplumber' não foi encontrada. Adicione 'pdfplumber' ao seu requirements.txt.")

# Configurações de Página
st.set_page_config(page_title="Conciliador Multi-Marcas IA", layout="wide", page_icon="🎰")
warnings.filterwarnings("ignore")

# --- FUNÇÕES DE LIMPEZA E FORMATAÇÃO ---
def limpar_valor(v):
    if pd.isna(v): return 0.0
    v_str = str(v).replace('R$', '').replace('$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
    try:
        if v_str.count('.') > 1:
             parts = v_str.split('.')
             v_str = "".join(parts[:-1]) + "." + parts[-1]
        return float(v_str)
    except:
        try:
            clean = re.sub(r'[^0-9,.]', '', str(v))
            if ',' in clean and '.' in clean: clean = clean.replace('.', '').replace(',', '.')
            elif ',' in clean: clean = clean.replace(',', '.')
            return float(clean)
        except: return 0.0

def converter_data(data_obj):
    if pd.isna(data_obj): return None
    try:
        return pd.to_datetime(data_obj, dayfirst=True).date()
    except:
        match = re.search(r'(\d{2}/\d{2}/\d{4})', str(data_obj))
        if match: return datetime.strptime(match.group(1), '%d/%m/%Y').date()
        return None

def normalizar_texto(t):
    if not isinstance(t, str): return ""
    return " ".join(t.upper().split())

# --- EXTRAÇÃO DE DADOS ADAPTADA (ACEITA ARQUIVO OU CAMINHO) ---
def processar_arquivo_unico(file_source, marca_nome, is_path=False):
    """
    Processa um arquivo individual, seja ele um objeto do Streamlit ou um caminho de string.
    """
    dados = []
    file_name = file_source if is_path else file_source.name
    
    if file_name.lower().endswith(".pdf"):
        try:
            # pdfplumber aceita o caminho (string) ou o stream (BytesIO)
            with pdfplumber.open(file_source) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if not text: continue
                    for linha in text.split('\n'):
                        data_m = re.search(r'(\d{2}/\d{2}/\d{4})', linha)
                        valor_m = re.findall(r'\d{1,3}(?:\.\d{3})*,\d{2}', linha)
                        if data_m and valor_m:
                            val = limpar_valor(valor_m[-1])
                            if val > 0:
                                dados.append({
                                    'Data': converter_data(data_m.group(1)),
                                    'Valor': val,
                                    'Descricao': normalizar_texto(linha),
                                    'Marca': marca_nome,
                                    'Arquivo': os.path.basename(file_name) if is_path else file_name,
                                    'ID_Origem': f"{file_name}_{val}_{data_m.group(1)}"
                                })
        except Exception as e:
            pass # Erro na leitura do PDF
            
    elif file_name.lower().endswith((".xlsx", ".xls", ".csv")):
        try:
            if file_name.lower().endswith('.csv'):
                df = pd.read_csv(file_source, sep=None, engine='python')
            else:
                df = pd.read_excel(file_source)
                
            c_data = next((c for c in df.columns if 'data' in str(c).lower() or 'dt' in str(c).lower()), df.columns[0])
            c_valor = next((c for c in df.columns if 'valor' in str(c).lower() or 'vlr' in str(c).lower()), df.columns[-1])
            
            for _, row in df.iterrows():
                val = limpar_valor(row[c_valor])
                dt = converter_data(row[c_data])
                if val > 0 and dt:
                    dados.append({
                        'Data': dt, 'Valor': val, 'Descricao': f"PLANILHA {marca_nome}", 
                        'Marca': marca_nome, 'Arquivo': os.path.basename(file_name) if is_path else file_name,
                        'ID_Origem': f"{file_name}_{val}_{dt}"
                    })
        except: pass
    return dados

# --- INTERFACE ---
st.title("🏦 Conciliador de Marcas Bet")

# Sidebar - Configurações e Modo de Operação
with st.sidebar:
    st.header("⚙️ Configurações")
    modo_entrada = st.radio("Fonte das Notas:", ["Pastas Locais (Drive no PC)", "Upload Manual (Nuvem)"])
    
    st.divider()
    st.subheader("Parâmetros de Cruzamento")
    tolerancia_dias = st.slider("Tolerância de Datas (dias):", 0, 15, 2)
    tolerancia_valor = st.number_input("Tolerância de Valor (centavos):", 0.00, 5.00, 0.01)

# Lógica de Captura de Dados
df_notas = pd.DataFrame()
df_dom_raw = None

if modo_entrada == "Pastas Locais (Drive no PC)":
    st.info("💡 **Nota:** Este modo funciona melhor se você rodar o app no seu computador. No Streamlit Cloud, use o modo 'Upload Manual'.")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1: path_mma = st.text_input("Caminho Pasta MMABET:", placeholder="C:/Users/.../MMABET")
    with col_p2: path_papi = st.text_input("Caminho Pasta PAPIGAMES:", placeholder="C:/Users/.../PAPIGAMES")
    with col_p3: path_vip = st.text_input("Caminho Pasta BETVIP:", placeholder="C:/Users/.../BETVIP")
    
    # Processar pastas
    if st.button("🚀 Ler Pastas do Drive"):
        lista_notas = []
        for path, marca in [(path_mma, "MMABET"), (path_papi, "PAPIGAMES"), (path_vip, "BETVIP")]:
            if path and os.path.exists(path):
                files = [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
                for f_path in files:
                    lista_notas.extend(processar_arquivo_unico(f_path, marca, is_path=True))
            elif path:
                st.warning(f"Caminho não encontrado: {path}")
        df_notas = pd.DataFrame(lista_notas)
        if not df_notas.empty:
            st.success(f"Foram lidas {len(df_notas)} notas das pastas.")

else:
    # Modo Upload Manual
    st.subheader("📂 Upload das Notas")
    c1, c2, c3 = st.columns(3)
    with c1: files_mma = st.file_uploader("Notas MMABET", accept_multiple_files=True)
    with c2: files_papi = st.file_uploader("Notas PAPIGAMES", accept_multiple_files=True)
    with c3: files_vip = st.file_uploader("Notas BETVIP", accept_multiple_files=True)
    
    if st.button("🚀 Processar Uploads"):
        lista_notas = []
        if files_mma: 
            for f in files_mma: lista_notas.extend(processar_arquivo_unico(f, "MMABET"))
        if files_papi: 
            for f in files_papi: lista_notas.extend(processar_arquivo_unico(f, "PAPIGAMES"))
        if files_vip: 
            for f in files_vip: lista_notas.extend(processar_arquivo_unico(f, "BETVIP"))
        df_notas = pd.DataFrame(lista_notas)

# Upload do Domínio (Sempre manual ou pode ser via caminho também)
st.divider()
st.subheader("📊 Arquivo do Sistema Domínio")
dominio_file = st.file_uploader("Relatório Geral Domínio (Excel/CSV)", type=["xlsx", "csv"])

if dominio_file and not df_notas.empty:
    try:
        df_dom_raw = pd.read_excel(dominio_file) if dominio_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(dominio_file)
        
        # Identificação de colunas
        cols = df_dom_raw.columns
        c_dt = next((c for c in cols if 'data' in str(c).lower() or 'dt' in str(c).lower()), None)
        c_vlr = next((c for c in cols if 'valor' in str(c).lower() or 'vlr' in str(c).lower() or 'total' in str(c).lower()), None)
        c_hist = next((c for c in cols if 'hist' in str(c).lower() or 'compl' in str(c).lower() or 'nome' in str(c).lower()), None)
        
        transacoes_dominio = []
        for idx, row in df_dom_raw.iterrows():
            v = limpar_valor(row[c_vlr])
            d = converter_data(row[c_dt])
            if v > 0 and d:
                transacoes_dominio.append({
                    'id_dom': idx, 'Data': d, 'Valor': v, 
                    'Historico': normalizar_texto(row[c_hist]) if c_hist else "",
                    'Marca_Identificada': "NÃO IDENTIFICADO",
                    'Status': "❌ NÃO ENCONTRADO"
                })
        df_dominio = pd.DataFrame(transacoes_dominio)

        # CONCILIAÇÃO
        notas_usadas = set()
        for idx, row_dom in df_dominio.iterrows():
            mask = (df_notas['Valor'] >= row_dom['Valor'] - tolerancia_valor) & \
                   (df_notas['Valor'] <= row_dom['Valor'] + tolerancia_valor)
            
            possiveis = df_notas[mask].copy()
            if not possiveis.empty:
                possiveis['diff_dias'] = possiveis['Data'].apply(lambda x: abs((x - row_dom['Data']).days))
                possiveis = possiveis[possiveis['diff_dias'] <= tolerancia_dias]
                
                if not possiveis.empty:
                    possiveis = possiveis.sort_values('diff_dias')
                    match = None
                    for _, nota in possiveis.iterrows():
                        if nota['ID_Origem'] not in notas_usadas:
                            match = nota; break
                    
                    if match is not None:
                        df_dominio.at[idx, 'Marca_Identificada'] = match['Marca']
                        df_dominio.at[idx, 'Status'] = "✅ CONCILIADO"
                        df_dominio.at[idx, 'Nota_Origem'] = match['Arquivo']
                        notas_usadas.add(match['ID_Origem'])

        # Exibição
        st.success("Conciliação concluída!")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Domínio", len(df_dominio))
        m2.metric("Conciliados", len(df_dominio[df_dominio['Status'] == "✅ CONCILIADO"]))
        m3.metric("Sobras nas Pastas", len(df_notas) - len(notas_usadas))

        tab1, tab2 = st.tabs(["Relatório Geral", "Separação por Marca"])
        with tab1:
            st.dataframe(df_dominio, use_container_width=True)
        with tab2:
            m_sel = st.selectbox("Marca para Exportação:", ["MMABET", "PAPIGAMES", "BETVIP"])
            df_m = df_dominio[df_dominio['Marca_Identificada'] == m_sel]
            st.dataframe(df_m, use_container_width=True)
            
            # Exportar
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_m.to_excel(writer, index=False)
            st.download_button(f"📥 Baixar Excel {m_sel}", output.getvalue(), f"conciliado_{m_sel}.xlsx")

    except Exception as e:
        st.error(f"Erro ao processar: {e}")

elif not df_notas.empty:
    st.info("Aguardando arquivo do Sistema Domínio para cruzar os dados.")