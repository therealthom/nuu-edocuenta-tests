import streamlit as st
import pandas as pd
import tempfile
import os
import logging
from typing import Dict
from datetime import datetime
import json
from procesadores.factory import ProcesadorFactory, TipoBanco

def setup_logger(log_path: str) -> logging.Logger:
    """Configura y retorna un logger"""
    # Remover handlers existentes para evitar duplicación
    logger = logging.getLogger('ProcesadorEstadoCuenta')
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(logging.INFO)
    
    # Solo configurar FileHandler (sin handler de consola)
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # En lugar de asignar flush = True, llamamos al método flush() después de cada write
    original_emit = file_handler.emit
    def emit_with_flush(record):
        original_emit(record)
        file_handler.flush()
    file_handler.emit = emit_with_flush
    
    logger.addHandler(file_handler)
    
    return logger

def main():
    st.title("Procesador de Estados de Cuenta")
    
    # Inicializar session_state si no existe
    if 'resultado' not in st.session_state:
        st.session_state.resultado = None
        st.session_state.df = None
        st.session_state.df_stats = None
        st.session_state.log_path = None
        st.session_state.timestamp = None
    
    # Selector de banco
    banco_seleccionado = st.selectbox(
        "Selecciona el banco",
        [banco.value for banco in TipoBanco]
    )
    
    uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf")
    
    if uploaded_file:
        # Crear directorios base si no existen
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = uploaded_file.name
        file_base = os.path.splitext(filename)[0]
        
        base_dir = "resources/uploads"
        file_dir = os.path.join(base_dir, file_base)
        temp_dir = os.path.join(file_dir, "temp")
        logs_dir = os.path.join(file_dir, "logs")
        output_dir = os.path.join(file_dir, "output")
        
        for dir_path in [temp_dir, logs_dir, output_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        # Agregar botón de procesar
        if st.button("Procesar Estado de Cuenta"):
            try:
                # Guardar timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                st.session_state.timestamp = timestamp
                
                # Configurar logger y guardar path
                log_path = os.path.join(logs_dir, f"procesamiento_{timestamp}.log")
                st.session_state.log_path = log_path
                logger = setup_logger(log_path)
                logger.info(f"Iniciando procesamiento del archivo: {filename}")
                
                # Guardar archivo temporal
                temp_path = os.path.join(temp_dir, f"temp_{timestamp}.pdf")
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                # Procesar archivo
                with st.spinner('Procesando archivo...'):
                    procesador = ProcesadorFactory.crear_procesador(
                        TipoBanco(banco_seleccionado),
                        logger
                    )
                    resultado = procesador.procesar_pdf(temp_path)
                
                # Guardar resultado en JSON
                json_path = os.path.join(output_dir, f"transacciones_{timestamp}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(resultado, f, ensure_ascii=False, indent=2)
                
                # Guardar en session_state
                st.session_state.resultado = resultado
                st.session_state.df = pd.DataFrame(resultado["estado_cuenta"]["movimientos"])
                st.session_state.df_stats = pd.DataFrame([resultado["estado_cuenta"]["estadisticas"]])
                
            except Exception as e:
                error_msg = f"Error al procesar el archivo: {str(e)}"
                logger.error(error_msg, exc_info=True)
                st.error(error_msg)
            finally:
                # Limpiar archivo temporal
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                logger.info("Procesamiento finalizado")
                # Cerrar handlers del logger
                for handler in logger.handlers[:]:
                    handler.flush()
                    handler.close()
                    logger.removeHandler(handler)

    # Mostrar resultados si existen
    if st.session_state.resultado is not None:
        st.success("Procesamiento completado")
        st.write("Estadísticas:")
        st.dataframe(st.session_state.df_stats)
        
        st.write("Transacciones:")
        st.dataframe(st.session_state.df)
        
        # Botones de descarga
        st.write("Descargar resultados:")
        col1, col2, col3 = st.columns(3)
        
        # JSON
        json_str = json.dumps(st.session_state.resultado, ensure_ascii=False, indent=2)
        col1.download_button(
            label="Descargar JSON",
            data=json_str,
            file_name=f"transacciones_{st.session_state.timestamp}.json",
            mime="application/json",
            key="json_download"
        )
        
        # LOG
        if st.session_state.log_path and os.path.exists(st.session_state.log_path):
            with open(st.session_state.log_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            col2.download_button(
                label="Descargar LOG",
                data=log_content,
                file_name=f"procesamiento_{st.session_state.timestamp}.log",
                mime="text/plain",
                key="log_download"
            )
        
        # CSV
        csv = st.session_state.df.to_csv(index=False).encode('utf-8')
        col3.download_button(
            label="Descargar CSV",
            data=csv,
            file_name=f"transacciones_{st.session_state.timestamp}.csv",
            mime="text/csv",
            key="csv_download"
        )

if __name__ == "__main__":
    main()