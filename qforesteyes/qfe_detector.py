# -*- coding: utf-8 -*-
"""
QFE Detector module for QForestEyes plugin
Detección de cambios forestales usando Google Earth Engine
"""

import subprocess
import sys
import os
import calendar
from datetime import datetime

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

# Rangos estacionales para uso interno
SEASONAL_RANGES = {
    '1. December - February': {'start_month': 12, 'end_month': 2},
    '2. March - May': {'start_month': 3, 'end_month': 5},
    '3. June - August': {'start_month': 6, 'end_month': 8},
    '4. September - November': {'start_month': 9, 'end_month': 11},
}


# === Instalación y autenticación ===
def install_and_authenticate():
    """Verifica e instala la API de GEE y realiza la autenticación."""
    try:
        import ee
        return True
    except ImportError:
        try:
            # Instalar earthengine-api SIN espacios extra en los argumentos
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "earthengine-api"
            ])
            import ee
            return True
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error al instalar 'earthengine-api': {e}",
                level=Qgis.Critical
            )
            return False


def authenticate_gee(force=False):
    """Autentica al usuario en Google Earth Engine (abre navegador automáticamente)."""
    try:
        import ee
        ee.Initialize()
        iface.messageBar().pushMessage(
            "GEE", "Sesión de Google Earth Engine ya autenticada.",
            level=Qgis.Success, duration=5
        )
        return True
    except Exception:
        try:
            import ee
            ee.Authenticate()  # ← Abre navegador automáticamente
            ee.Initialize()
            iface.messageBar().pushMessage(
                "GEE", "¡Autenticación exitosa! Ya puedes usar QForestEyes.",
                level=Qgis.Success, duration=8
            )
            return True
        except Exception as auth_error:
            iface.messageBar().pushMessage(
                "GEE", f"Autenticación fallida: {auth_error}",
                level=Qgis.Critical, duration=10
            )
            return False


def initialize_gee(project_id):
    """Inicializa la API de Google Earth Engine."""
    try:
        import ee
        ee.Initialize(project=project_id)
        iface.messageBar().pushMessage(
            "GEE", "Google Earth Engine se ha inicializado correctamente.",
            level=Qgis.Success
        )
        return True
    except Exception as e:
        iface.messageBar().pushMessage(
            "GEE", f"Error al inicializar GEE: {e}",
            level=Qgis.Critical
        )
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
        """Actualiza las opciones del ComboBox estacional."""
        self.seasonal_combo.clear()
        is_current_year = (selected_t2_year == self.current_year)
        
        for key, value in SEASONAL_RANGES.items():
            start_month = value['start_month']
            end_month = value['end_month']
            is_blocked = False
            
            if is_current_year:
                # Bloquear rangos no concluidos en año actual
                if start_month == 9 and self.current_month < 11:
                    is_blocked = True
                elif start_month == 11:
                    is_blocked = True
            
            display_text = key
            if is_blocked:
                display_text += " (No disponible)"
                self.seasonal_combo.addItem(display_text)
                self.seasonal_combo.setItemData(
                    self.seasonal_combo.count() - 1,
                    False,
                    Qt.UserRole - 1
                )
            else:
                self.seasonal_combo.addItem(display_text)
    
    def validate_and_get_data(self):
        """Valida que los años sean cronológicos y retorna los datos."""
        t1_year = self.t1_year_spin.value()
        t2_year = self.t2_year_spin.value()
        selected_key = self.seasonal_combo.currentText()
        
        # Limpiar texto de bloqueo
        if "(No disponible)" in selected_key:
            QMessageBox.warning(
                None, "Opción no disponible",
                "Esa opción estacional aún no está disponible para el año actual."
            )
            return None
        
        clean_key = selected_key.replace(" (No disponible)", "").strip()
        
        try:
            range_data = SEASONAL_RANGES[clean_key]
        except KeyError:
            QMessageBox.critical(None, "Error de Selección", "Rango estacional no válido.")
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
        """Genera string de fecha en formato ISO."""
        if is_end_date:
            last_day = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{last_day:02d}"
        else:
            return f"{year:04d}-{month:02d}-01"
    
    def get_all_dates(self, data):
        """Calcula fechas completas para T1 y T2."""
        y1_start, y2_start = data['t1_year'], data['t2_year']
        m_start, m_end = data['start_month'], data['end_month']
        
        year_adjust = 1 if m_start > m_end else 0
        y1_end = y1_start + year_adjust
        y2_end = y2_start + year_adjust
        
        if y2_start <= y1_end:
            QMessageBox.critical(
                None, "Error de Período",
                "El Año T2 debe ser al menos un año después del Año T1."
            )
            return None
        
        return {
            't1_start': self._get_date_string(y1_start, m_start, is_end_date=False),
            't1_end': self._get_date_string(y1_end, m_end, is_end_date=True),
            't2_start': self._get_date_string(y2_start, m_start, is_end_date=False),
            't2_end': self._get_date_string(y2_end, m_end, is_end_date=True)
        }


