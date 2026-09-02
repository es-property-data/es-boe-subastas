"""Jerarquía de excepciones del recolector.
El punto de entrada las traduce a códigos de salida.
"""


class BoeSubastasError(Exception):
    """Base de todos los errores previstos del recolector."""


class SourceUnavailableError(BoeSubastasError):
    """La fuente no responde: fallo de red, timeout, error del servidor o bloqueo.

    Se traduce al código de salida 3.
    """


class AuthenticationError(BoeSubastasError):
    """No se pudo iniciar sesión en el portal o la sesión ha caducado.

    Impide acceder a la vista autenticada de la fuente; código de salida 3.
    """


class QueryError(BoeSubastasError):
    """La fuente rechazó la consulta (p. ej. demasiados resultados).

    Requiere acotar los filtros: se trata como uso incorrecto, código 2.
    """


class StructureError(BoeSubastasError):
    """Se descargó contenido pero no se pudo interpretar.

    Señal de que la fuente cambió su estructura y el parser necesita
    mantenimiento; código de salida 4.
    """


class ItemNotFoundError(BoeSubastasError):
    """El identificador solicitado no existe en la fuente."""
