# -*- coding: utf-8 -*-
"""
QForestEyes Plugin
Detección de cambios forestales con Google Earth Engine + vectorización
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsApplication, Qgis
from qgis.utils import iface
import os
import sys
import subprocess

# Importar módulos del plugin
from .qfe_detector import QFEChangeDetector, install_and_authenticate, get_user_parameters_with_zones
from .vectorizer import run_vectorization


class QForestEyesPlugin:
    """Plugin principal que registra dos acciones independientes en QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.detector_instance = None  # Mantener referencia viva durante el dibujo

    def tr(self, message):
        """Soporte para traducciones (placeholder)."""
        return QCoreApplication.translate('QForestEyesPlugin', message)

    def initGui(self):
        """Registrar las dos acciones en la barra de herramientas y menú."""
        
        # === ACCIÓN 1: Detección de cambios con GEE ===
        icon_detect = QIcon(os.path.join(self.plugin_dir, 'icons', 'detect.png'))
        self.action_detect = QAction(icon_detect, self.tr("Detección de Cambios (GEE)"), self.iface.mainWindow())
        self.action_detect.setObjectName("qforesteyes_detect")
        self.action_detect.setToolTip(self.tr("Dibuja un área y detecta cambios forestales con Google Earth Engine"))
        self.action_detect.triggered.connect(self.run_detection)
        self.iface.addToolBarIcon(self.action_detect)
        self.iface.addPluginToMenu("QForestEyes", self.action_detect)
        self.actions.append(self.action_detect)

        # === ACCIÓN 2: Vectorizar resultados ===
        icon_vectorize = QIcon(os.path.join(self.plugin_dir, 'icons', 'vectorize.png'))
        self.action_vectorize = QAction(icon_vectorize, self.tr("Vectorizar Resultados"), self.iface.mainWindow())
        self.action_vectorize.setObjectName("qforesteyes_vectorize")
        self.action_vectorize.setToolTip(self.tr("Vectoriza un raster de cambio (valores 1-5) y calcula hectáreas"))
        self.action_vectorize.triggered.connect(self.run_vectorization)
        self.iface.addToolBarIcon(self.action_vectorize)
        self.iface.addPluginToMenu("QForestEyes", self.action_vectorize)
        self.actions.append(self.action_vectorize)

        # === Mensaje de bienvenida ===
        self.iface.messageBar().pushMessage(
            "QForestEyes",
            self.tr("Plugin cargado. Usa los botones en la barra de herramientas para detectar cambios o vectorizar resultados."),
            level=Qgis.Info,
            duration=8
        )

    def unload(self):
        """Eliminar acciones al desinstalar el plugin."""
        for action in self.actions:
            self.iface.removePluginMenu("QForestEyes", action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        self.detector_instance = None

    def run_detection(self):
        """Ejecutar flujo de detección de cambios con GEE."""
        try:
            # Verificar e instalar earthengine-api si es necesario
            if not install_and_authenticate():
                reply = QMessageBox.question(
                    None,
                    self.tr("Instalación requerida"),
                    self.tr("¿Deseas intentar instalar 'earthengine-api' automáticamente?"),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "earthengine-api"])
                        if not install_and_authenticate():
                            QMessageBox.critical(None, self.tr("Error"), self.tr("Autenticación fallida. Ejecuta 'earthengine authenticate' en tu terminal."))
                            return
                    except Exception as e:
                        QMessageBox.critical(None, self.tr("Error"), self.tr(f"No se pudo instalar earthengine-api:\n{str(e)}"))
                        return
                else:
                    return

            # Obtener parámetros del usuario
            parametros = get_user_parameters_with_zones()
            if not parametros:
                return

            # Separar fechas y preparar detector
            dates = {
                't1_start': parametros.pop('t1_start'),
                't1_end': parametros.pop('t1_end'),
                't2_start': parametros.pop('t2_start'),
                't2_end': parametros.pop('t2_end')
            }
            num_categories = parametros.pop('num_categories')

            # Crear instancia del detector (se mantiene viva durante el dibujo)
            self.detector_instance = QFEChangeDetector(
                project_id=parametros['project_id'],
                umbrales=parametros['umbrales'],
                dates=dates,
                num_categories=num_categories
            )

        except Exception as e:
            QMessageBox.critical(None, self.tr("Error"), self.tr(f"Error al iniciar detección:\n{str(e)}"))
            import traceback
            QgsApplication.instance().messageLog().logMessage(
                f"QForestEyes error:\n{traceback.format_exc()}",
                "QForestEyes",
                Qgis.Critical
            )

    def run_vectorization(self):
        """Ejecutar flujo de vectorización."""
        try:
            run_vectorization()
        except Exception as e:
            QMessageBox.critical(None, self.tr("Error"), self.tr(f"Error al vectorizar:\n{str(e)}"))
            import traceback
            QgsApplication.instance().messageLog().logMessage(
                f"QForestEyes vectorization error:\n{traceback.format_exc()}",
                "QForestEyes",
                Qgis.Critical
            )