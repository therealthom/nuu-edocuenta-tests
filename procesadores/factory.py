from enum import Enum
from typing import Dict
from .base import ProcesadorBase
from .citibanamex import ProcesadorCitibanamex
import logging

class TipoBanco(Enum):
    CITIBANAMEX = "CITIBANAMEX"
    # Agregar más bancos aquí
    
class ProcesadorFactory:
    @staticmethod
    def crear_procesador(tipo_banco: TipoBanco, logger: logging.Logger) -> ProcesadorBase:
        if tipo_banco == TipoBanco.CITIBANAMEX:
            return ProcesadorCitibanamex(logger)
        # Agregar más casos para otros bancos
        else:
            raise ValueError(f"Tipo de banco no soportado: {tipo_banco}") 