def get_user_parameters_with_zones():
    """Muestra el diálogo principal de configuración."""
    dialog = QDialog()
    dialog.setWindowTitle('Configuración Detección de Cambios (Delta NDVI)')
    layout = QVBoxLayout()
    formLayout = QFormLayout()
    
    # Parámetros generales
    project_id_line = QLineEdit('tu-id-de-proyecto')
    formLayout.addRow("ID de Proyecto de GEE:", project_id_line)
    
    zone_combo = QComboBox()
    zone_combo.addItems(ZONES_THRESHOLDS.keys())
    formLayout.addRow("Selecciona la Zona de Análisis:", zone_combo)
    
    layout.addLayout(formLayout)
    
    # Selector de rangos
    range_selector = RangeSelectWidget()
    layout.addWidget(range_selector)
    
    # Botones
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    
    dialog.setLayout(layout)
    
    if dialog.exec_() == QDialog.Accepted:
        range_data = range_selector.validate_and_get_data()
        if range_data is None:
            return None
        
        selected_zone = zone_combo.currentText()
        umbrales = ZONES_THRESHOLDS.get(selected_zone)
        
        num_categories = 5
        dates = range_selector.get_all_dates(range_data)
        
        if dates is None:
            return None
        
        return {
            'project_id': project_id_line.text() or 'tu-id-de-proyecto',
            'umbrales': umbrales,
            'num_categories': num_categories,
            't1_start': dates['t1_start'],
            't1_end': dates['t1_end'],
            't2_start': dates['t2_start'],
            't2_end': dates['t2_end']
        }
    
    return None


# === Herramienta de dibujo MEJORADA (borde verde sin relleno) ===
class GetExtentMapTool(QgsMapToolEmitPoint):
    """Herramienta para dibujar polígonos en el canvas con estilo verde sin relleno."""
    finished = pyqtSignal(QgsGeometry)
    
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        
        # Rubber band con borde verde (#1ED760) y SIN relleno
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setWidth(3)  # Borde más visible
        
        # Color de borde verde Spotify (#1ED760)
        self.rubberBand.setColor(QColor("#1ED760"))
        
        # Relleno TRANSPARENTE (0% opacidad)
        self.rubberBand.setFillColor(QColor(0, 0, 0, 0))  # Negro con 0% alpha = transparente
    
    def canvasPressEvent(self, e):
        point = self.toMapCoordinates(e.pos())
        self.points.append(point)
        
        # ✅ MOSTRAR POLÍGONO DESDE EL SEGUNDO PUNTO
        if len(self.points) == 1:
            self.rubberBand.addPoint(point, False)  # Primer punto: no actualizar visualmente
        else:
            self.rubberBand.addPoint(point, True)   # Segundo punto+: actualizar y mostrar polígono
        
        self.rubberBand.show()
    
    def canvasDoubleClickEvent(self, e):
        if len(self.points) > 2:
            # Cerrar el polígono con el primer punto
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


