# -*- coding: utf-8 -*-
"""
Vectorizer module for QForestEyes plugin
Vectoriza rasters de cambio (valores 1-5) y reclasifica a 3 categorías con cálculo de hectáreas
"""

from qgis.PyQt.QtWidgets import (
    QFileDialog, QMessageBox, QInputDialog, QDialog, QVBoxLayout,
    QLabel, QProgressBar, QApplication
)
from qgis.PyQt.QtCore import Qt, QTimer, QVariant  # ✅ QVariant desde PyQt5.QtCore
from qgis.core import (
    QgsRasterLayer, QgsVectorLayer, QgsField, QgsFillSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsRasterBandStats,
    QgsProject, Qgis
)
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface
import os
import processing
from datetime import datetime


class ProgressDialog(QDialog):
    """Diálogo modal con barra de progreso indeterminada."""
    
    def __init__(self, parent=None, message="Procesando..."):
        super().__init__(parent)
        self.setWindowTitle("QForestEyes")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(350, 120)
        
        layout = QVBoxLayout()
        
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Modo indeterminado (barra animada)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        
        self.setLayout(layout)
    
    def show_and_force_render(self):
        """Muestra el diálogo y fuerza su renderizado completo."""
        self.show()
        self.raise_()
        self.activateWindow()
        
        # Forzar renderizado en 3 pasos
        for _ in range(3):
            QApplication.processEvents()
            QTimer.singleShot(50, lambda: None)
            QApplication.processEvents()


