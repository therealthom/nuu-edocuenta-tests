from dataclasses import asdict
import json
import logging
import re
import pdfplumber
from typing import Dict, Tuple, List
from .base import ProcesadorBase, Transaccion
import os

logger = logging.getLogger(__name__)

class ProcesadorBBVA(ProcesadorBase):
    # Constantes para identificar secciones
    INICIO_MOVIMIENTOS = "Detalle de Movimientos Realizados"
    FIN_MOVIMIENTOS = "Total de Movimientos"
    
    # Constantes para tipos de transacciones
    CONCEPTOS_DEPOSITO = ["RECIBIDO", "DEPOSITO", "INTERESES GANADOS"]
    CONCEPTOS_RETIRO = ["ENVIADO", "TRASPASO A TERCEROS", "TRASPASO ENTRE CUENTAS"]
    
    # Constantes para patrones de expresiones regulares
    PATRON_FECHA = r'^\d{2}/\w{3}\b'
    PATRON_MONTO = r'[\d,]+\.\d{2}'
    PATRON_CARGO = r'\s+([\d,]+\.\d{2})\s+(?:\d{1,3}(?:,\d{3})*\.\d{2}){2}$'
    PATRON_ABONO = r'\s+(?:\d{1,3}(?:,\d{3})*\.\d{2})\s+([\d,]+\.\d{2})\s+\d{1,3}(?:,\d{3})*\.\d{2}$'

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self.patron_fecha = re.compile(self.PATRON_FECHA)
        self.patron_monto = re.compile(self.PATRON_MONTO)
        self.es_seccion_movimientos = False

    def _es_concepto_retiro(self, concepto: str) -> bool:
        return any(keyword in concepto.upper() for keyword in self.CONCEPTOS_RETIRO)

    def _es_concepto_deposito(self, concepto: str) -> bool:
        return any(keyword in concepto.upper() for keyword in self.CONCEPTOS_DEPOSITO)

    def _es_fecha(self, linea: str) -> bool:
        return bool(self.patron_fecha.match(linea))

    def _procesar_linea_montos(self, linea: str, concepto: str) -> Tuple[str | None, str | None, str | None]:
        montos = self.patron_monto.findall(linea)
        self.logger.info(f"Procesando montos: {montos}")
        
        retiro = None
        deposito = None
        saldo = None
        
        # Procesar montos según las reglas de BBVA
        if montos:
            # Verificar primero en la columna CARGOS
            cargo_match = re.search(self.PATRON_CARGO, linea)
            if cargo_match:
                retiro = cargo_match.group(1)
                self.logger.info(f"Monto encontrado en columna CARGOS: {retiro}")
            else:
                # Verificar en la columna ABONOS
                abono_match = re.search(self.PATRON_ABONO, linea)
                if abono_match:
                    deposito = abono_match.group(1)
                    self.logger.info(f"Monto encontrado en columna ABONOS: {deposito}")
            
            # El último monto siempre es el saldo
            saldo = montos[-1]
            self.logger.info(f"Saldo encontrado: {saldo}")
        
        return retiro, deposito, saldo

    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        
        self.logger.info("\n" + "="*80)
        self.logger.info(f"INICIANDO PROCESAMIENTO DEL ARCHIVO: {os.path.basename(ruta_pdf)}")
        self.logger.info("="*80)
        
        with pdfplumber.open(ruta_pdf) as pdf:
            self.es_seccion_movimientos = False
            
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto = pagina.extract_text(layout=True)
                self.logger.info("\n" + "-"*80)
                self.logger.info(f"PROCESANDO PÁGINA {num_pagina}")
                self.logger.info("-"*80)
                
                lineas = texto.split('\n')
                for linea in lineas:
                    linea = linea.strip()
                    
                    # Verificar inicio y fin de sección de movimientos
                    if self.INICIO_MOVIMIENTOS in linea:
                        self.es_seccion_movimientos = True
                        self.logger.info("\n>>> INICIO DE SECCIÓN DE MOVIMIENTOS DETECTADO <<<")
                        continue
                        
                    if self.FIN_MOVIMIENTOS in linea:
                        self.es_seccion_movimientos = False
                        self.logger.info("\n>>> FIN DE SECCIÓN DE MOVIMIENTOS DETECTADO <<<")
                        break
                    
                    if not self.es_seccion_movimientos:
                        continue
                    
                    # Detectar línea de fecha (DD/MMM)
                    fecha_match = re.match(r'^(\d{2}/\w{3})', linea)
                    if fecha_match:
                        # Si hay una transacción en proceso, guardarla
                        if transaccion_actual:
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()
                            self.logger.info("----- Fin de transacción anterior -----")
                            self.logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        self.logger.info("\n***** NUEVA TRANSACCIÓN DETECTADA *****")
                        fecha = fecha_match.group(1)
                        self.logger.info(f"Fecha encontrada: {fecha}")
                        
                        # Extraer montos
                        montos = re.findall(r'[\d,]+\.\d{2}', linea)
                        self.logger.info(f"Montos encontrados en línea: {montos}")
                        
                        retiro = deposito = saldo = None
                        if montos:
                            # El primer monto puede ser cargo o abono
                            if len(montos) >= 1:
                                if self._es_concepto_retiro(linea):
                                    retiro = montos[0]
                                    self.logger.info(f"Monto clasificado como RETIRO: {retiro}")
                                elif self._es_concepto_deposito(linea):
                                    deposito = montos[0]
                                    self.logger.info(f"Monto clasificado como DEPÓSITO: {deposito}")
                            
                            # El último monto es el saldo
                            if len(montos) > 1:
                                saldo = montos[-1]
                                self.logger.info(f"Saldo identificado: {saldo}")
                        
                        # Crear nueva transacción
                        transaccion_actual = Transaccion(
                            fecha=fecha,
                            concepto='',  # Se llenará con las líneas siguientes
                            retiro=retiro,
                            deposito=deposito,
                            saldo=saldo,
                            pagina=num_pagina
                        )
                        
                        # Iniciar recolección de concepto
                        concepto_inicial = linea[7:].strip()  # Después de la fecha
                        self.logger.info(f"Concepto inicial: {concepto_inicial}")
                        lineas_concepto = [concepto_inicial]
                        
                    elif transaccion_actual and linea:
                        self.logger.info(f"Agregando línea adicional al concepto: {linea}")
                        lineas_concepto.append(linea)
                
                self.logger.info(f"\nFin del procesamiento de página {num_pagina}")
        
        # Agregar última transacción si existe
        if transaccion_actual:
            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()
            self.logger.info("----- Guardando última transacción -----")
            self.logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
            transacciones.append(transaccion_actual)
        
        self.logger.info("\n" + "="*80)
        self.logger.info("RESUMEN FINAL")
        self.logger.info("="*80)
        
        if not transacciones:
            self.logger.warning("¡No se encontraron transacciones en el documento!")
        else:
            self.logger.info(f"Total de transacciones encontradas: {len(transacciones)}")
        
        estadisticas = self._calcular_estadisticas(transacciones)
        self.logger.info("\nEstadísticas del estado de cuenta:")
        self.logger.info(json.dumps(estadisticas, indent=2, ensure_ascii=False))
        
        return {
            "estado_cuenta": {
                "movimientos": [asdict(t) for t in transacciones],
                "estadisticas": estadisticas
            }
        }