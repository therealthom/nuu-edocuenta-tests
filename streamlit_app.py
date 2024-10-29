import streamlit as st
import os
from procesador_pdf import procesar_archivo
import base64
import json
from datetime import datetime
import pdfplumber
import time
import pandas as pd
import glob

st.set_page_config(page_title="Procesador de Estados de Cuenta", layout="wide")

def get_download_link(file_path, link_text):
    with open(file_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{os.path.basename(file_path)}">{link_text}</a>'

def get_output_filename(original_filename: str, extension: str) -> str:
    """Genera un nombre de archivo de salida basado en el nombre original"""
    # Quitar la extensión .pdf del nombre original
    base_name = os.path.splitext(original_filename)[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{base_name}_{timestamp}.{extension}"

def main():
    st.title("Procesador de Estados de Cuenta PDF")
    
    if 'procesando' not in st.session_state:
        st.session_state.procesando = False
    if 'resultados' not in st.session_state:
        st.session_state.resultados = []
    
    uploaded_files = st.file_uploader(
        "Selecciona uno o varios archivos PDF",
        type=['pdf'],
        accept_multiple_files=True,
        disabled=st.session_state.procesando
    )
    
    if uploaded_files:
        st.write("### Archivos cargados:")
        for file in uploaded_files:
            with pdfplumber.open(file) as pdf:
                st.write(f"📄 {file.name} - {len(pdf.pages)} páginas - {file.size/1024/1024:.2f} MB")
        
        if st.button("Procesar archivos", disabled=st.session_state.procesando):
            st.session_state.procesando = True
            st.session_state.resultados = []
            os.makedirs('temp', exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            json_path = f"transacciones_{timestamp}.json"
            st.session_state.json_path = json_path  # Guardamos la ruta del JSON
            
            for uploaded_file in uploaded_files:
                st.write(f"⏳ Procesando: {uploaded_file.name}")
                temp_pdf_path = f"temp/{uploaded_file.name}"
                
                try:
                    with open(temp_pdf_path, "wb") as f:
                        f.write(uploaded_file.getvalue())
                    
                    resultado = procesar_archivo(temp_pdf_path)
                    
                    if resultado:
                        st.session_state.resultados.append({
                            'nombre': uploaded_file.name,
                            'estado': 'success'
                        })
                    
                except Exception as e:
                    st.session_state.resultados.append({
                        'nombre': uploaded_file.name,
                        'error': str(e),
                        'estado': 'error'
                    })
                
                finally:
                    if os.path.exists(temp_pdf_path):
                        os.remove(temp_pdf_path)
            
            st.session_state.procesando = False
            st.rerun()

    # Mostrar resultados guardados
    if st.session_state.resultados:
        st.write("### Resultados del procesamiento:")
        for resultado in st.session_state.resultados:
            if resultado['estado'] == 'success':
                st.success(f"✅ {resultado['nombre']} procesado correctamente")
            else:
                st.error(f"❌ Error procesando {resultado['nombre']}: {resultado['error']}")
        
        # Mostrar enlace de descarga si existe el JSON
        if hasattr(st.session_state, 'json_path'):
            json_files = sorted(glob.glob("transacciones_*.json"))
            if json_files:  # Tomar el archivo JSON más reciente
                latest_json = json_files[-1]
                st.markdown(get_download_link(latest_json, "📥 Descargar JSON"), unsafe_allow_html=True)

    if st.session_state.procesando:
        st.warning('⏳ Procesamiento en curso. Por favor, espere...')

if __name__ == "__main__":
    main() 