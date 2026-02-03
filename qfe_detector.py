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
# BLOQUE DE CARGA INTELIGENTE
# ==============================================================================
def ensure_ee_library():
    """Intenta importar EE, y si falla, inyecta las rutas de usuario al sistema."""
    try:
        import ee
        return ee
    except ImportError:
        try:
            paths_to_check = []
            user_site = site.getusersitepackages()
            if isinstance(user_site, list):
                paths_to_check.extend(user_site)
            else:
                paths_to_check.append(user_site)
            
            if os.name == 'nt':
                appdata = os.environ.get('APPDATA')
                if appdata:
                    for v in ['39', '310', '311', '312', '313']:
                        paths_to_check.append(os.path.join(appdata, 'Python', f'Python{v}', 'site-packages'))

            for path in paths_to_check:
                if os.path.exists(path) and path not in sys.path:
                    sys.path.append(path)
            
            importlib.invalidate_caches()
            import ee
            return ee
        except Exception:
            return None

ee = ensure_ee_library()
# ==============================================================================


from qgis.core import (
    QgsGeometry, QgsWkbTypes, Qgis, QgsProject, QgsSettings
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QMessageBox, QLineEdit, QDialog, QVBoxLayout, QFormLayout,
    QDialogButtonBox, QComboBox, QSpinBox, QWidget, QLabel
)
from qgis.utils import iface

# Umbrales por zona
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
    global ee 
    if ee is not None: return True
    ee = ensure_ee_library()
    if ee is not None: return True
    iface.messageBar().pushMessage("Error", "Librería 'earthengine-api' no detectada. Reinicia QGIS.", level=Qgis.Critical)
    return False

def authenticate_gee(force=False):
    try:
        import ee
        try:
            ee.Initialize()
            iface.messageBar().pushMessage("GEE", "Sesión ya autenticada.", level=Qgis.Success)
            return True
        except Exception:
            ee.Authenticate()
            ee.Initialize()
            iface.messageBar().pushMessage("GEE", "¡Autenticación exitosa!", level=Qgis.Success)
            return True
    except Exception as e:
        iface.messageBar().pushMessage("GEE", f"Fallo autenticación: {e}", level=Qgis.Critical)
        return False


def initialize_gee(project_id):
    """Inicializa GEE y GUARDA la ID en la memoria de QGIS si funciona."""
    try:
        import ee
        try:
            ee.Initialize(project=project_id)
            
            # --- PERSISTENCIA EN QGIS SETTINGS (LA CLAVE DEL ÉXITO) ---
            # Si la inicialización funciona, guardamos esta ID para siempre
            settings = QgsSettings()
            settings.setValue("QForestEyes/project_id", project_id)
            # ----------------------------------------------------------
            
        except Exception:
            ee.Initialize()
            
        iface.messageBar().pushMessage("GEE", "GEE inicializado correctamente.", level=Qgis.Success)
        return True
    except Exception as e:
        iface.messageBar().pushMessage("GEE", f"Error al inicializar: {e}", level=Qgis.Critical)
        return False


