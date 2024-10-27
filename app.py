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

class ProcesadorEstadoCuenta:
    def __init__(self):
        self.patron_fecha = re.compile(r'^\d{2}\s+[A-Z]{3}\b')
        self.patron_monto = re.compile(r'[\d,]+\.\d{2}')
        
    def _es_fecha(self, texto: str) -> bool:
        return bool(self.patron_fecha.match(str(texto).strip()))

    def _limpiar_monto(self, monto: str) -> Optional[str]:
        if not monto:
            return None
        monto = re.sub(r'[^\d,.]', '', monto)
        try:
            return str(Decimal(monto.replace(',', '')))
        except:
            return None

    def _determinar_tipo_monto(self, linea: str, monto: str) -> tuple:
        """
        Determina si un monto es retiro, depósito o saldo basado en su posición en la línea
        """
        texto_antes_monto = linea[:linea.find(monto)]
        palabras = texto_antes_monto.split()
        
        # Contar tabulaciones o espacios significativos
        tabs = texto_antes_monto.count('\t')
        espacios = len(texto_antes_monto) - len(texto_antes_monto.lstrip())
        
        logger.info(f"Analizando monto: {monto}")
        logger.info(f"Texto antes del monto: '{texto_antes_monto}'")
        logger.info(f"Tabs: {tabs}, Espacios: {espacios}")
        
        # Si el monto está en la última columna, es saldo
        if linea.strip().endswith(monto):
            return (None, None, monto)
        
        # Si hay palabras clave antes del monto
        texto_lower = texto_antes_monto.lower()
        if 'retiro' in texto_lower or 'cargo' in texto_lower:
            return (monto, None, None)
        elif 'deposito' in texto_lower or 'abono' in texto_lower:
            return (None, monto, None)
        
        # Por posición en la línea
        if espacios < 40:  # Ajusta estos valores según el formato de tu PDF
            return (monto, None, None)  # Retiro
        elif espacios < 60:
            return (None, monto, None)  # Depósito
        else:
            return (None, None, monto)  # Saldo

    def _procesar_montos_en_linea(self, linea: str) -> tuple:
        """
        Procesa todos los montos en una línea y los asigna según su posición
        Retorna (retiro, deposito, saldo)
        """
        retiro = deposito = saldo = None
        montos = self.patron_monto.findall(linea)
        
        if not montos:
            return retiro, deposito, saldo
            
        logger.info(f"\nProcesando línea: {linea}")
        logger.info(f"Montos encontrados: {montos}")
        
        # Dividir la línea en columnas aproximadas
        longitud_linea = len(linea)
        
        for monto in montos:
            pos_monto = linea.find(monto)
            logger.info(f"Analizando monto: {monto} en posición: {pos_monto}")
            
            # Determinar la columna basado en la posición relativa
            if pos_monto < longitud_linea * 0.4:  # Primera mitad - Columna RETIROS
                retiro = self._limpiar_monto(monto)
                logger.info(f"RETIRO detectado: {retiro}")
            elif pos_monto < longitud_linea * 0.7:  # Segunda mitad - Columna DEPOSITOS
                deposito = self._limpiar_monto(monto)
                logger.info(f"DEPÓSITO detectado: {deposito}")
            else:  # Última parte - Columna SALDO
                saldo = self._limpiar_monto(monto)
                logger.info(f"SALDO detectado: {saldo}")
        
        logger.info(f"Resultado final de la línea - Retiro: {retiro}, Depósito: {deposito}, Saldo: {saldo}")
        return retiro, deposito, saldo

    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        
        with pdfplumber.open(ruta_pdf) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto = pagina.extract_text()
                if not texto:
                    continue
                
                logger.info(f"\nProcesando página {num_pagina}")
                
                for linea in texto.split('\n'):
                    linea = linea.strip()
                    if not linea or any(x in linea for x in ['DETALLE DE OPERACIONES', 'ESTADO DE CUENTA', 'Página:', 'CLIENTE:']):
                        continue

                    if self._es_fecha(linea):
                        # Guardar transacción anterior si existe
                        if transaccion_actual:
                            logger.info(f"Guardando transacción: {asdict(transaccion_actual)}")
                            transacciones.append(transaccion_actual)
                        
                        # Iniciar nueva transacción
                        transaccion_actual = Transaccion(
                            fecha=linea[:6].strip(),
                            concepto=linea[6:].strip(),
                            retiro=None,
                            deposito=None,
                            saldo=None
                        )
                        lineas_concepto = [linea[6:].strip()]
                        logger.info(f"\nNueva transacción iniciada: {linea[:6]}")
                    
                    elif transaccion_actual:
                        # Procesar montos en la línea
                        retiro, deposito, saldo = self._procesar_montos_en_linea(linea)
                        
                        # Actualizar transacción con los montos encontrados
                        if retiro:
                            transaccion_actual.retiro = retiro
                            logger.info(f"Asignado retiro: {retiro}")
                        if deposito:
                            transaccion_actual.deposito = deposito
                            logger.info(f"Asignado depósito: {deposito}")
                        if saldo:
                            transaccion_actual.saldo = saldo
                            logger.info(f"Asignado saldo: {saldo}")
                        
                        # Si no hay montos, agregar al concepto
                        if not any([retiro, deposito, saldo]):
                            lineas_concepto.append(linea)
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()

        # Procesar última transacción
        if transaccion_actual:
            transacciones.append(transaccion_actual)
            logger.info(f"Guardando última transacción: {asdict(transaccion_actual)}")

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
