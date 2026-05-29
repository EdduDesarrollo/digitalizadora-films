# AGU printer film scanner
La digitalización de películas fotoquímicas es una necesidad de todos los archivos y colecciones.
A pesar de que en los últimos años han bajado considerablemente los costos de los equipos necesarios, todavía es inaccesible para los archivos y colecciones pequeñas.
Con esto en mente, en el Espacio de digitalización de documentos universitarios del Archivo General de la UDELAR nos abocamos a la tarea de desarrollar un sistema de escaneo de bajo costo y replicable por otras instituciones y particulares que cumpla con ciertos criterios de calidad y sustentabilidad.

<img width="400" height="200" alt="image2" src="https://github.com/user-attachments/assets/bc887b72-1014-4087-983f-aca6ca5a7e00" />


## Componentes

<img width="400" height="400" alt="image6" src="https://github.com/user-attachments/assets/871c9989-c511-47bc-9ca4-4892228428dd" />

1. Una impresora de tickets de las utilizadas en los puestos de venta.

<img width="400" height="400" alt="image12" src="https://github.com/user-attachments/assets/7a4aabcb-5ffc-4c54-8df3-e3bd50ba3120" />

2. Una cámara digital compatible con el software gphoto2. http://www.gphoto.org/proj/libgphoto2/support.php

3. Un lente macro o aros de extensión.

4. Una computadora de mediana potencia con sistema operativo Ubuntu.

<img width="400" height="400" alt="image4" src="https://github.com/user-attachments/assets/d74d393f-e265-4def-9b87-aed1b4be190d" />

5. Un plafón de iluminación led cuadrado de aprox 11 cm de lado.

<img width="400" height="400" alt="image5" src="https://github.com/user-attachments/assets/ffe8d74a-c20d-4cf4-a881-b4dbdbc86906" />


6. Partes que fueron impresas en 3D:
Soporte y agarraderas para plafón de iluminación.

Base, tapa y trancas para películas de 16mm y 35mm.

7. Un tablón de madera como base de todos los elementos.

8. Un pie de ampliadora como soporte de la cámara.

9. Dos antiguas rebobinadoras de película.

## Principio de funcionamiento

<img width="400" height="250" alt="image11" src="https://github.com/user-attachments/assets/dec98bf0-89c8-4cfe-98f9-80574b886b9a" />

Se utiliza el mecanismo de mover el papel de la impresora para traccionar la película. Para ello es necesario hacerle unas pequeñas modificaciones:

1. Tapar el sensor de falta de papel con un adhesivo.

<img width="400" height="266" alt="image3" src="https://github.com/user-attachments/assets/645053f8-d7e1-42b8-ade5-4661f911b810" />


2. Realizar un pequeño corte en el plástico de la tapa por donde va a entrar la película.

<img width="400" height="250" alt="image1" src="https://github.com/user-attachments/assets/374d10af-6c2e-4d45-8560-35b4e514d069" />

3. Remover el eje de la tapa para poder quitarla al enhebrar la película.

<img width="400" height="250" alt="image10" src="https://github.com/user-attachments/assets/e3858138-cb60-41f1-a4c9-4b02f391b6bd" />

Para este proceso no es exclusivo contar con una impresora de tickets, sino que puede utilizarse cualquier impresora térmica genérica. No obstante, las modificaciones podrían tener que adaptarse a la forma de la impresora.

4. Como fuente de luz se utiliza un plafón genérico de led.

5. Se realizan unas piezas impresas en 3D para colocar la fuente de luz a la misma altura que la entrada de la cinta en la impresora y unas guías para llevar la película sobre la ventana hecha en el soporte.
Modelo 3d de la guía para película de 16 mm

6. La cámara con lente macro se sitúa sobre el soporte a una altura adecuada para encuadrar el fotograma. En nuestro caso usamos un pie de una vieja ampliadora fotográfica para sostener la cámara.

<img width="400" height="605" alt="image7" src="https://github.com/user-attachments/assets/94201f88-8134-4422-a704-b85cb33fea67" />


7. Tanto la cámara como la impresora se conectan con la computadora mediante cables usb por lo que no es necesario realizar ningún tipo de conexión extra ni soldaduras.

## Software

<img width="400" height="250" alt="image8" src="https://github.com/user-attachments/assets/c68448fa-8f84-40d0-b1d9-6abe2b21a64f" />


Todo el sistema se maneja con un script de python que controla la cámara mediante la librería gphoto2 y manipula las imágenes mediante opencv. Por el momento este script funciona sólo sobre sistema operativo linux pero es posible portarlo a macOS.

