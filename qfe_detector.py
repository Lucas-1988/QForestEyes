# -*- coding: utf-8 -*-
"""
QFE Detector module for QForestEyes plugin
Detección de cambios forestales usando Google Earth Engine
"""

import sys
import os
import site
import subprocess
import calendar
import importlib
from datetime import datetime

# ==============================================================================
# BLOQUE DE CARGA INTELIGENTE (Solución para Equipos "Rebeldes")
# ==============================================================================
def ensure_ee_library():
    """Intenta importar EE, y si falla, inyecta las rutas de usuario al sistema."""
    try:
        import ee
        return ee
    except ImportError:
        try:
            # Estrategia agresiva de búsqueda de rutas
            paths_to_check = []
            
            # 1. Site packages del usuario
            user_site = site.getusersitepackages()
            if isinstance(user_site, list):
                paths_to_check.extend(user_site)
            else:
                paths_to_check.append(user_site)
            
            # 2. Rutas típicas de Windows si site no responde bien
            if os.name == 'nt':
                appdata = os.environ.get('APPDATA')
                if appdata:
                    # Python 3.9 a 3.13 (cobertura amplia)
                    for v in ['39', '310', '311', '312', '313']:
                        paths_to_check.append(os.path.join(appdata, 'Python', f'Python{v}', 'site-packages'))

            # Inyectar rutas
            for path in paths_to_check:
                if os.path.exists(path) and path not in sys.path:
                    sys.path.append(path)
            
            importlib.invalidate_caches()
            import ee
            return ee
        except Exception:
            return None

# Intentamos cargar ee globalmente ahora mismo
ee = ensure_ee_library()
# ==============================================================================


from qgis.core import (
    QgsGeometry, QgsWkbTypes, Qgis, QgsProject
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QMessageBox, QLineEdit, QDialog, QVBoxLayout, QFormLayout,
    QDialogButtonBox, QComboBox, QSpinBox, QWidget, QLabel
)
from qgis.utils import iface

# Umbrales por zona (configuración global)
ZONES_THRESHOLDS = {
    'Zone: Amazonic (Selva Densa)': {'loss_threshold': 0.08, 'gain_threshold': -0.10},
    'Zone: Subtropical (Yungas)': {'loss_threshold': 0.15, 'gain_threshold': -0.20},
    'Zone: Chaqueña': {'loss_threshold': 0.12, 'gain_threshold': -0.15},
    'Zone: Pampeana': {'loss_threshold': 0.10, 'gain_threshold': -0.10},
    'Zona: Mountainous': {'loss_threshold': 0.14, 'gain_threshold': -0.20},
    'Zone: Desert/Arid': {'loss_threshold': 0.08, 'gain_threshold': -0.05},
    'Zone: Atlantic Forest (Selva Paranaense)': {'loss_threshold': 0.18, 'gain_threshold': -0.25}
}

# Rangos estacionales
SEASONAL_RANGES = {
    '1. December - February': {'start_month': 12, 'end_month': 2},
    '2. March - May': {'start_month': 3, 'end_month': 5},
    '3. June - August': {'start_month': 6, 'end_month': 8},
    '4. September - November': {'start_month': 9, 'end_month': 11},
}


# === Instalación y autenticación ===
def install_and_authenticate():
    """Verifica si la API de GEE es visible para QGIS."""
    global ee 
    
    if ee is not None:
        return True

    ee = ensure_ee_library()
    if ee is not None:
        return True

    iface.messageBar().pushMessage(
        "Error de Librería", 
        "La librería 'earthengine-api' parece estar instalada pero QGIS no la detecta. "
        "Intenta reiniciar QGIS.",
        level=Qgis.Critical, duration=15
    )
    return False

def authenticate_gee(force=False):
    """Autentica al usuario en Google Earth Engine."""
    try:
        import ee
        try:
            ee.Initialize()
            iface.messageBar().pushMessage("GEE", "Sesión ya autenticada.", level=Qgis.Success, duration=5)
            return True
        except Exception:
            ee.Authenticate()
            ee.Initialize()
            iface.messageBar().pushMessage("GEE", "¡Autenticación exitosa!", level=Qgis.Success, duration=8)
            return True
    except Exception as auth_error:
        iface.messageBar().pushMessage("GEE", f"Autenticación fallida: {auth_error}", level=Qgis.Critical)
        return False


def initialize_gee(project_id):
    """Inicializa la API de Google Earth Engine con el proyecto específico."""
    try:
        import ee
        try:
            ee.Initialize(project=project_id)
            # Guardamos el proyecto exitoso como default para la próxima
            try:
                config_dir = os.path.join(os.path.expanduser("~"), '.config', 'earthengine')
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir)
                with open(os.path.join(config_dir, 'project'), 'w') as f:
                    f.write(project_id)
            except:
                pass 
        except Exception:
            # Fallback si falla el proyecto específico
            ee.Initialize()
            
        iface.messageBar().pushMessage("GEE", "GEE inicializado correctamente.", level=Qgis.Success)
        return True
    except Exception as e:
        iface.messageBar().pushMessage("GEE", f"Error al inicializar: {e}", level=Qgis.Critical)
        return False


