# -*- coding: utf-8 -*-
"""
Vectorizer module for QForestEyes plugin
Vectoriza rasters de cambio (valores 1-5) y reclasifica a 3 categorías con cálculo de hectáreas
"""

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QInputDialog
from qgis.core import (
    QgsRasterLayer, QgsVectorLayer, QgsField, QgsFillSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsRasterBandStats,
    QgsProject, Qgis
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface
import os
import processing
from datetime import datetime


def run_vectorization():
    """
    Ejecuta el flujo completo de vectorización y reclasificación.
    No lanza excepciones que cierren QGIS - maneja errores con mensajes al usuario.
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

        # 5. Vectorizar el raster ORIGINAL para obtener los valores 1-5 como atributos
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

        result = processing.run("gdal:polygonize", params)
        vector = QgsVectorLayer(result['OUTPUT'], f"Clasificación {tipo}", "ogr")

        if not vector.isValid() or vector.featureCount() == 0:
            QMessageBox.warning(None, "Sin entidades", "El raster no generó polígonos válidos.")
            try:
                os.remove(output_path)
            except:
                pass
            return

        # 6. Agregar columnas
        vector.startEditing()
        vector.dataProvider().addAttributes([
            QgsField("Sup_has", QVariant.Double),  # Superficie en hectáreas
            QgsField("Tipo", QVariant.String),     # Tipo de categoría
            QgsField("categoria", QVariant.Int)    # Categoría numérica reclasificada
        ])
        vector.updateFields()

        # 7. Calcular valores, RECLASIFICAR y calcular área
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

        # 8. Aplicar estilo condicional
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

        # 9. Añadir capa al proyecto
        QgsProject.instance().addMapLayer(vector)

        iface.messageBar().pushMessage(
            "QForestEyes",
            f"✓ Vectorización completada: {vector.featureCount()} polígonos creados",
            level=Qgis.Success,
            duration=8
        )

    except Exception as e:
        QMessageBox.critical(None, "Error en vectorización", f"Ocurrió un error:\n{str(e)}")
        from qgis.core import QgsApplication
        import traceback
        QgsApplication.instance().messageLog().logMessage(
            f"QForestEyes vectorization error:\n{traceback.format_exc()}",
            "QForestEyes",
            Qgis.Critical
        )