# -*- coding: utf-8 -*-
"""
QForestEyes Plugin
Detección de cambios forestales con Google Earth Engine + vectorización
"""

from qgis.PyQt.QtCore import QCoreApplication, QUrl, Qt
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QHBoxLayout
)
from qgis.core import QgsApplication, Qgis
from qgis.utils import iface
import os
import sys
import subprocess

# Importar módulos del plugin (¡con nombre QFEChangeDetector!)
from .qfe_detector import QFEChangeDetector, install_and_authenticate, get_user_parameters_with_zones, authenticate_gee
from .vectorizer import run_vectorization


class QForestEyesPlugin:
    """Plugin principal que registra tres acciones en QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.detector_instance = None

    def tr(self, message):
        return QCoreApplication.translate('QForestEyesPlugin', message)

    def initGui(self):
        # === BOTÓN 1: Detección de cambios ===
        icon_detect = QIcon(os.path.join(self.plugin_dir, 'icons', 'detect.png'))
        self.action_detect = QAction(icon_detect, self.tr("Detección de Cambios (GEE)"), self.iface.mainWindow())
        self.action_detect.setToolTip(self.tr("Dibuja un área y detecta cambios forestales con Google Earth Engine"))
        self.action_detect.triggered.connect(self.run_detection)
        self.iface.addToolBarIcon(self.action_detect)
        self.iface.addPluginToMenu("QForestEyes", self.action_detect)
        self.actions.append(self.action_detect)

        # === BOTÓN 2: Vectorizar resultados ===
        icon_vectorize = QIcon(os.path.join(self.plugin_dir, 'icons', 'vectorize.png'))
        self.action_vectorize = QAction(icon_vectorize, self.tr("Vectorizar Resultados"), self.iface.mainWindow())
        self.action_vectorize.setToolTip(self.tr("Vectoriza un raster de cambio y calcula hectáreas"))
        self.action_vectorize.triggered.connect(self.run_vectorization)
        self.iface.addToolBarIcon(self.action_vectorize)
        self.iface.addPluginToMenu("QForestEyes", self.action_vectorize)
        self.actions.append(self.action_vectorize)

        # === BOTÓN 3: Información y autenticación ===
        icon_info = QIcon(os.path.join(self.plugin_dir, 'icons', 'info.png'))
        self.action_info = QAction(icon_info, self.tr("Ayuda y Configuración GEE"), self.iface.mainWindow())
        self.action_info.setToolTip(self.tr("Requisitos y autenticación para Google Earth Engine"))
        self.action_info.triggered.connect(self.show_help_dialog)
        self.iface.addToolBarIcon(self.action_info)
        self.iface.addPluginToMenu("QForestEyes", self.action_info)
        self.actions.append(self.action_info)

        # Mensaje de bienvenida
        self.iface.messageBar().pushMessage(
            "QForestEyes",
            self.tr("Plugin cargado. Usa los botones para detectar cambios, vectorizar o configurar GEE."),
            level=Qgis.Info,
            duration=8
        )

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu("QForestEyes", action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        self.detector_instance = None

    def run_detection(self):
        try:
            if not install_and_authenticate():
                reply = QMessageBox.question(
                    None,
                    self.tr("Instalación requerida"),
                    self.tr("¿Deseas instalar 'earthengine-api' automáticamente?"),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "earthengine-api"])
                        if not install_and_authenticate():
                            QMessageBox.critical(None, self.tr("Error"), self.tr("Autenticación fallida. Usa el botón de Ayuda para autenticarte."))
                            return
                    except Exception as e:
                        QMessageBox.critical(None, self.tr("Error"), self.tr(f"No se pudo instalar earthengine-api:\n{str(e)}"))
                        return
                else:
                    return

            parametros = get_user_parameters_with_zones()
            if not parametros:
                return

            dates = {
                't1_start': parametros.pop('t1_start'),
                't1_end': parametros.pop('t1_end'),
                't2_start': parametros.pop('t2_start'),
                't2_end': parametros.pop('t2_end')
            }
            num_categories = parametros.pop('num_categories')

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

    def show_help_dialog(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("QForestEyes - Configuración de Google Earth Engine")
        dialog.setFixedSize(680, 480)
        
        layout = QVBoxLayout()
        
        title = QLabel("<h3>Configuración de Google Earth Engine</h3>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        info_text = QLabel(
            "Para usar QForestEyes necesitas una cuenta de Google Earth Engine. "
            "La autenticación solo se requiere <b>una vez</b> en tu computadora:"
        )
        info_text.setWordWrap(True)
        layout.addWidget(info_text)
        
        steps = QLabel(
            """
            <ol>
                <li><b>Registro en GEE (obligatorio):</b><br>
                    <a href="https://code.earthengine.google.com/register">https://code.earthengine.google.com/register</a></li>
                
                <li><b>Habilitar APIs (obligatorio):</b><br>
                    Activa estas APIs en Google Cloud Console:<br>
                    • Google Earth Engine API<br>
                    • Google Drive API<br>
                    <a href="https://console.cloud.google.com/apis/dashboard">https://console.cloud.google.com/apis/dashboard</a></li>
                
                <li><b>Autenticación (obligatorio):</b><br>
                    Usa el botón "🔐 Autenticar ahora con Google" en este diálogo<br>
                    (se abrirá tu navegador para iniciar sesión)</li>
                
                <li><b>Configuración IAM (opcional):</b><br>
                    <i>Solo necesario si compartes el proyecto con otros usuarios.<br>
                    En ese caso, asigna el rol "Earth Engine User" a cada colaborador:<br>
                    <a href="https://console.cloud.google.com/iam-admin/iam">https://console.cloud.google.com/iam-admin/iam</a></i></li>
            </ol>
            """
        )
        steps.setOpenExternalLinks(True)
        steps.setTextInteractionFlags(Qt.TextBrowserInteraction)
        steps.setWordWrap(True)
        layout.addWidget(steps)
        
        separator = QLabel("<hr>")
        layout.addWidget(separator)
        
        auth_layout = QVBoxLayout()
        auth_label = QLabel(
            "<b>🔑 Autenticación rápida (recomendado):</b><br>"
            "Haz clic abajo para autenticarte sin usar la terminal. "
            "Se abrirá tu navegador para iniciar sesión con Google."
        )
        auth_label.setWordWrap(True)
        auth_layout.addWidget(auth_label)
        
        auth_button = QPushButton("Autenticar ahora con Google")
        auth_button.setStyleSheet("background-color: #1ED760; color: #082D12; font-weight: bold; padding: 8px;")
        auth_button.clicked.connect(lambda: self._authenticate_and_close(dialog))
        auth_layout.addWidget(auth_button)
        
        layout.addLayout(auth_layout)
        
        note = QLabel(
            "<i>💡 Nota: La autenticación se guarda en tu computadora. "
            "Solo necesitas hacerlo una vez (a menos que limpies cookies o cambies de cuenta).</i>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555; margin-top: 10px; font-size: 10px;")
        layout.addWidget(note)
        
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def _authenticate_and_close(self, dialog):
        dialog.setEnabled(False)
        if authenticate_gee():
            dialog.accept()
            self.iface.messageBar().pushMessage(
                "GEE", "¡Autenticación exitosa! Ya puedes usar QForestEyes.",
                level=Qgis.Success, duration=8
            )
        else:
            dialog.setEnabled(True)