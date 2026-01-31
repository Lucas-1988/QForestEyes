<img src='icons/LogoQFeyes.png' width="250">

**QForestEyes** es un complemento (plugin) para **QGIS** diseñado para la detección de cambios en la cobertura vegetal mediante el análisis de imágenes satelitales. Utiliza la potencia de **Google Earth Engine (GEE)** para procesar grandes volúmenes de datos y generar mapas de diferencia de cobertura vegetal mediante tecnicas de comparación entre fechas utulizando metodos cuantitativos y cualitativos de forma eficiente.

## 🚀 Características principales

* **Integración con Google Earth Engine:** Procesa imágenes de Sentinel-2 directamente en la nube.
* **Análisis Temporal:** Compara dos periodos de tiempo (T1 y T2) para identificar pérdidas o ganancias de biomasa.
* **Umbrales Zonales:** Incluye configuraciones predefinidas para diferentes ecosistemas (Amazónico, Chaqueño, Pampeano, etc.).
* **Vectorización Automática:** Convierte los resultados raster a polígonos vectoriales listos para análisis geoespacial, incluyendo cálculo automático de superficies en hectáreas.
* **Visualización Dinámica:** Clasifica los cambios en hasta 3 categorías (pérdida, sin cambios y ganancia).

## 🛠️ Requisitos

Para utilizar este plugin, es necesario:
1.  Tener instalado **QGIS** (versión 2.8 como mínimo).
2.  Contar con una cuenta registrada en [Google Earth Engine](https://earthengine.google.com/).
3.  Crear un proyecto en GEE y obtener una ID de proyecto (esta ID será la que te solicite el plugin para ejecutarse)
4.  Habilitar las APIs (las APIs de Google Earth Engine API y Google Drive API): https://console.cloud.google.com/apis/dashboard 

## 📂 Estructura del Repositorio

* `qforesteyes.py`: Lógica principal y manejo de la API de Earth Engine.
* `vectorizer.py`: Módulo especializado en la conversión de raster a vector y cálculo de áreas.
* `metadata.txt`: Información técnica del complemento para QGIS.
* `icons/`: Iconografía utilizada en la interfaz del usuario.

## 💻 Instalación

1.  Descarga este repositorio como un archivo `.zip` (o clónalo).
2.  En QGIS, ve al menú **Complementos** > **Administrar e instalar complementos**.
3.  Selecciona **Instalar a partir de ZIP** y elige el archivo descargado.
4.  Asegúrate de tener un **ID de Proyecto de Google Cloud** válido para inicializar GEE.

## 📝 Uso rápido

1.  Inicia el complemento desde la barra de herramientas de QGIS.
2.  Configura el ID de tu proyecto de GEE y selecciona la zona de análisis.
3.  Define los años de referencia (T1) y análisis (T2) junto con el rango estacional.
4.  Dibuja un polígono en el lienzo de QGIS sobre el área de interés.
5.  ¡Listo! El plugin procesará los datos y te notificará cuando el resultado esté disponible en tu Google Drive o listo para vectorizar.

---

## 👨‍💻 Autor
**Lucas M. Leonczyk** *GIS Specialist / Python Developer* [GitHub Profile](https://github.com/Lucas-1988)

## ⚖️ Licencia
Este proyecto está bajo la Licencia GNU GPL v3.