import pdfplumber
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import logging
from decimal import Decimal
import os
from datetime import datetime

# Configuración del logging a archivo
def setup_logger(log_path: str):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Handler para archivo
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger

@dataclass
class Transaccion:
    fecha: str
    concepto: str
    retiro: Optional[str]
    deposito: Optional[str]
    saldo: Optional[str]
    pagina: int  # Nuevo campo para el número de página

class ReglasNegocio:
    """Clase que contiene todas las reglas de negocio para procesar transacciones"""
    
    @staticmethod
    def es_pago_recibido(concepto: str) -> bool:
        """Determina si una transacción es un pago recibido"""
        return 'PAGO RECIBIDO' in concepto.upper()
    
    @staticmethod
    def procesar_montos(montos: List[str], concepto: str) -> tuple:
        """
        Aplica las reglas de negocio para determinar retiro, depósito y saldo:
        - Si hay 2 montos: el segundo es saldo y el primero es depósito o retiro según el concepto
        - Si hay 1 monto: es depósito si el concepto indica pago recibido, sino es retiro
        - Los montos se asignan como string con formato decimal (ej: "1234.56")
        - Si un monto no aplica se asigna como None
        """
        retiro = deposito = saldo = None
        logger.info(f"Procesando montos: {montos}")
        logger.info(f"Concepto: {concepto}")
        
        if len(montos) == 2:
            # El último monto siempre es saldo
            saldo = montos[1]
            logger.info(f"Segundo monto asignado como saldo: {saldo}")
            
            # El primer monto es depósito o retiro según el concepto
            if ReglasNegocio.es_pago_recibido(concepto):
                deposito = montos[0]
                logger.info(f"Primer monto asignado como depósito: {deposito}")
            else:
                retiro = montos[0]
                logger.info(f"Primer monto asignado como retiro: {retiro}")
        
        elif len(montos) == 1:
            # Un solo monto es depósito o retiro según el concepto
            if ReglasNegocio.es_pago_recibido(concepto):
                deposito = montos[0]
                logger.info(f"Monto único asignado como depósito: {deposito}")
            else:
                retiro = montos[0]
                logger.info(f"Monto único asignado como retiro: {retiro}")
        
        return retiro, deposito, saldo