def run_vectorization():
    """
    Ejecuta el flujo completo de vectorización y reclasificación.
    Muestra diálogo de progreso durante operaciones pesadas.
    """
    try:
        # 1. Seleccionar raster
        raster_path, _ = QFileDialog.getOpenFileName(
            None,
            "Seleccionar archivo raster",
            "",
            "Raster (*.tif *.img *.vrt)"
        )
        if not raster_path:
            iface.messageBar().pushMessage(
                "QForestEyes", "Vectorización cancelada por el usuario",
                level=Qgis.Warning, duration=5
            )
            return

        # 2. Cargar raster sin añadirlo al proyecto
        raster_layer = QgsRasterLayer(raster_path, "raster_temp", "gdal")
        if not raster_layer.isValid():
            QMessageBox.critical(None, "Error", "No se pudo cargar el raster.")
            return

        # 3. Analizar valores únicos del raster (muestreo rápido)
        stats = raster_layer.dataProvider().bandStatistics(1, QgsRasterBandStats.All)
        min_val, max_val = stats.minimumValue, stats.maximumValue

        if max_val <= 0:
            QMessageBox.critical(
                None,
                "Error",
                f"El raster parece no tener valores válidos. Rango detectado: {min_val} - {max_val}"
            )
            return

        # 4. Preguntar al usuario qué tipo de SALIDA quiere
        tipo, ok = QInputDialog.getItem(
            None,
            "Categorías a mostrar",
            "Seleccione una opción de visualización:",
            ["Pérdida", "Sin cambios", "Ganancia", "Tres categorías (1-3)"],
            0,
            False
        )
        if not ok:
            iface.messageBar().pushMessage(
                "QForestEyes", "Vectorización cancelada por el usuario",
                level=Qgis.Warning, duration=5
            )
            return

        # 5. MOSTRAR DIÁLOGO DE PROGRESO (¡CON RENDERIZADO FORZADO!)
        progress_dialog = ProgressDialog(
            iface.mainWindow(),
            "Vectorizando raster...\nPor favor, espera mientras se procesan los datos."
        )
        progress_dialog.show_and_force_render()

        try:
            # 6. Vectorizar el raster ORIGINAL para obtener los valores 1-5 como atributos
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_dir = os.path.dirname(raster_path)
            base_name = "resultado_vectorizado_" + tipo.replace(" ", "_")
            output_path = os.path.join(base_dir, f"{base_name}_{timestamp}.shp")

            params = {
                'INPUT': raster_layer,
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'OUTPUT': output_path
            }

            # OPERACIÓN PESADA: gdal:polygonize
            QApplication.processEvents()
            result = processing.run("gdal:polygonize", params)
            vector = QgsVectorLayer(result['OUTPUT'], f"Clasificación {tipo}", "ogr")

            if not vector.isValid() or vector.featureCount() == 0:
                QMessageBox.warning(None, "Sin entidades", "El raster no generó polígonos válidos.")
                try:
                    os.remove(output_path)
                except:
                    pass
                progress_dialog.accept()
                return

            # 7. Agregar columnas
            vector.startEditing()  # ✅ SIN ESPACIO
            vector.dataProvider().addAttributes([
                QgsField("Sup_has", QVariant.Double),  # Superficie en hectáreas
                QgsField("Tipo", QVariant.String),     # Tipo de categoría
                QgsField("categoria", QVariant.Int)    # Categoría numérica reclasificada
            ])
            vector.updateFields()

            # 8. Calcular valores, RECLASIFICAR y calcular área
            orig_idx = 0  # Índice del campo de valor original (1-5) creado por gdal:polygonize

            for f in vector.getFeatures():
                # Obtener valor original y convertir a entero
                orig_val = f[orig_idx]
                try:
                    orig_val = int(orig_val)
                except (TypeError, ValueError):
                    orig_val = 0  # Manejar NULL/NoData

                # Reclasificación vectorial
                if orig_val in (1, 2):
                    reclas_val = 1
                    tipo_str = "Pérdida"
                elif orig_val == 3:
                    reclas_val = 2
                    tipo_str = "Sin cambios"
                elif orig_val in (4, 5):
                    reclas_val = 3
                    tipo_str = "Ganancia"
                else:
                    reclas_val = 0
                    tipo_str = "No clasificado"

                # Asignar nuevos valores
                f['categoria'] = reclas_val
                f['Tipo'] = tipo_str
                f['Sup_has'] = f.geometry().area() / 10000.0  # Convertir m² a hectáreas

                vector.updateFeature(f)

            vector.commitChanges()

            # 9. Aplicar estilo condicional
            OPACIDAD = 178
            TRANSPARENTE = 0
            color_perdida = f'220,16,16,{OPACIDAD}'        # Rojo (70% opaco)
            color_ganancia = f'51,160,44,{OPACIDAD}'       # Verde (70% opaco)
            color_sin_cambios_vis = f'255,251,1,{OPACIDAD}' # Amarillo claro (70% opaco)
            color_transparente = f'255,255,255,{TRANSPARENTE}' # Transparente

            # Inicializar símbolos con transparencia total
            sym_perdida = QgsFillSymbol.createSimple({'color': color_transparente, 'outline_color': color_transparente})
            sym_sin_cambios = QgsFillSymbol.createSimple({'color': color_transparente, 'outline_color': color_transparente})
            sym_ganancia = QgsFillSymbol.createSimple({'color': color_transparente, 'outline_color': color_transparente})

            # Aplicar lógica condicional según selección del usuario
            if tipo == "Pérdida":
                sym_perdida = QgsFillSymbol.createSimple({'color': color_perdida, 'outline_color': color_perdida})
            elif tipo == "Sin cambios":
                sym_sin_cambios = QgsFillSymbol.createSimple({'color': color_sin_cambios_vis, 'outline_color': color_transparente})
            elif tipo == "Ganancia":
                sym_ganancia = QgsFillSymbol.createSimple({'color': color_ganancia, 'outline_color': color_ganancia})
            else:  # "Tres categorías (1-3)"
                sym_perdida = QgsFillSymbol.createSimple({'color': color_perdida, 'outline_color': color_perdida})
                sym_sin_cambios = QgsFillSymbol.createSimple({'color': color_sin_cambios_vis, 'outline_color': color_transparente})
                sym_ganancia = QgsFillSymbol.createSimple({'color': color_ganancia, 'outline_color': color_ganancia})

            # Aplicar renderizador categorizado
            renderer = QgsCategorizedSymbolRenderer('categoria', [
                QgsRendererCategory(1, sym_perdida, 'Pérdida'),
                QgsRendererCategory(2, sym_sin_cambios, 'Sin cambios'),
                QgsRendererCategory(3, sym_ganancia, 'Ganancia')
            ])
            vector.setRenderer(renderer)
            vector.triggerRepaint()

            # 10. Añadir capa al proyecto
            QgsProject.instance().addMapLayer(vector)

            # ✅ CERRAR DIÁLOGO DE PROGRESO
            progress_dialog.accept()

            iface.messageBar().pushMessage(
                "QForestEyes",
                f"✓ Vectorización completada: {vector.featureCount()} polígonos creados",
                level=Qgis.Success,
                duration=8
            )

        except Exception as e:
            # Siempre cerrar diálogo antes de mostrar error
            progress_dialog.accept()
            QApplication.processEvents()
            raise e

    except Exception as e:
        QMessageBox.critical(None, "Error en vectorización", f"Ocurrió un error:\n{str(e)}")
        import traceback
        from qgis.core import QgsApplication
        QgsApplication.instance().messageLog().logMessage(
            f"QForestEyes vectorization error:\n{traceback.format_exc()}",
            "QForestEyes",
            Qgis.Critical
        )