from dataclasses import asdict
import json
import logging
import re
import pdfplumber
from typing import Dict, Tuple, List
from .base import ProcesadorBase, Transaccion

logger = logging.getLogger(__name__)

class ProcesadorCitibanamex(ProcesadorBase):
    # Constantes para conceptos especiales
    NUMERO_CHEQUES_EXENTOS = "NUMERO DE CHEQUES EXENTOS"
    SALDO_MINIMO_REQUERIDO = "SALDO MINIMO REQUERIDO"
    DETALLE_OPERACIONES = "DETALLE DE OPERACIONES"

    # Constantes para tipos de transacciones
    CONCEPTOS_DEPOSITO = ["PAGO RECIBIDO", "ABONO", "INTERESES PAGADOS", "VENTA", "SU RENDIMIENTO"]
    CONCEPTOS_RETIRO = ["RETIRO", "PAGO"]

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self.patron_fecha = re.compile(r'^\d{2}\s+[A-Z]{3}\b')
        self.patron_monto = re.compile(r'[\d,]+\.\d{2}')
        self.patron_identificador_pagina = re.compile(r'^\d+\.([A-Z]|[0-9])+\.([A-Z]|[0-9])+\.\d+\.\d+$')
        self.patron_encabezado_columnas = re.compile(r'^FECHA\s+CONCEPTO\s+RETIROS\s+DEPOSITOS\s+SALDO$')
        self.patron_hora_suc = re.compile(r'^HORA\s+\d{2}:\d{2}\s+SUC\s+\d{4}$')
        self.ignorar_lineas = False

    def _es_fecha(self, linea: str) -> bool:
        return bool(self.patron_fecha.match(linea))

    def _es_identificador_pagina(self, linea: str) -> bool:
        return bool(self.patron_identificador_pagina.match(linea.strip()))

    def _procesar_linea_montos(self, linea: str, concepto: str) -> Tuple[str | None, str | None, str | None]:
        montos = self.patron_monto.findall(linea)
        self.logger.info(f"Procesando montos: {montos}")
        
        retiro = None
        deposito = None
        saldo = None
        
        # Nueva validación para NUMERO DE CHEQUES EXENTOS
        if self.NUMERO_CHEQUES_EXENTOS in concepto.upper():
            if montos:
                saldo = montos[0]
                self.logger.info(f"Monto asignado como saldo por regla {self.NUMERO_CHEQUES_EXENTOS}: {saldo}")
                return retiro, deposito, saldo
        
        # Primero aplicamos las reglas de negocio basadas en el concepto
        if any(palabra in concepto.upper() for palabra in self.CONCEPTOS_DEPOSITO):
            if montos:
                deposito = montos[0]
                self.logger.info(f"Monto asignado como depósito por regla de negocio: {deposito}")
        elif any(palabra in concepto.upper() for palabra in self.CONCEPTOS_RETIRO):
            if montos:
                retiro = montos[0]
                self.logger.info(f"Monto asignado como retiro por regla de negocio: {retiro}")
        else:
            # Si no hay reglas específicas y hay un solo monto, se considera retiro por defecto
            if len(montos) == 1:
                retiro = montos[0]
                self.logger.info(f"Monto asignado como retiro por defecto: {retiro}")
        
        # El último monto siempre es el saldo cuando hay más de un monto
        if len(montos) > 1:
            saldo = montos[-1]
            self.logger.info(f"Último monto asignado como saldo: {saldo}")
        
        return retiro, deposito, saldo

    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        transacciones = []
        transaccion_actual = None
        lineas_concepto = []
        
        with pdfplumber.open(ruta_pdf) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto = pagina.extract_text(layout=True)
                self.logger.info('='*80)
                self.logger.info(f"Procesando página {num_pagina}")
                self.logger.info('='*80)
                
                for linea in texto.split('\n'):
                    linea = linea.strip()
                    
                    # Ignorar líneas de pie de página
                    if self._es_identificador_pagina(linea):
                        self.logger.info("Detectado identificador de página - Iniciando modo ignorar")
                        self.ignorar_lineas = True
                        continue
                    
                    if self.ignorar_lineas:
                        if self.DETALLE_OPERACIONES in linea:
                            self.logger.info("Encontrado DETALLE DE OPERACIONES")
                            continue
                        elif self.patron_encabezado_columnas.match(linea):
                            self.logger.info("Encontrado encabezado de columnas - Finalizando modo ignorar")
                            self.ignorar_lineas = False
                        continue
                    
                    # Ignorar líneas de HORA SUC que aparecen al pie
                    if self.patron_hora_suc.match(linea):
                        self.logger.info(f"Ignorando línea de HORA SUC: {linea}")
                        continue
                    
                    if self._es_fecha(linea):
                        if transaccion_actual:
                            self.logger.info("----- Fin de transacción -----")
                            self.logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        self.logger.info("★★★★★ NUEVA TRANSACCIÓN DETECTADA ★★★★★")
                        linea_limpia = linea.strip()
                        fecha = linea_limpia[:7].strip()
                        concepto = linea_limpia[7:].strip()
                        
                        self.logger.info(f"Fecha encontrada: {fecha}")
                        self.logger.info(f"Concepto inicial: {concepto}")
                        
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
                            self.logger.info(">>> Validación de montos <<<")
                            self.logger.info(f"Línea analizada: {linea}")
                            self.logger.info(f"Aplicando reglas de negocio para concepto: {transaccion_actual.concepto}")
                            
                            retiro, deposito, saldo = self._procesar_linea_montos(
                                linea, 
                                transaccion_actual.concepto
                            )
                            
                            if retiro: 
                                transaccion_actual.retiro = retiro
                                self.logger.info(f"✓ RETIRO identificado: ${retiro}")
                            if deposito: 
                                transaccion_actual.deposito = deposito
                                self.logger.info(f"✓ DEPÓSITO identificado: ${deposito}")
                            if saldo: 
                                transaccion_actual.saldo = saldo
                                self.logger.info(f"✓ SALDO identificado: ${saldo}")
                        else:
                            lineas_concepto.append(linea.strip())
                            transaccion_actual.concepto = ' '.join(lineas_concepto).strip()
                    
                    # Detectar final de la tabla de movimientos
                    if self.SALDO_MINIMO_REQUERIDO in linea:
                        if transaccion_actual:
                            self.logger.info("----- Fin de última transacción -----")
                            self.logger.info(json.dumps(asdict(transaccion_actual), indent=2, ensure_ascii=False))
                            transacciones.append(transaccion_actual)
                        
                        self.logger.info("\n" + "="*80)
                        self.logger.info("RESUMEN FINAL")
                        self.logger.info("="*80)
                        
                        estadisticas = self._calcular_estadisticas(transacciones)
                        self.logger.info("\nEstadísticas del estado de cuenta:")
                        self.logger.info(json.dumps(estadisticas, indent=2, ensure_ascii=False))
                        
                        return {
                            "estado_cuenta": {
                                "movimientos": [asdict(t) for t in transacciones],
                                "estadisticas": estadisticas
                            }
                        }
        
        return {
            "estado_cuenta": {
                "movimientos": [asdict(t) for t in transacciones],
                "estadisticas": self._calcular_estadisticas(transacciones)
            }
        } 