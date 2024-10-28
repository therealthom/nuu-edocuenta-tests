import pdfplumber
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import logging
from decimal import Decimal
import os

# Configuración del logging a archivo
def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Crear directorio logs si no existe
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Handler para archivo
    fh = logging.FileHandler('logs/procesamiento.log')
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger

logger = setup_logger()

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
        Aplica las reglas de negocio para determinar retiro, depósito y saldo
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
        return bool(self.patron_fecha.match(str(texto).strip()))
    
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
                    if not linea.strip():
                        continue
                    
                    # Control de sección
                    if 'DETALLE DE OPERACIONES' in linea:
                        en_detalle_operaciones = True
                        logger.info(f">>> Encontrada sección DETALLE DE OPERACIONES en página {num_pagina}")
                        continue
                    
                    if not en_detalle_operaciones:
                        continue
                    
                    # Procesar línea
                    if self._es_fecha(linea):
                        logger.info(f"\nNueva fecha encontrada: {linea[:6]} en página {num_pagina}")
                        
                        # Guardar transacción anterior
                        if transaccion_actual:
                            logger.info("Guardando transacción anterior:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        # Iniciar nueva transacción
                        transaccion_actual = Transaccion(
                            fecha=linea[:6],
                            concepto=linea[6:].strip(),
                            retiro=None,
                            deposito=None,
                            saldo=None,
                            pagina=num_pagina  # Agregamos el número de página
                        )
                        logger.info("Nueva transacción creada:")
                        logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                        lineas_concepto = [linea[6:].strip()]
                    
                    elif transaccion_actual:
                        if self.patron_monto.search(linea):
                            logger.info(f"Procesando línea con montos: {linea}")
                            # Procesar línea con montos
                            retiro, deposito, saldo = self._procesar_linea_montos(
                                linea, 
                                transaccion_actual.concepto
                            )
                            
                            if retiro: 
                                transaccion_actual.retiro = retiro
                                logger.info(f"Retiro asignado: {retiro}")
                            if deposito: 
                                transaccion_actual.deposito = deposito
                                logger.info(f"Depósito asignado: {deposito}")
                            if saldo: 
                                transaccion_actual.saldo = saldo
                                logger.info(f"Saldo asignado: {saldo}")
                            
                            logger.info("Transacción actualizada:")
                            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                        else:
                            # Agregar línea al concepto
                            lineas_concepto.append(linea.strip())
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()
                            logger.info(f"Concepto actualizado: {transaccion_actual.concepto}")
        
        # Guardar última transacción
        if transaccion_actual:
            logger.info("\nGuardando última transacción:")
            logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
            transacciones.append(transaccion_actual)
        
        logger.info(f"\nProcesamiento completado. Total de transacciones: {len(transacciones)}")
        return {
            "estado_cuenta": {
                "movimientos": [asdict(t) for t in transacciones]
            }
        }

def procesar_archivo(ruta_pdf: str, ruta_salida: str = "transacciones.json") -> Dict:
    try:
        # Limpiar archivo de log
        if os.path.exists('logs/procesamiento.log'):
            open('logs/procesamiento.log', 'w').close()
            logger.info("Archivo de log limpiado")
        
        # Limpiar archivo de salida JSON
        if os.path.exists(ruta_salida):
            open(ruta_salida, 'w').close()
            logger.info(f"Archivo {ruta_salida} limpiado")
        
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