# === Diálogo informativo después del dibujo (CORREGIDO) ===
class ProcessStartedDialog(QDialog):
    """Diálogo que muestra información sobre el proceso iniciado en GEE."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Proceso iniciado en Google Earth Engine")
        self.setFixedSize(480, 230)
        
        layout = QVBoxLayout()
        
        # Icono/información
        info_label = QLabel(
            "✅ ¡Área definida correctamente!\n\n"
            "El proceso de detección de cambios se está ejecutando en Google Earth Engine.\n\n"
            "⏱️ Tiempo estimado: 2-5 minutos (dependiendo del tamaño del área)"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Enlace a Tasks (CORREGIDO: sin espacios que rompen la URL)
        link_label = QLabel(
            '<a href="https://code.earthengine.google.com/tasks" style="color:#1a0dab;font-weight:bold;text-decoration:underline;">'
            'https://code.earthengine.google.com/tasks</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        link_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(QLabel("🔗 Sigue el progreso aquí:"))
        layout.addWidget(link_label)
        
        # Nota importante
        note_label = QLabel(
            "<i>💡 Nota: Una vez completada la tarea, descarga el raster desde Google Drive "
            "y usa el botón 'Vectorizar Resultados' para procesarlo en QGIS.</i>"
        )
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        
        # Botón Cerrar (simple, SIN temporizador)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        # ✅ SIN temporizador → el diálogo permanece visible hasta que el usuario haga clic en "OK"


# === Funciones de procesamiento GEE ===
def get_ndvi_composite(start, end, polygon, collection_id, cloud_pct):
    """Calcula la mediana del NDVI para un periodo."""
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
        
        # Inicializar herramienta de dibujo MEJORADA
        self.map_tool = GetExtentMapTool(iface.mapCanvas())
        self.map_tool.finished.connect(self.run_gee_script)
        iface.mapCanvas().setMapTool(self.map_tool)
        
        iface.messageBar().pushMessage(
            "Dibujo",
            "Dibuja el polígono de tu área de interés (borde verde) y haz doble clic para comenzar el análisis.",
            level=Qgis.Info,
            duration=12
        )
    
    def run_gee_script(self, polygon_geometry):
        """Ejecuta el flujo completo de detección de cambios."""
        # 1. Inicializar GEE
        if not initialize_gee(self.project_id):
            return
        
        import ee
        
        # 2. Obtener coordenadas del polígono dibujado
        coords_list = [[p.x(), p.y()] for p in self.map_tool.points]
        
        # 3. Obtener CRS del canvas
        qgis_crs_obj = iface.mapCanvas().mapSettings().destinationCrs()
        if qgis_crs_obj.isValid():
            epsg_code = qgis_crs_obj.postgisSrid()
            ee_crs = f'EPSG:{epsg_code}'
        else:
            ee_crs = 'EPSG:4326'
        
        iface.messageBar().pushMessage(
            "CRS", f"Usando CRS: {ee_crs} para GEE.",
            level=Qgis.Info,
            duration=5
        )
        
        # 4. Construir geometría de Earth Engine
        ee_polygon = ee.Geometry.Polygon(coords_list, proj=ee_crs, geodesic=False)
        
        # 5. Parámetros de procesamiento
        cloud_percent = 30
        scale = 10
        collection_id = 'COPERNICUS/S2_SR_HARMONIZED'
        
        iface.messageBar().pushMessage(
            "Cálculo", "Calculando compuestos de NDVI para T1 y T2...",
            level=Qgis.Info,
            duration=8
        )
        
        # 6. Obtener NDVI para T1 y T2
        ndvi_t1, size_t1 = get_ndvi_composite(
            self.dates['t1_start'], self.dates['t1_end'],
            ee_polygon, collection_id, cloud_percent
        )
        
        ndvi_t2, size_t2 = get_ndvi_composite(
            self.dates['t2_start'], self.dates['t2_end'],
            ee_polygon, collection_id, cloud_percent
        )
        
        # 7. Validar disponibilidad de imágenes
        if size_t1 == 0 or size_t2 == 0:
            msg = (f"No hay imágenes de Sentinel-2 para el área/periodo seleccionado. "
                   f"(T1: {size_t1} imágenes, T2: {size_t2} imágenes). "
                   f"Intenta expandir las fechas o reducir el filtro de nubes.")
            iface.messageBar().pushMessage("Error", msg, level=Qgis.Critical, duration=15)
            return
        
        # 8. Calcular Delta NDVI
        delta_ndvi = ndvi_t2.subtract(ndvi_t1).rename('Delta_NDVI')
        
        # 9. Aplicar umbrales zonales (5 clases)
        loss_threshold_abs = self.umbrales['loss_threshold']
        gain_threshold_abs = self.umbrales['gain_threshold']
        loss_light_threshold_abs = loss_threshold_abs / 2.0
        gain_light_threshold_abs = gain_threshold_abs / 2.0
        
        # Clase base: "Sin cambios" (valor 3)
        classified_map = delta_ndvi.expression('3')
        
        # Pérdida leve (valor 2)
        classified_map = classified_map.where(
            delta_ndvi.gt(gain_threshold_abs).And(
                delta_ndvi.lte(gain_light_threshold_abs)
            ),
            2
        )
        
        # Pérdida severa (valor 1)
        classified_map = classified_map.where(
            delta_ndvi.lt(gain_threshold_abs),
            1
        )
        
        # Ganancia leve (valor 4)
        classified_map = classified_map.where(
            delta_ndvi.lt(loss_threshold_abs).And(
                delta_ndvi.gte(loss_light_threshold_abs)
            ),
            4
        )
        
        # Ganancia severa (valor 5)
        classified_map = classified_map.where(
            delta_ndvi.gt(loss_threshold_abs),
            5
        )
        
        classified_map = classified_map.rename('Change_ID').toInt8()
        
        iface.messageBar().pushMessage(
            "Éxito",
            f"Detección de cambios ({self.num_categories} clases) completada. Exportando...",
            level=Qgis.Success,
            duration=8
        )
        
        # 10. ✅ EXPORTAR A GOOGLE DRIVE (INICIA LA TAREA EN BACKGROUND)
        self.export_image(classified_map, self.dates['t2_start'], ee_polygon, scale)
        
        # 11. ✅ MOSTRAR DIÁLOGO INFORMATIVO DESPUÉS DE INICIAR LA TAREA
        # Usa exec_() para que sea modal y permanezca visible hasta que el usuario haga clic en "OK"
        dialog = ProcessStartedDialog()
        dialog.exec_()  # ← exec_() bloquea hasta que el usuario cierre el diálogo
    
    def export_image(self, image, start_date, ee_polygon, scale):
        """Exporta la imagen clasificada a Google Drive."""
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
            task.start()  # ← ¡LA TAREA SE INICIA INMEDIATAMENTE AQUÍ!
            
            iface.messageBar().pushMessage(
                "Exportación",
                "✅ Tarea iniciada en GEE. Revisa el estado en Tasks.",
                level=Qgis.Success,
                duration=10
            )
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error al exportar: {str(e)}",
                level=Qgis.Critical,
                duration=10
            )