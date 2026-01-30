# -*- coding: utf-8 -*-
"""
QForestEyes Plugin - Punto de entrada
"""

from .main import QForestEyesPlugin


def classFactory(iface):
    """
    Instanciar el plugin cuando QGIS lo carga.
    
    :param iface: Interfaz de QGIS (QgisInterface)
    :return: Instancia del plugin
    """
    return QForestEyesPlugin(iface)