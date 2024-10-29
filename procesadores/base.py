from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List
import logging
from decimal import Decimal, ROUND_HALF_UP

@dataclass
class Transaccion:
    fecha: str
    concepto: str
    retiro: str | None
    deposito: str | None
    saldo: str | None
    pagina: int

class ProcesadorBase(ABC):
    """Clase base abstracta para procesadores de estados de cuenta"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        # Asegurar que el logger tenga al menos un handler
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @abstractmethod
    def procesar_pdf(self, ruta_pdf: str) -> Dict:
        """Procesa el PDF y retorna un diccionario con los resultados"""
        pass
    
    def _limpiar_monto(self, monto: str) -> Decimal:
        """Limpia el string de monto y lo convierte a Decimal para precisión"""
        if not monto:
            return Decimal('0')
        # Eliminar símbolos de moneda, espacios y comas
        monto = monto.strip().replace('$', '').replace(' ', '').replace(',', '')
        return Decimal(monto)
    
    def _calcular_estadisticas(self, transacciones: List[Transaccion]) -> Dict:
        """Método común para calcular estadísticas"""
        self.logger.info("\nCalculando estadísticas:")
        
        total_retiros = sum(1 for t in transacciones if t.retiro is not None)
        total_depositos = sum(1 for t in transacciones if t.deposito is not None)
        
        # Debug para verificar cada monto
        suma_retiros = Decimal('0')
        suma_depositos = Decimal('0')
        
        for t in transacciones:
            if t.retiro is not None:
                monto_retiro = self._limpiar_monto(t.retiro)
                suma_retiros += monto_retiro
                self.logger.info(f"Retiro encontrado: {t.retiro}")
                self.logger.info(f"Monto limpio: {monto_retiro}")
                self.logger.info(f"Suma parcial retiros: {suma_retiros}")
            
            if t.deposito is not None:
                monto_deposito = self._limpiar_monto(t.deposito)
                suma_depositos += monto_deposito
                self.logger.info(f"Depósito encontrado: {t.deposito}")
                self.logger.info(f"Monto limpio: {monto_deposito}")
                self.logger.info(f"Suma parcial depósitos: {suma_depositos}")
        
        estadisticas = {
            "numero_transacciones": len(transacciones),
            "cantidad_retiros": total_retiros,
            "cantidad_depositos": total_depositos,
            "suma_retiros": str(suma_retiros.quantize(Decimal('0.01'))),
            "suma_depositos": str(suma_depositos.quantize(Decimal('0.01')))
        }
        
        return estadisticas