# === Widget de selección de rangos ===
class RangeSelectWidget(QWidget):
    """Widget de configuración de años y rangos estacionales fijos."""
    
    def __init__(self, default_year=None, parent=None):
        super().__init__(parent)
        if default_year is None:
            default_year = datetime.now().year
        
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        
        layout = QVBoxLayout()
        formLayout = QFormLayout()
        
        MIN_YEAR = 2019
        default_t1 = max(MIN_YEAR, default_year - 2)
        
        # Año de referencia T1
        self.t1_year_spin = QSpinBox()
        self.t1_year_spin.setRange(MIN_YEAR, default_year)
        self.t1_year_spin.setValue(default_t1)
        formLayout.addRow("Año de Referencia T1 (BASE):", self.t1_year_spin)
        
        # Año de análisis T2
        self.t2_year_spin = QSpinBox()
        self.t2_year_spin.setRange(MIN_YEAR + 1, default_year)
        self.t2_year_spin.setValue(default_year - 1)
        formLayout.addRow("Año de Análisis T2 (ACTUAL):", self.t2_year_spin)
        
        # Selector estacional
        self.seasonal_combo = QComboBox()
        formLayout.addRow("Selecciona Rango Estacional:", self.seasonal_combo)
        
        layout.addLayout(formLayout)
        self.setLayout(layout)
        
        self.t2_year_spin.valueChanged.connect(self.update_seasonal_options)
        self.update_seasonal_options(self.t2_year_spin.value())
    
    def update_seasonal_options(self, selected_t2_year):
        self.seasonal_combo.clear()
        is_current_year = (selected_t2_year == self.current_year)
        
        for key, value in SEASONAL_RANGES.items():
            start_month = value['start_month']
            is_blocked = False
            
            if is_current_year:
                if start_month == 9 and self.current_month < 11:
                    is_blocked = True
                elif start_month == 11:
                    is_blocked = True
            
            display_text = key
            if is_blocked:
                display_text += " (No disponible)"
                self.seasonal_combo.addItem(display_text)
                self.seasonal_combo.setItemData(self.seasonal_combo.count() - 1, False, Qt.UserRole - 1)
            else:
                self.seasonal_combo.addItem(display_text)
    
    def validate_and_get_data(self):
        t1_year = self.t1_year_spin.value()
        t2_year = self.t2_year_spin.value()
        selected_key = self.seasonal_combo.currentText()
        
        if "(No disponible)" in selected_key:
            QMessageBox.warning(None, "Opción no disponible", "Rango estacional no disponible.")
            return None
        
        clean_key = selected_key.replace(" (No disponible)", "").strip()
        try:
            range_data = SEASONAL_RANGES[clean_key]
        except KeyError:
            return None
        
        if t1_year >= t2_year:
            QMessageBox.critical(None, "Error de Año", "El Año T2 debe ser posterior al Año T1.")
            return None
        
        return {
            't1_year': t1_year,
            't2_year': t2_year,
            'start_month': range_data['start_month'],
            'end_month': range_data['end_month']
        }
    
    @staticmethod
    def _get_date_string(year, month, is_end_date):
        if is_end_date:
            last_day = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{last_day:02d}"
        else:
            return f"{year:04d}-{month:02d}-01"
    
    def get_all_dates(self, data):
        y1_start, y2_start = data['t1_year'], data['t2_year']
        m_start, m_end = data['start_month'], data['end_month']
        year_adjust = 1 if m_start > m_end else 0
        y1_end = y1_start + year_adjust
        y2_end = y2_start + year_adjust
        
        if y2_start <= y1_end:
            QMessageBox.critical(None, "Error de Período", "T2 debe ser al menos un año después de T1.")
            return None
        
        return {
            't1_start': self._get_date_string(y1_start, m_start, is_end_date=False),
            't1_end': self._get_date_string(y1_end, m_end, is_end_date=True),
            't2_start': self._get_date_string(y2_start, m_start, is_end_date=False),
            't2_end': self._get_date_string(y2_end, m_end, is_end_date=True)
        }


