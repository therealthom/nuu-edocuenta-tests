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

    def _extraer_tabla(self, page) -> List[List[str]]:
        """Extrae la tabla usando pdfplumber y retorna las filas"""
        tabla = page.extract_table()
        logger.info("Contenido extraído de la página:")
        if tabla:
            for fila in tabla:
                logger.info(f"FILA: {fila}")
        else:
            logger.warning("No se detectó tabla en la página")
        return [[str(cell).strip() if cell else '' for cell in row] for row in tabla] if tabla else []

    def _detectar_columnas(self, texto: str) -> Dict[str, int]:
        """
        Detecta las posiciones de las columnas usando el encabezado
        """
        for linea in texto.split('\n'):
            if 'FECHA' in linea and 'CONCEPTO' in linea and 'RETIROS' in linea:
                logger.info(f"Encabezado encontrado: [{linea}]")
                
                # Encontrar posiciones exactas
                pos_fecha = linea.find('FECHA')
                pos_concepto = linea.find('CONCEPTO')
                pos_retiros = linea.find('RETIROS')
                pos_depositos = linea.find('DEPOSITOS')
                pos_saldo = linea.find('SALDO')
                
                logger.info(f"Posiciones - FECHA: {pos_fecha}, CONCEPTO: {pos_concepto}, "
                           f"RETIROS: {pos_retiros}, DEPOSITOS: {pos_depositos}, SALDO: {pos_saldo}")
                
                if all(pos >= 0 for pos in [pos_fecha, pos_concepto, pos_retiros, pos_depositos, pos_saldo]):
                    columnas = {
                        'fecha': (0, pos_concepto),
                        'concepto': (pos_concepto, pos_retiros),
                        'retiros': (pos_retiros, pos_depositos),
                        'depositos': (pos_depositos, pos_saldo),
                        'saldo': (pos_saldo, float('inf'))
                    }
                    logger.info(f"Rangos de columnas detectados: {columnas}")
                    return columnas
        
        return None

    def _determinar_tipo_monto(self, linea: str, monto: str, columnas: Dict) -> tuple:
        """
        Determina el tipo de monto basado en su posición y los rangos de columnas
        """
        if not columnas:
            return None, None, None
        
        pos_monto = linea.find(monto)
        logger.info(f"Analizando monto {monto} en posición {pos_monto}")
        
        # Determinar en qué columna cae el monto
        if columnas['retiros'][0] <= pos_monto < columnas['retiros'][1]:
            logger.info(f"Monto {monto} identificado como RETIRO")
            return monto, None, None
        elif columnas['depositos'][0] <= pos_monto < columnas['depositos'][1]:
            logger.info(f"Monto {monto} identificado como DEPÓSITO")
            return None, monto, None
        elif columnas['saldo'][0] <= pos_monto:
            logger.info(f"Monto {monto} identificado como SALDO")
            return None, None, monto
        
        return None, None, None

    def _procesar_montos_en_linea(self, linea: str, concepto: str) -> tuple:
        """
        Procesa los montos en una línea usando las reglas de negocio:
        - Si el concepto contiene 'PAGO RECIBIDO', es un depósito
        - Si hay dos montos, el último siempre es saldo
        - Si no dice 'PAGO RECIBIDO' y hay dos montos, el primero es retiro
        """
        montos = self.patron_monto.findall(linea)
        if not montos:
            return None, None, None
        
        logger.info(f"Línea con montos: [{linea}]")
        logger.info(f"Concepto: [{concepto}]")
        logger.info(f"Montos encontrados: {montos}")
        
        retiro = deposito = saldo = None
        es_pago_recibido = 'PAGO RECIBIDO' in concepto.upper()
        
        if len(montos) == 2:
            # El último monto siempre es saldo
            saldo = self._limpiar_monto(montos[1])
            logger.info(f"Segundo monto es SALDO: {saldo}")
            
            # El primer monto es depósito o retiro según el concepto
            if es_pago_recibido:
                deposito = self._limpiar_monto(montos[0])
                logger.info(f"PAGO RECIBIDO - Primer monto es DEPÓSITO: {deposito}")
            else:
                retiro = self._limpiar_monto(montos[0])
                logger.info(f"Primer monto es RETIRO: {retiro}")
        
        elif len(montos) == 1:
            # Un solo monto es depósito o retiro según el concepto
            if es_pago_recibido:
                deposito = self._limpiar_monto(montos[0])
                logger.info(f"PAGO RECIBIDO - Monto único es DEPÓSITO: {deposito}")
            else:
                retiro = self._limpiar_monto(montos[0])
                logger.info(f"Monto único es RETIRO: {retiro}")
        
        return retiro, deposito, saldo

    def _esta_en_tabla(self, linea: str) -> bool:
        """
        Determina si una línea pertenece a la tabla de operaciones
        """
        # Ignorar líneas que no son parte de la tabla
        if any(texto in linea for texto in [
            'DETALLE DE OPERACIONES',
            'ESTADO DE CUENTA',
            'CLIENTE:',
            'Página:',
            '.B15CHDA',
            'GOBIERNO DEL ESTADO'
        ]):
            return False
        
        # La línea debe tener el formato esperado (fecha o espacios al inicio)
        return bool(self._es_fecha(linea) or linea.startswith(' '))

    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        en_tabla = False
        
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text(layout=True)
                
                for linea in texto.split('\n'):
                    # Ignorar líneas vacías
                    if not linea.strip():
                        continue
                    
                    # Verificar si estamos en la tabla
                    if 'DETALLE DE OPERACIONES' in linea:
                        en_tabla = True
                        continue
                    
                    # Solo procesar líneas dentro de la tabla
                    if not en_tabla or not self._esta_en_tabla(linea):
                        continue
                    
                    logger.info(f"Procesando línea de tabla: [{linea}]")
                    
                    # Si es una nueva fecha
                    if self._es_fecha(linea):
                        logger.info(f"\nNueva fecha detectada: {linea[:6]}")
                        
                        if transaccion_actual:
                            logger.info(f"Guardando transacción: {asdict(transaccion_actual)}")
                            transacciones.append(transaccion_actual)
                        
                        transaccion_actual = Transaccion(
                            fecha=linea[:6].strip(),
                            concepto=linea[6:].strip(),
                            retiro=None,
                            deposito=None,
                            saldo=None
                        )
                        lineas_concepto = [linea[6:].strip()]
                    
                    elif transaccion_actual:
                        if self.patron_monto.search(linea):
                            retiro, deposito, saldo = self._procesar_montos_en_linea(
                                linea, 
                                transaccion_actual.concepto
                            )
                            
                            if retiro:
                                transaccion_actual.retiro = retiro
                            if deposito:
                                transaccion_actual.deposito = deposito
                            if saldo:
                                transaccion_actual.saldo = saldo
                        else:
                            lineas_concepto.append(linea.strip())
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()

        # Guardar última transacción
        if transaccion_actual:
            transacciones.append(transaccion_actual)

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