class ProcesadorEstadoCuenta:
    def __init__(self):
        self.patron_fecha = re.compile(r'^\d{2}\s+[A-Z]{3}\b')
        self.patron_monto = re.compile(r'[\d,]+\.\d{2}')
        self.patron_identificador_pagina = re.compile(r'^\d+\.([A-Z]|[0-9])+\.([A-Z]|[0-9])+\.\d+\.\d+$')
        self.patron_encabezado_columnas = re.compile(r'^FECHA\s+CONCEPTO\s+RETIROS\s+DEPOSITOS\s+SALDO$')
        self.reglas = ReglasNegocio()
        self.ignorar_lineas = False
    
    def _es_identificador_pagina(self, linea: str) -> bool:
        """Verifica si una línea es un identificador de página"""
        return bool(self.patron_identificador_pagina.match(linea.strip()))
    
    def _limpiar_monto(self, monto: str) -> Optional[str]:
        """Limpia y formatea un monto"""
        if not monto:
            return None
        monto = re.sub(r'[^\d,.]', '', monto)
        try:
            return str(Decimal(monto.replace(',', '')))
        except:
            return None
    
    def _es_fecha(self, texto: str) -> bool:
        """Verifica si un texto comienza con una fecha (DD MMM)"""
        texto = texto.strip()  # Limpiamos espacios al inicio y final
        return bool(self.patron_fecha.match(texto))
    
    def _procesar_linea_montos(self, linea: str, concepto: str) -> tuple:
        """Procesa una línea que contiene montos"""
        montos = [self._limpiar_monto(m) for m in self.patron_monto.findall(linea)]
        return ReglasNegocio.procesar_montos(montos, concepto)
    
    def _calcular_estadisticas(self, transacciones: List[Transaccion]) -> Dict:
        """Calcula estadísticas de las transacciones procesadas"""
        total_retiros = sum(1 for t in transacciones if t.retiro is not None)
        total_depositos = sum(1 for t in transacciones if t.deposito is not None)
        
        suma_retiros = sum(float(t.retiro) for t in transacciones if t.retiro is not None)
        suma_depositos = sum(float(t.deposito) for t in transacciones if t.deposito is not None)
        
        return {
            "numero_transacciones": len(transacciones),
            "cantidad_retiros": total_retiros,
            "cantidad_depositos": total_depositos,
            "suma_retiros": round(suma_retiros, 2),
            "suma_depositos": round(suma_depositos, 2),
            "balance_total": round(suma_depositos - suma_retiros, 2)
        }

    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        """Procesa el PDF y extrae las transacciones"""
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        
        logger.info(f"Iniciando procesamiento del PDF: {ruta_pdf}")
        
        with pdfplumber.open(ruta_pdf) as pdf:
            logger.info(f"PDF abierto. Total de páginas: {len(pdf.pages)}")
            
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto = pagina.extract_text(layout=True)
                logger.info(f"\nProcesando página {num_pagina}")
                
                for linea in texto.split('\n'):
                    linea = linea.strip()
                    
                    # Detectar final de la tabla de movimientos
                    if 'SALDO MINIMO REQUERIDO' in linea:
                        if transaccion_actual:
                            logger.info("Última transacción completada:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        estadisticas = self._calcular_estadisticas(transacciones)
                        logger.info("\nEstadísticas del estado de cuenta:")
                        logger.info(json.dumps(estadisticas, indent=2, ensure_ascii=False))
                        
                        return {
                            "estado_cuenta": {
                                "movimientos": [asdict(t) for t in transacciones],
                                "estadisticas": estadisticas
                            }
                        }
                    
                    # Si encontramos un identificador de página, activamos el flag para ignorar líneas
                    if self._es_identificador_pagina(linea):
                        self.ignorar_lineas = True
                        logger.info(f"Saltando identificador de página: {linea}")
                        continue
                    
                    # Si estamos ignorando líneas, buscamos DETALLE DE OPERACIONES
                    if self.ignorar_lineas:
                        if "DETALLE DE OPERACIONES" in linea:
                            # Encontramos la sección pero seguimos ignorando hasta encontrar los encabezados
                            continue
                        elif self.patron_encabezado_columnas.match(linea):
                            # Encontramos los encabezados, podemos volver a procesar
                            self.ignorar_lineas = False
                        continue
                    
                    # Procesamiento normal de las transacciones
                    if not linea:
                        continue
                    
                    if self._es_fecha(linea):
                        logger.info(f"\nNueva fecha encontrada: {linea[:7]}")
                        
                        if transaccion_actual:
                            logger.info("Transacción completada:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        # Creamos nueva transacción
                        linea_limpia = linea.strip()
                        fecha = linea_limpia[:7].strip()
                        concepto = linea_limpia[7:].strip()
                        
                        transaccion_actual = Transaccion(
                            fecha=fecha.replace("  ", " "),
                            concepto=concepto,
                            retiro=None,
                            deposito=None,
                            saldo=None,
                            pagina=num_pagina
                        )
                        lineas_concepto = [concepto]
                        
                    elif transaccion_actual:
                        if self.patron_monto.search(linea):
                            logger.info(f"Procesando línea con montos: {linea}")
                            retiro, deposito, saldo = self._procesar_linea_montos(
                                linea, 
                                transaccion_actual.concepto
                            )
                            
                            if retiro: transaccion_actual.retiro = retiro
                            if deposito: transaccion_actual.deposito = deposito
                            if saldo: transaccion_actual.saldo = saldo
                        else:
                            lineas_concepto.append(linea.strip())
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()
        
        # Guardar última transacción
        if transaccion_actual:
            logger.info("\nÚltima transacción:")
            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
            transacciones.append(transaccion_actual)
        
        logger.info(f"\nProcesamiento completado. Total de transacciones: {len(transacciones)}")
        return {
            "estado_cuenta": {
                "movimientos": [asdict(t) for t in transacciones]
            }
        }

def get_resource_paths(pdf_filename: str, timestamp: str) -> Dict[str, str]:
    """Genera las rutas de recursos para un archivo PDF"""
    base_dir = f"resources/uploads/{os.path.splitext(pdf_filename)[0]}"
    
    paths = {
        'base': base_dir,
        'temp': f"{base_dir}/temp",
        'logs': f"{base_dir}/logs",
        'output': f"{base_dir}/output",
        'pdf': f"{base_dir}/temp/{pdf_filename}",
        'log': f"{base_dir}/logs/procesamiento_{timestamp}.log",
        'json': f"{base_dir}/output/transacciones_{timestamp}.json"
    }
    
    # Crear directorios
    for dir_path in [paths['temp'], paths['logs'], paths['output']]:
        os.makedirs(dir_path, exist_ok=True)
        
    return paths

def procesar_archivo(ruta_pdf: str) -> Dict:
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = os.path.basename(ruta_pdf)
        paths = get_resource_paths(pdf_filename, timestamp)
        
        # Configurar logger
        global logger
        logger = setup_logger(paths['log'])
        logger.info(f"Iniciando nuevo procesamiento con timestamp: {timestamp}")
        
        procesador = ProcesadorEstadoCuenta()
        resultado = procesador.procesar_pdf(ruta_pdf)
        
        # Guardar resultado en JSON
        with open(paths['json'], 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Archivo JSON generado: {paths['json']}")
        return resultado, paths
        
    except Exception as e:
        logger.error(f"Error durante el procesamiento: {str(e)}")
        raise

if __name__ == "__main__":
    ruta_pdf = "/Users/tom/70061797449-12.pdf"
    resultado, paths = procesar_archivo(ruta_pdf)