# === CONFIGURACIÓN DE PARÁMETROS (CON AUTOCOMPLETADO ROBUSTO) ===
def get_user_parameters_with_zones():
    """Muestra el diálogo principal de configuración."""
    dialog = QDialog()
    dialog.setWindowTitle('Configuración Detección de Cambios (Delta NDVI)')
    layout = QVBoxLayout()
    formLayout = QFormLayout()
    
    # --- AUTOCOMPLETADO ROBUSTO ---
    default_project = ''
    
    # Lista de lugares donde buscar el archivo 'project'
    paths_to_check = []
    
    # 1. Ruta oficial de la librería (si está cargada)
    if ee is not None:
        try:
            paths_to_check.append(os.path.join(ee.data.get_config_dir(), 'project'))
        except:
            pass
            
    # 2. Rutas estándar de usuario (Fuerza Bruta)
    user_home = os.path.expanduser("~")
    paths_to_check.append(os.path.join(user_home, '.config', 'earthengine', 'project'))
    
    # Intentar leer
    for path in paths_to_check:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    content = f.read().strip()
                    if content:
                        # Limpiamos comillas que a veces quedan del .bat o JSON
                        clean_id = content.replace('"', '').replace("'", "")
                        if clean_id:
                            default_project = clean_id
                            break
            except:
                pass
    
    # Campo ID de Proyecto
    project_id_line = QLineEdit(default_project)
    project_id_line.setPlaceholderText("ej. mi-proyecto-gcloud-123")
    formLayout.addRow("ID de Proyecto de GEE:", project_id_line)
    
    zone_combo = QComboBox()
    zone_combo.addItems(ZONES_THRESHOLDS.keys())
    formLayout.addRow("Selecciona la Zona de Análisis:", zone_combo)
    
    layout.addLayout(formLayout)
    
    range_selector = RangeSelectWidget()
    layout.addWidget(range_selector)
    
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    
    dialog.setLayout(layout)
    
    if dialog.exec_() == QDialog.Accepted:
        range_data = range_selector.validate_and_get_data()
        if range_data is None: return None
        
        project_id_text = project_id_line.text().strip()
        if not project_id_text:
             QMessageBox.warning(None, "Falta ID", "Debes ingresar un Project ID válido.")
             return None

        selected_zone = zone_combo.currentText()
        umbrales = ZONES_THRESHOLDS.get(selected_zone)
        dates = range_selector.get_all_dates(range_data)
        
        if dates is None: return None
        
        return {
            'project_id': project_id_text,
            'umbrales': umbrales,
            'num_categories': 5,
            't1_start': dates['t1_start'],
            't1_end': dates['t1_end'],
            't2_start': dates['t2_start'],
            't2_end': dates['t2_end']
        }
    
    return None


# === Herramienta de dibujo ===
class GetExtentMapTool(QgsMapToolEmitPoint):
    finished = pyqtSignal(QgsGeometry)
    
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setWidth(3)
        self.rubberBand.setColor(QColor("#1ED760")) # Verde
        self.rubberBand.setFillColor(QColor(0, 0, 0, 0))
    
    def canvasPressEvent(self, e):
        point = self.toMapCoordinates(e.pos())
        self.points.append(point)
        if len(self.points) == 1:
            self.rubberBand.addPoint(point, False)
        else:
            self.rubberBand.addPoint(point, True)
        self.rubberBand.show()
    
    def canvasDoubleClickEvent(self, e):
        if len(self.points) > 2:
            self.rubberBand.addPoint(self.points[0], True)
            self.rubberBand.show()
            self.polygon = QgsGeometry.fromPolygonXY([self.points])
            self.finished.emit(self.polygon)
            self.deactivate()
    
    def deactivate(self):
        super().deactivate()
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        self.canvas.unsetMapTool(self)
        self.points = []