Cuando se comienza a utilizar el software, es necesario ingresar el código de referencia a escanear e indicar la ruta donde se van a guardar las imágenes de los cuadros. Luego, se debe seleccionar el formato de la película. Por el momento, el sistema funciona con películas de 16 mm (se está trabajando para incluir también las de 35 mm, aunque aún no se ha puesto a prueba con el acervo del archivo). En el futuro también se podrá trabajar con películas de 8mm y Súper 8.
 
 
Una vez que se selecciona el formato, en la interfaz del programa se verá el liveview  (visualización en directo) que toma la cámara con tres líneas rojas superpuestas al liveview, que sirven para alinear la cámara con la película, el área en azúl donde el sistema buscará la perforación, además de algunos botones de configuración y reproducción  en la parte inferior derecha de la pantalla y en la parte inferior tres botones (play, pausa y adelantar).

Una vez que la película está alineada con la cámara, es necesario ajustar el foco y otras configuraciones de la cámara. Esto se hace a través del programa Entangle, al cual se puede acceder a través del botón “Ajustes” (o presionando la tecla E).  . Una vez realizados los ajustes, se debe retornar al liveview y, si está todo correcto, se puede comenzar el escaneo. 

El botón de adelantar (tecla C) permite avanzar de a un píxel hasta la parte que se quiere empezar a digitalizar. El botón de pausa (tecla P), sirve para pausar la digitalización en cualquier momento.Para comenzar el escaneo basta con hacer clic en el botón de Play en la parte inferior de la pantalla, o la tecla Z.
 
## Escaneo

El escaneo comienza con la identificación de la perforación mediante el conteo de la cantidad de píxeles blancos en la zona indicada con el recuadro azul (aprox. 2500 pixeles). De no identificar la perforación, la impresora mueve la película de a un píxel hasta encontrar la perforación Si no lo encuentra, imprime 1 px para que la impresora mueva la película hasta que encuentre la perforación.

Para los casos con más de una perforación por cuadro, como las películas de 35 mm, el sistema cuenta las perforaciones hasta identificar el cambio de cuadro. Luego de esto, el proceso de digitalización es el mismo.

Por el momento, los carretes no cuentan con motores, por lo que es necesario que una persona suelte y recoja la película manualmente. Para acelerar el proceso de escaneo, el sistema guarda las imágenes (.jpg) en la carpeta de destino y los archivos raws (tif, cr3, u otros según la cámara) en la tarjeta de memoria de la cámara. Cuando existe un archivo raw en la cámara, el botón “Descargar Raws” cambia a color rojo, avisando que hay archivos pendientes de descarga.

Durante el proceso de escaneo es necesario limpiar todo el sistema cada cierta cantidad de fotos por lo que lo configuramos para que se detenga cada 500 cuadros. Usando aire (pera de goma o aire comprimido) se limpia la zona que se captura removiendo cualquier impureza que se pudo haber desprendido de la película.También aprovechamos esa pausa para descargar las imágenes raws.
 
## Posproducción

Una vez que el escaneo de la película está finalizado, se obtiene una secuencia de fotos digitales numeradas en correspondencia con los cuadros fotoquímicos de la película original. Luego de esto, es necesario un proceso de estabilización digital para corregir los pequeños desfasajes en la toma de las fotos digitales. Una posibilidad para hacerlo es mediante el software de edición de video Davinci Resolve, que tiene una versión gratuita. 
 
## Ventajas y desventajas

La principal ventaja de este sistema es su bajo costo. El componente más caro es la cámara fotográfica, aunque puede utilizarse un cámara sencilla que cumpla con los requisitos de ser compatible con gphoto 2 y contar con un lente macro. Al tratarse de un sistema modular, puede mejorarse progresivamente si se dispone de un presupuesto mayor. En el AGU se utilizó una cámara sin espejo ya descontinuada, de 32 megapíxeles, suficiente para obtener una resolución de 4K (aprox. USD 700), un lente de 50mm (aprox. USD 300) y aros de extensión (aprox. USD 100). La computadora empleada es una de las disponibles en el archivo, con una antigüedad de cuatro años. Las piezas impresas en 3D se produjeron con un equipo muy sencillo, que costó unos USD 300, aunque también pueden fabricarse mediante servicios externos de impresión.

Otra ventaja es su sencillez, dado que no es necesario contar con un conocimiento avanzado de informática para instalar y operar el sistema. El sistema también destaca por su versatilidad. Si bien el diseño se desarrolló inicialmente para la digitalización de películas de 16mm, que conforman la parte más voluminosa del acervo del AGU, es posible adaptar las guías y el script para otros formatos.

Una desventaja es que, por el momento, el sistema solamente puede utilizarse en Ubuntu. Aunque es posible migrarlo a macOS mediante algunas modificaciones, aún no puede ejecutarse en Windows, dado que la librería gphoto2 no es compatible con ese entorno.
 
## Próximos pasos

Como se mencionó anteriormente, este es un proyecto en desarrollo. Tras ponerlo a prueba durante los últimos meses identificamos algunas mejoras a realizar:

Motorizar los carretes de alimentación de película.
Desarrollar la a adaptación para películas de 35 y 8 mm
Mejorar el soporte de la cámara.
Mejoras estéticas en la interfaz de usuario.


## Guía de Configuración y Ejecución del Script

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
