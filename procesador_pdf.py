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
def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Generar nombre único para el archivo de log
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'logs/procesamiento_{timestamp}.log'
    
    # Crear directorio logs si no existe
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Handler para archivo
    fh = logging.FileHandler(log_filename)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger, log_filename

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
        self.reglas = ReglasNegocio()
    
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
    
    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        """Procesa el PDF y extrae las transacciones"""
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        en_detalle_operaciones = False
        
        logger.info(f"Iniciando procesamiento del PDF: {ruta_pdf}")
        
        with pdfplumber.open(ruta_pdf) as pdf:
            logger.info(f"PDF abierto. Total de páginas: {len(pdf.pages)}")
            
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto = pagina.extract_text(layout=True)
                logger.info(f"\nProcesando página {num_pagina}")
                
                for linea in texto.split('\n'):
                    linea = linea.strip()  # Limpiamos espacios al inicio y final
                    if not linea:
                        continue
                    
                    # Control de sección
                    if 'DETALLE DE OPERACIONES' in linea:
                        en_detalle_operaciones = True
                        logger.info(f">>> Encontrada sección DETALLE DE OPERACIONES en página {num_pagina}")
                        continue
                    
                    if not en_detalle_operaciones:
                        continue
                    
                    if self._es_fecha(linea):
                        logger.info(f"\nNueva fecha encontrada: {linea[:7]}")  # Cambiado de 6 a 7 para incluir "DD MMM"
                        
                        if transaccion_actual:
                            logger.info("Transacción completada:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        # Limpiamos la línea y la fecha
                        linea_limpia = linea.strip()
                        fecha = linea_limpia[:7].strip()  # DD MMM y quitamos espacios extra
                        concepto = linea_limpia[7:].strip()
                        
                        transaccion_actual = Transaccion(
                            fecha=fecha.replace("  ", " "),  # Reemplazamos espacios múltiples por uno solo
                            concepto=concepto,
                            retiro=None,
                            deposito=None,
                            saldo=None,
                            pagina=num_pagina
                        )
                        lineas_concepto = [concepto]
                        logger.info(f"Nueva transacción creada con fecha: [{fecha.replace('  ', ' ')}]")
                    
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
                            
                            # Mostramos la transacción después de procesar montos
                            logger.info("Transacción actualizada:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                        else:
                            # Solo concatenamos el concepto sin logging
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

def procesar_archivo(ruta_pdf: str, ruta_salida: str = None) -> Dict:
    try:
        # Generar nombres únicos para los archivos
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Configurar logger con nuevo nombre de archivo
        global logger
        logger, log_filename = setup_logger()
        logger.info(f"Iniciando nuevo procesamiento con timestamp: {timestamp}")
        
        # Generar nombre de archivo de salida si no se especifica
        if ruta_salida is None:
            ruta_salida = f"transacciones_{timestamp}.json"
        
        procesador = ProcesadorEstadoCuenta()
        resultado = procesador.procesar_pdf(ruta_pdf)
        
        # Guardar resultado en JSON
        with open(ruta_salida, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Archivo JSON generado: {ruta_salida}")
        return resultado
        
    except Exception as e:
        logger.error(f"Error durante el procesamiento: {str(e)}")
        raise

if __name__ == "__main__":
    ruta_pdf = "/Users/tom/70061797449-12.pdf"
    resultado = procesar_archivo(ruta_pdf)
    ruta_pdf = "/Users/tom/70061797449-07.pdf"
    resultado = procesar_archivo(ruta_pdf)
    ruta_pdf = "/Users/tom/70061797449-03.pdf"
    resultado = procesar_archivo(ruta_pdf)
    ruta_pdf = "/Users/tom/70061797449-05.pdf"
    resultado = procesar_archivo(ruta_pdf)
    ruta_pdf = "/Users/tom/70061797449-06.pdf"
    resultado = procesar_archivo(ruta_pdf)