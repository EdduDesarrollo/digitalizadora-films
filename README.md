# Guía de Configuración y Ejecución del Script

Este documento proporciona los pasos necesarios para preparar y ejecutar el script correctamente.

## Paso 1: Instalar Python 3

Asegúrate de tener Python 3 instalado en tu sistema. Puedes descargarlo e instalarlo desde el sitio oficial de Python: [python.org](https://www.python.org/downloads/).

## Paso 2: Obtener el Número de Serie de la Cámara Usando la Terminal

1. **Instalar `gphoto2` (si no está instalado):**

   Abre una terminal y ejecuta el siguiente comando para instalar `gphoto2`:

   ```bash
   sudo apt update
   sudo apt install gphoto2
   ```

2. **Conectar la Cámara:**

   Asegúrate de que tu cámara esté conectada al puerto USB de tu computadora.

3. **Listar Dispositivos Conectados:**

   Ejecuta el siguiente comando para listar los dispositivos conectados y verificar que tu cámara sea reconocida:

   ```bash
   gphoto2 --auto-detect
   ```

   Esto debería mostrar una lista de dispositivos conectados, incluyendo tu cámara.

4. **Obtener el Número de Serie:**

   Una vez que hayas confirmado que la cámara está conectada y reconocida, ejecuta el siguiente comando para obtener el número de serie:

   ```bash
   gphoto2 --get-config serialnumber
   ```

   Este comando debería devolver el número de serie de la cámara.

5. **Actualizar el Archivo `config.json`:**

   Abre el archivo `config.json` y actualiza el campo `"CAMARA"` con el número de serie obtenido:

   ```json
   {
       "CAMARA": "tu_numero_de_serie_aqui"
   }
   ```

## Paso 3: Crear el Ejecutable en el Escritorio

Para crear un acceso directo en el escritorio que ejecute el script, sigue estos pasos:

1. **Crear un Archivo de Escritorio:**

   Crea un nuevo archivo con extensión `.desktop` en tu escritorio. Puedes hacerlo usando un editor de texto o desde la terminal:

   ```bash
   touch ~/Escritorio/digitalizar_film.desktop
   ```

2. **Editar el Archivo `.desktop`:**

   Abre el archivo `.desktop` y agrega el siguiente contenido, ajustando los campos según sea necesario:

   ```ini
   [Desktop Entry]
    Version=1.0
    Type=Application
    Name=Digitalizadora films
    Comment=Ejecutar digitalizar-film.py
    Exec=gnome-terminal -- bash -c "python3
    /home/NOMBRE_USUARIO/Escritorio/digitalizadoraFilms/digitalizar-film.py"
    Icon=/home/NOMBRE_USUARIO/Escritorio/digitalizadoraFilms/Utils/Iconos/film_icon.png
    Terminal=false
    Categories=Utility;
   ```

   Asegúrate de reemplazar `/home/NOMBRE_USUARIO/Escritorio/digitalizadoraFilms/digitalizar-film.py"` con la ruta real a tu script y `/home/NOMBRE_USUARIO/Escritorio/digitalizadoraFilms/Utils/Iconos/film_icon.png` con la ruta a un icono si lo deseas.

3. **Hacer el Archivo Ejecutable:**

   Cambia los permisos del archivo para hacerlo ejecutable:

   ```bash
   chmod +x ~/Escritorio/digitalizar_film.desktop
   ```

4. **Verificar el Acceso Directo:**

   Ahora deberías ver el acceso directo en tu escritorio. Haz doble clic para ejecutar el script.

---

Con estos pasos completados, deberías estar listo para ejecutar el script sin problemas. Si encuentras algún problema, revisa cada paso para asegurarte de que todo esté configurado correctamente.