# === Widget de rangos ===
class RangeSelectWidget(QWidget):
    def __init__(self, default_year=None, parent=None):
        super().__init__(parent)
        if default_year is None: default_year = datetime.now().year
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        
        layout = QVBoxLayout()
        formLayout = QFormLayout()
        
        MIN_YEAR = 2019
        default_t1 = max(MIN_YEAR, default_year - 2)
        
        self.t1_year_spin = QSpinBox()
        self.t1_year_spin.setRange(MIN_YEAR, default_year)
        self.t1_year_spin.setValue(default_t1)
        formLayout.addRow("Año de Referencia T1 (BASE):", self.t1_year_spin)
        
        self.t2_year_spin = QSpinBox()
        self.t2_year_spin.setRange(MIN_YEAR + 1, default_year)
        self.t2_year_spin.setValue(default_year - 1)
        formLayout.addRow("Año de Análisis T2 (ACTUAL):", self.t2_year_spin)
        
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
                if start_month == 9 and self.current_month < 11: is_blocked = True
                elif start_month == 11: is_blocked = True
            
            display_text = key + (" (No disponible)" if is_blocked else "")
            self.seasonal_combo.addItem(display_text)
            if is_blocked:
                self.seasonal_combo.setItemData(self.seasonal_combo.count()-1, False, Qt.UserRole-1)
    
    def validate_and_get_data(self):
        t1 = self.t1_year_spin.value()
        t2 = self.t2_year_spin.value()
        key = self.seasonal_combo.currentText()
        if "(No disponible)" in key:
            QMessageBox.warning(None, "Error", "Rango no disponible.")
            return None
        clean = key.replace(" (No disponible)", "").strip()
        try: data = SEASONAL_RANGES[clean]
        except: return None
        if t1 >= t2:
            QMessageBox.critical(None, "Error", "T2 debe ser mayor que T1.")
            return None
        return {'t1_year': t1, 't2_year': t2, 'start_month': data['start_month'], 'end_month': data['end_month']}
    
    @staticmethod
    def _get_date_string(year, month, is_end):
        last = calendar.monthrange(year, month)[1] if is_end else 1
        return f"{year:04d}-{month:02d}-{last:02d}"
    
    def get_all_dates(self, data):
        y1, y2 = data['t1_year'], data['t2_year']
        m_s, m_e = data['start_month'], data['end_month']
        adj = 1 if m_s > m_e else 0
        if y2 <= (y1 + adj):
             QMessageBox.critical(None, "Error", "Periodo inválido.")
             return None
        return {
            't1_start': self._get_date_string(y1, m_s, False), 't1_end': self._get_date_string(y1+adj, m_e, True),
            't2_start': self._get_date_string(y2, m_s, False), 't2_end': self._get_date_string(y2+adj, m_e, True)
        }


# === CONFIGURACIÓN DE PARÁMETROS (USANDO QgsSettings) ===
def get_user_parameters_with_zones():
    dialog = QDialog()
    dialog.setWindowTitle('Configuración Detección de Cambios')
    layout = QVBoxLayout()
    formLayout = QFormLayout()
    
    # 1. Intentar recuperar desde QGIS Settings (Prioridad Máxima)
    settings = QgsSettings()
    default_project = settings.value("QForestEyes/project_id", "")
    
    # 2. Si no hay nada en QGIS, buscar en archivos del sistema (Fallback)
    if not default_project:
        paths = []
        if ee:
            try: paths.append(os.path.join(ee.data.get_config_dir(), 'project'))
            except: pass
        paths.append(os.path.join(os.path.expanduser("~"), '.config', 'earthengine', 'project'))
        
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, 'r') as f:
                        clean = f.read().strip().replace('"','').replace("'", "")
                        if clean:
                            default_project = clean
                            break
                except: pass
    
    project_id_line = QLineEdit(str(default_project)) # Asegurar string
    project_id_line.setPlaceholderText("ej. mi-proyecto-gcloud-123")
    formLayout.addRow("ID de Proyecto de GEE:", project_id_line)
    
    zone_combo = QComboBox()
    zone_combo.addItems(ZONES_THRESHOLDS.keys())
    formLayout.addRow("Zona:", zone_combo)
    
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
        if not range_data: return None
        pid = project_id_line.text().strip()
        if not pid:
             QMessageBox.warning(None, "Falta ID", "Ingresa un ID válido.")
             return None
        
        dates = range_selector.get_all_dates(range_data)
        if not dates: return None
        
        return {
            'project_id': pid,
            'umbrales': ZONES_THRESHOLDS.get(zone_combo.currentText()),
            'num_categories': 5,
            **dates
        }
    return None


# === Herramienta de dibujo ===
class GetExtentMapTool(QgsMapToolEmitPoint):
    finished = pyqtSignal(QgsGeometry)
    def __init__(self, canvas):
        super().__init__(canvas)
        self.points = []
        self.rubberBand = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setWidth(3)
        self.rubberBand.setColor(QColor("#1ED760"))
        self.rubberBand.setFillColor(QColor(0, 0, 0, 0))
    
    def canvasPressEvent(self, e):
        p = self.toMapCoordinates(e.pos())
        self.points.append(p)
        self.rubberBand.addPoint(p, len(self.points) > 1)
        self.rubberBand.show()
    
    def canvasDoubleClickEvent(self, e):
        if len(self.points) > 2:
            self.rubberBand.addPoint(self.points[0], True)
            self.polygon = QgsGeometry.fromPolygonXY([self.points])
            self.finished.emit(self.polygon)
            self.deactivate()
    
    def deactivate(self):
        super().deactivate()
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        self.points = []
        iface.mapCanvas().unsetMapTool(self)


