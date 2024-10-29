# Procesador de Estados de Cuenta PDF

## Descripción
Aplicación web desarrollada con Streamlit para procesar estados de cuenta en formato PDF. La aplicación extrae información de transacciones bancarias, incluyendo fechas, conceptos, retiros, depósitos y saldos, generando un archivo JSON estructurado con los datos procesados.

## Requisitos Previos
- Python 3.8+
- pip (gestor de paquetes de Python)

## Instalación
1. Clonar el repositorio
2. Crear un entorno virtual:
   ```
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```
3. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```

## Uso
1. Iniciar la aplicación:
   ```
   streamlit run streamlit_app.py
   ```
2. Abrir el navegador en la dirección indicada (típicamente http://localhost:8501)
3. Subir uno o varios archivos PDF de estados de cuenta
4. Hacer clic en "Procesar archivos"
5. Descargar los resultados en formato JSON y revisar los logs generados

## Estructura del Proyecto
proyecto/
│   README.md
│   requirements.txt
│   procesador_pdf.py
│   streamlit_app.py
│   .gitignore
│
└───resources/
    └───uploads/
        └───[nombre_archivo]/
            ├───temp/
            ├───logs/
            └───output/

## Características
- Procesamiento múltiple de archivos PDF
- Extracción automática de transacciones bancarias
- Generación de archivos JSON estructurados
- Sistema de logging detallado
- Interfaz web intuitiva
- Manejo de errores robusto

## Desarrollo
El proyecto utiliza las siguientes bibliotecas principales:
- Streamlit para la interfaz web
- pdfplumber para la extracción de texto de PDFs
- pandas para el manejo de datos

## Licencia
Este proyecto está bajo la Licencia MIT. 