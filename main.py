# -*- coding: utf-8 -*-
"""
QForestEyes Plugin
Detección de cambios forestales con Google Earth Engine + vectorización
"""

from qgis.PyQt.QtCore import QCoreApplication, QUrl, Qt
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QHBoxLayout, QInputDialog
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
        # === BOTÓN 1: Información y autenticación ===
        icon_info = QIcon(os.path.join(self.plugin_dir, 'icons', 'info.png'))
        self.action_info = QAction(icon_info, self.tr("Ayuda y Configuración GEE"), self.iface.mainWindow())
        self.action_info.setToolTip(self.tr("Requisitos y autenticación para Google Earth Engine"))
        self.action_info.triggered.connect(self.show_help_dialog)
        self.iface.addToolBarIcon(self.action_info)
        self.iface.addPluginToMenu("QForestEyes", self.action_info)
        self.actions.append(self.action_info)
        
        # === BOTÓN 1: Detección de cambios ===
        icon_detect = QIcon(os.path.join(self.plugin_dir, 'icons', 'detect.png'))
        self.action_detect = QAction(icon_detect, self.tr("Detección de Cambios (GEE)"), self.iface.mainWindow())
        self.action_detect.setToolTip(self.tr("Dibuja un área y detecta cambios forestales con Google Earth Engine"))
        self.action_detect.triggered.connect(self.run_detection)
        self.iface.addToolBarIcon(self.action_detect)
        self.iface.addPluginToMenu("QForestEyes", self.action_detect)
        self.actions.append(self.action_detect)

        # === BOTÓN 3: Vectorizar resultados ===
        icon_vectorize = QIcon(os.path.join(self.plugin_dir, 'icons', 'vectorize.png'))
        self.action_vectorize = QAction(icon_vectorize, self.tr("Vectorizar Resultados"), self.iface.mainWindow())
        self.action_vectorize.setToolTip(self.tr("Vectoriza un raster de cambio y calcula hectáreas"))
        self.action_vectorize.triggered.connect(self.run_vectorization)
        self.iface.addToolBarIcon(self.action_vectorize)
        self.iface.addPluginToMenu("QForestEyes", self.action_vectorize)
        self.actions.append(self.action_vectorize)

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
                # Importación local para evitar conflictos de rutas al iniciar
                from .qfe_detector import (
                    install_and_authenticate, 
                    get_user_parameters_with_zones, 
                    QFEChangeDetector
                )
                
                # Paso 1: Validar/Instalar API de forma silenciosa
                if not install_and_authenticate():
                    return

                # Paso 2: Obtener parámetros del usuario
                parametros = get_user_parameters_with_zones()
                if not parametros:
                    return

                # Paso 3: Organizar datos
                dates = {
                    't1_start': parametros.pop('t1_start'),
                    't1_end': parametros.pop('t1_end'),
                    't2_start': parametros.pop('t2_start'),
                    't2_end': parametros.pop('t2_end')
                }
                num_categories = parametros.pop('num_categories')

                # Paso 4: Activar el detector y la herramienta de dibujo
                self.detector_instance = QFEChangeDetector(
                    project_id=parametros['project_id'],
                    umbrales=parametros['umbrales'],
                    dates=dates,
                    num_categories=num_categories
                )

            except Exception as e:
                QMessageBox.critical(None, self.tr("Error"), self.tr(f"Error al iniciar detección:\n{str(e)}"))

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
                    en la página de registro de Earth Engine cree un proyecto (si aun no tiene uno) y asi obtenga su ID proyecto (presionando ctrl + o) <br>
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
            "Se abrirá tu navegador para iniciar sesión con Google. (espera unos minutos y se abrirá el navegador pidiendote que confirmes que inicias sesion en Google, posiblemente te manden un codigo de verificación a tu movil para confirmar) ESTO SE HACE POR UNICA VEZ 😁"
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
        console_btn = QPushButton("🛠️ Configuración Avanzada (Terminal)")
        console_btn.setStyleSheet("background-color: #f0f0f0; font-weight: bold; padding: 8px;")
        console_btn.clicked.connect(self.setup_gee_console)        
        layout.addWidget(console_btn)
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

    def setup_gee_console(self):
            """Versión Universal: Detecta la versión de Python automáticamente."""
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                "Configuración GEE",
                "¿Deseas configurar Google Earth Engine?\n\n"
                "Se abrirá una consola independiente para evitar conflictos con QGIS.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

            project_id, ok = QInputDialog.getText(
                self.iface.mainWindow(), 
                "ID de Proyecto", 
                "Ingresa tu Project ID de Google Cloud:"
            )
            if not (ok and project_id):
                return

            # --- 1. DETECCIÓN DINÁMICA DE RUTAS ---
            # En lugar de "Python312", usamos sys.prefix para encontrar la carpeta real
            # sys.prefix en QGIS apunta a ".../apps/Python3xx"
            python_exe = os.path.join(sys.prefix, "python.exe")

            # Verificar si existe (por seguridad)
            if not os.path.exists(python_exe):
                # Plan B: Intentar deducir desde el ejecutable de QGIS
                bin_dir = os.path.dirname(sys.executable)
                qgis_root = os.path.dirname(bin_dir)
                # Buscamos cualquier carpeta que empiece con "Python3" dentro de apps
                apps_path = os.path.join(qgis_root, "apps")
                if os.path.exists(apps_path):
                    for folder in os.listdir(apps_path):
                        if folder.startswith("Python3") and os.path.isdir(os.path.join(apps_path, folder)):
                            python_exe = os.path.join(apps_path, folder, "python.exe")
                            break
            
            if not os.path.exists(python_exe):
                QMessageBox.critical(None, "Error", f"No se pudo localizar el intérprete de Python.")
                return

            # Calcular la carpeta de Scripts del usuario según la versión actual (ej. Python39, Python312)
            py_version = f"Python{sys.version_info.major}{sys.version_info.minor}"
            appdata_scripts = os.path.join(os.environ['APPDATA'], "Python", py_version, "Scripts")
            earthengine_exe = os.path.join(appdata_scripts, "earthengine.exe")

            # --- 2. CREAR EL SCRIPT ---
            temp_script = os.path.join(os.environ['TEMP'], "qforesteyes_setup.py")
            
            # Usamos r-strings para evitar problemas con las barras invertidas de Windows
            script_content = f'''import subprocess
    import sys
    import os

    print("=" * 60)
    print("CONFIGURACIÓN QFORESTEYES - Google Earth Engine")
    print("Detectado: {py_version}")
    print("=" * 60)
    print()

    # Limpieza radical del entorno para evitar conflictos con QGIS
    os.environ['PATH'] = r'C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem'
    env_vars_to_remove = ['QGIS_PREFIX_PATH', 'GDAL_DATA', 'PROJ_LIB', 'PYTHONPATH', 'PYTHONHOME']
    for var in env_vars_to_remove:
        if var in os.environ:
            del os.environ[var]

    print("1. Instalando earthengine-api...")
    # Usamos sys.executable porque este script ya correrá con el python correcto
    subprocess.run([sys.executable, "-m", "pip", "install", "earthengine-api", "--user"], check=False)

    print()
    print(f"2. Configurando proyecto: {project_id}")

    # Intentar ubicar el ejecutable earthengine recién instalado
    ee_exe = r"{earthengine_exe}"
    used_method = "Directo EXE"

    if os.path.exists(ee_exe):
        cmd = [ee_exe, "set_project", "{project_id}"]
    else:
        # Si no aparece el exe, usamos el modulo
        used_method = "Modulo Python"
        cmd = [sys.executable, "-m", "ee_official_cli", "set_project", "{project_id}"]

    print(f"   Método: {{used_method}}")
    try:
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode == 0:
            print("\\n[OK] ¡CONFIGURACIÓN EXITOSA!")
        else:
            # Fallback para versiones antiguas de la librería
            print("\\n[Info] Intentando método alternativo...")
            subprocess.run([sys.executable, "-m", "ee", "set_project", "{project_id}"], capture_output=False)
    except Exception as e:
        print(f"\\nError crítico: {{e}}")

    print("=" * 60)
    input("Presiona ENTER para cerrar...")
    '''
            
            with open(temp_script, "w", encoding="utf-8") as f:
                f.write(script_content)

            # --- 3. EJECUTAR ---
            try:
                CREATE_NEW_CONSOLE = 0x00000010
                subprocess.Popen(
                    [python_exe, temp_script],
                    creationflags=CREATE_NEW_CONSOLE,
                    close_fds=True,
                    cwd=os.environ['TEMP']
                )
            except Exception as e:
                QMessageBox.critical(None, "Error", f"Fallo al lanzar consola: {e}")