# === Diálogo informativo (CON LINK DINÁMICO) ===
class ProcessStartedDialog(QDialog):
    """Diálogo que muestra información y link directo al proyecto."""
    
    def __init__(self, project_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Proceso iniciado en Google Earth Engine")
        self.setFixedSize(500, 250)
        
        layout = QVBoxLayout()
        
        info_label = QLabel(
            "✅ ¡Área definida correctamente!\n\n"
            "El proceso de detección de cambios se está ejecutando en los servidores de Google.\n"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Construimos la URL con el ID del proyecto para ir directo
        # NOTA: ?project=ID selecciona el contexto del proyecto en la consola
        tasks_url = f"https://code.earthengine.google.com/tasks?project={project_id}"
        
        link_label = QLabel(
            f'<a href="{tasks_url}" style="color:#1a0dab;font-weight:bold;text-decoration:underline;font-size:12pt;">'
            '🔗 VER ESTADO DE LA TAREA (GEE Tasks)</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        link_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(link_label)
        
        layout.addWidget(QLabel("\n(Se abrirá tu navegador predeterminado)"))
        
        note_label = QLabel(
            "<i>💡 Nota: Una vez que la tarea en la web diga 'COMPLETED', "
            "descarga el raster de tu Google Drive y usa el botón 'Vectorizar Resultados'.</i>"
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #555; margin-top: 10px;")
        layout.addWidget(note_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
        
        self.setLayout(layout)


# === Funciones de procesamiento GEE ===
def get_ndvi_composite(start, end, polygon, collection_id, cloud_pct):
    import ee
    collection = (ee.ImageCollection(collection_id)
                  .filterDate(start, end)
                  .filterBounds(polygon)
                  .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_pct))
                  .map(lambda image: image.normalizedDifference(['B8', 'B4']).rename('NDVI'))
                  .select('NDVI'))
    
    collection_size = collection.size().getInfo()
    if collection_size == 0:
        return None, 0
    composite = collection.median()
    return composite, collection_size


# === Clase principal del detector ===
class QFEChangeDetector(QObject):
    """Clase principal que ejecuta la detección de cambios en GEE."""
    
    def __init__(self, project_id, umbrales, dates, num_categories, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.umbrales = umbrales
        self.dates = dates
        self.num_categories = num_categories
        
        self.map_tool = GetExtentMapTool(iface.mapCanvas())
        self.map_tool.finished.connect(self.run_gee_script)
        iface.mapCanvas().setMapTool(self.map_tool)
        
        iface.messageBar().pushMessage(
            "QForestEyes",
            "Dibuja el polígono (borde verde) y haz doble clic para ejecutar.",
            level=Qgis.Info, duration=8
        )
    
    def run_gee_script(self, polygon_geometry):
        # 1. Inicializar GEE
        if not initialize_gee(self.project_id):
            return
        
        import ee
        
        # 2. Obtener coordenadas
        coords_list = [[p.x(), p.y()] for p in self.map_tool.points]
        
        # 3. Obtener CRS
        qgis_crs_obj = iface.mapCanvas().mapSettings().destinationCrs()
        if qgis_crs_obj.isValid():
            epsg_code = qgis_crs_obj.postgisSrid()
            ee_crs = f'EPSG:{epsg_code}'
        else:
            ee_crs = 'EPSG:4326'
        
        ee_polygon = ee.Geometry.Polygon(coords_list, proj=ee_crs, geodesic=False)
        
        # 5. Parámetros
        cloud_percent = 30
        scale = 10
        collection_id = 'COPERNICUS/S2_SR_HARMONIZED'
        
        iface.messageBar().pushMessage("QForestEyes", "Procesando en la nube...", level=Qgis.Info, duration=5)
        
        # 6. Obtener NDVI
        ndvi_t1, size_t1 = get_ndvi_composite(
            self.dates['t1_start'], self.dates['t1_end'],
            ee_polygon, collection_id, cloud_percent
        )
        ndvi_t2, size_t2 = get_ndvi_composite(
            self.dates['t2_start'], self.dates['t2_end'],
            ee_polygon, collection_id, cloud_percent
        )
        
        if size_t1 == 0 or size_t2 == 0:
            iface.messageBar().pushMessage("Error", "No se encontraron imágenes en el periodo/zona.", level=Qgis.Critical)
            return
        
        # 8. Calcular Delta
        delta_ndvi = ndvi_t2.subtract(ndvi_t1).rename('Delta_NDVI')
        
        # 9. Clasificar
        loss_th = self.umbrales['loss_threshold']
        gain_th = self.umbrales['gain_threshold']
        
        classified_map = delta_ndvi.expression('3') # Sin cambios
        classified_map = classified_map.where(delta_ndvi.gt(gain_th).And(delta_ndvi.lte(gain_th/2)), 2)
        classified_map = classified_map.where(delta_ndvi.lt(gain_th), 1)
        classified_map = classified_map.where(delta_ndvi.lt(loss_th).And(delta_ndvi.gte(loss_th/2)), 4)
        classified_map = classified_map.where(delta_ndvi.gt(loss_th), 5)
        
        classified_map = classified_map.rename('Change_ID').toInt8()
        
        # 10. Exportar
        self.export_image(classified_map, self.dates['t2_start'], ee_polygon, scale)
        
        # 11. Mostrar Diálogo (Pasando el ID del Proyecto para el link)
        dialog = ProcessStartedDialog(self.project_id)
        dialog.exec_()
    
    def export_image(self, image, start_date, ee_polygon, scale):
        import ee
        try:
            prefix = f'QForestEyes_{self.num_categories}C_Change'
            task = ee.batch.Export.image.toDrive(
                image=image,
                description='QForestEyes_Change_Detection',
                folder='QForestEyes_Exports',
                fileNamePrefix=f'{prefix}_{start_date.replace("-", "")}',
                scale=scale,
                region=ee_polygon,
                maxPixels=1e13
            )
            task.start()
            iface.messageBar().pushMessage("GEE Tasks", "Tarea enviada exitosamente.", level=Qgis.Success)
        except Exception as e:
            iface.messageBar().pushMessage("Error Export", str(e), level=Qgis.Critical)