# === Diálogo Final ===
class ProcessStartedDialog(QDialog):
    def __init__(self, project_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proceso Iniciado")
        self.setFixedSize(500, 200)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("✅ Proceso ejecutándose en Google Earth Engine."))
        
        url = f"https://code.earthengine.google.com/tasks?project={project_id}"
        link = QLabel(f'<a href="{url}" style="color:#1a0dab;font-weight:bold;text-decoration:underline;font-size:12pt;" >🔗 VER ESTADO DE LA TAREA</a>')
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        layout.addWidget(link)
        
        layout.addWidget(QLabel("<i>Descarga el raster de Drive cuando termine.</i>"))
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)
        self.setLayout(layout)


# === Lógica GEE ===
def get_ndvi_composite(start, end, polygon, collection_id, cloud_pct):
    import ee
    col = (ee.ImageCollection(collection_id).filterDate(start, end)
           .filterBounds(polygon).filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_pct))
           .map(lambda i: i.normalizedDifference(['B8', 'B4']).rename('NDVI')).select('NDVI'))
    if col.size().getInfo() == 0: return None, 0
    return col.median(), col.size().getInfo()

class QFEChangeDetector(QObject):
    def __init__(self, project_id, umbrales, dates, num_categories, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.umbrales = umbrales
        self.dates = dates
        self.num_categories = num_categories
        self.map_tool = GetExtentMapTool(iface.mapCanvas())
        self.map_tool.finished.connect(self.run_gee)
        iface.mapCanvas().setMapTool(self.map_tool)
        iface.messageBar().pushMessage("QForestEyes", "Dibuja el área.", level=Qgis.Info)
    
    def run_gee(self, poly):
        if not initialize_gee(self.project_id): return
        import ee
        coords = [[p.x(), p.y()] for p in self.map_tool.points]
        crs = iface.mapCanvas().mapSettings().destinationCrs()
        ee_crs = f'EPSG:{crs.postgisSrid()}' if crs.isValid() else 'EPSG:4326'
        ee_poly = ee.Geometry.Polygon(coords, proj=ee_crs, geodesic=False)
        
        iface.messageBar().pushMessage("Info", "Calculando...", level=Qgis.Info)
        
        n1, s1 = get_ndvi_composite(self.dates['t1_start'], self.dates['t1_end'], ee_poly, 'COPERNICUS/S2_SR_HARMONIZED', 30)
        n2, s2 = get_ndvi_composite(self.dates['t2_start'], self.dates['t2_end'], ee_poly, 'COPERNICUS/S2_SR_HARMONIZED', 30)
        
        if s1 == 0 or s2 == 0:
            iface.messageBar().pushMessage("Error", "Sin imágenes.", level=Qgis.Critical)
            return
            
        delta = n2.subtract(n1).rename('Delta_NDVI')
        l_th, g_th = self.umbrales['loss_threshold'], self.umbrales['gain_threshold']
        
        res = delta.expression('3')
        res = res.where(delta.gt(g_th).And(delta.lte(g_th/2)), 2)
        res = res.where(delta.lt(g_th), 1)
        res = res.where(delta.lt(l_th).And(delta.gte(l_th/2)), 4)
        res = res.where(delta.gt(l_th), 5)
        
        prefix = f'QForestEyes_{self.num_categories}C'
        task = ee.batch.Export.image.toDrive(image=res.toInt8(), description='QForestEyes_Change', folder='QForestEyes_Exports',
                                             fileNamePrefix=f'{prefix}_{self.dates["t2_start"].replace("-","")}', scale=10, region=ee_poly, maxPixels=1e13)
        task.start()
        
        ProcessStartedDialog(self.project_id).exec_()