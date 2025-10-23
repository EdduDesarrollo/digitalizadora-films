# Este archivo es parte de digitalizadora-films
#
# Este software está licenciado bajo la Licencia Pública General GNU v3.0 o superior.
# Una copia de la licencia se incluye en el archivo `LICENSE` de este directorio.
# También está disponible en línea en: <https://www.gnu.org/licenses/gpl-3.0.html>.

from __future__ import print_function

from contextlib import contextmanager
import os
import subprocess
import io
import sys
import time
import shutil
from datetime import datetime
import logging
import shutil
import threading
import platform
import glob
import json
import psutil

try:
    import gphoto2 as gp
except ImportError:
    print("El módulo 'gphoto2' no está instalado. Intentando instalarlo...")

    # Instala primero las dependencias del sistema (solo funciona si usas sudo)
    try:
        subprocess.check_call(["sudo", "apt", "install", "-y", "libgphoto2-dev", "gphoto2"])
    except Exception as e:
        print("No se pudo instalar dependencias del sistema. Error:", e)

    # Instala el módulo de Python
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--user","--break-system-packages", "gphoto2"
        ])
    except Exception as e:
        print("No se pudo instalar el módulo 'gphoto2'. Error:", e)
        sys.exit(1)

    # Reintenta la importación
    try:
        import gphoto2 as gp
        print("Módulo 'gphoto2' instalado correctamente.")
    except ImportError:
        print("La instalación falló. No se puede importar 'gphoto2'.")
        sys.exit(1)
try:
    from escpos import printer
except Exception as e:
    print("Módulo 'escpos' no encontrado. Instalando...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--user","--break-system-packages", "python-escpos"
    ])
    # Reintentar la importación después de la instalación
    from escpos import printer    

try:
    import cv2
except Exception as e:
    print("Módulo 'opencv-python' no encontrado. Instalando...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--user","--break-system-packages", "opencv-python"
    ])
    # Reintentar la importación después de la instalación
    import cv2

try:
    import numpy as np
except Exception as e:
    print("Módulo 'numpy' no encontrado. Instalando...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--user","--break-system-packages", "numpy"
    ])
    # Reintentar la importación después de la instalación
    import numpy as np

try:
    from PIL import Image as Imge
    from io import BytesIO
except Exception as e:
    print("El módulo 'Pillow' no está instalado. Intentando instalarlo...")

    # Intenta instalar Pillow
    try:
        import subprocess
        import sys
        subprocess.check_call([sys.executable,
            "-m", "pip", "install",
            "--user","--break-system-packages", "Pillow"
        ])
        # Reintenta importar después de instalar
        from PIL import Image as Imge
        from io import BytesIO
    except Exception as e:
        print("No se pudo instalar el módulo 'Pillow'. Error:", e)
        sys.exit(1)

try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.anchorlayout import AnchorLayout
    from kivy.properties import StringProperty
    from kivy.uix.image import Image
    from kivy.clock import Clock, mainthread
    from kivy.graphics import Color, Rectangle
    from kivy.graphics.texture import Texture # pylint: disable=E0611
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
    from kivy.core.window import Window
    from kivy.uix.filechooser import FileChooserListView #FileChooserIconView
    from kivy.resources import resource_find
    from kivy.core.image import Image as CoreImage
    from kivy.uix.widget import Widget
except ModuleNotFoundError:
    print("Kivy no está instalado. Instalando...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--user","--break-system-packages", "kivy"
    ])
    subprocess.check_call(["sudo", "apt", "install", "-y", "xclip"])
    os.execv(sys.executable, ['python3'] + sys.argv)
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.anchorlayout import AnchorLayout
    from kivy.properties import StringProperty
    from kivy.uix.image import Image
    from kivy.clock import Clock
    from kivy.graphics.texture import Texture # pylint: disable=E0611
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
    from kivy.core.window import Window
    from kivy.uix.filechooser import FileChooserListView #FileChooserIconView
    from kivy.resources import resource_find
    from kivy.core.image import Image as CoreImage
    from kivy.uix.widget import Widget

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception as e:
    print("El módulo 'Pillow' no está instalado. Intentando instalarlo...")
    subprocess.check_call(["sudo", "apt", "install", "-y", "python3-tk"])
    #subprocess.check_call([
    #    sys.executable, "-m", "pip", "install",
    #    "--user","--break-system-packages", "tk"
    #])
    import tkinter as tk
    from tkinter import filedialog, messagebox

def instalar_entangle():
    '''Verifica si entangle está instalado, si no, lo instala'''
    if shutil.which("entangle") is not None:
        print("Entangle ya está instalado.")
        return

    print("Entangle no está instalado. Intentando instalar...")

    try:
        subprocess.check_call(["sudo", "apt", "update"])
        subprocess.check_call(["sudo", "apt", "install", "-y", "entangle"])
        print("Entangle instalado correctamente.")
    except subprocess.CalledProcessError as error:
        print(f"Error al instalar Entangle:\n{error}")
        sys.exit(1)
    except OSError as error:
        print(f"Error inesperado:\n{error}")
        sys.exit(1)

instalar_entangle()

logging.getLogger("PIL").setLevel(logging.DEBUG)

# time between captures
INTERVAL = 0.05 # 0.1

# result
OUT_FILE = 'time_lapse.mp4'
TIEMPO_ESPERA = 1.0
FECHA_ACTUAL = datetime.now().strftime("%d%m%Y")

# Ruta al archivo de configuración
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# Cargar configuración desde el archivo
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        PREFIJO_ARCHIVO = config.get("PREFIJO_ARCHIVO", "")
        CAMARA = config.get("CAMARA", "")
        CARPETA_DESTINO = config.get("CARPETA_DESTINO", "")
        DIRECTORIO_GUARDADO = config.get("DIRECTORIO", "")
        CODIGO_REFERENCIA = config.get("CODIGO_REFERENCIA", "")
except Exception as e:
    print(f"⚠️ No se pudo cargar el archivo de configuración: {e}")
    PREFIJO_ARCHIVO = "UY-UDELAR-AGU-AIH"
    CAMARA = ""
    DIRECTORIO_GUARDADO = ""
    CODIGO_REFERENCIA = ""

def guardar_configuracion(clave, valor):
    """Guarda una configuración específica en el archivo config.json"""
    try:
        # Leer la configuración actual
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        # Actualizar el valor
        config[clave] = valor
        
        # Guardar la configuración actualizada
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Configuración guardada: {clave} = {valor}")
        
    except Exception as e:
        print(f"⚠️ Error al guardar configuración: {e}")

COLOR_BOTONES = (0.175, 0.319, 0.513, 0.997) # (1, 0, 0, 0.5)

# Constantes para mensajes
MENSAJE_PIDO_ROLLO = ("Es necesario saber el número de rollo con el que va a trabajar \n"
    "y la cantidad de dígitos.")
MENSAJE_PIDO_CONTADOR = "Ingresar nuevo número para el contador"
MENSAJE_LIMPIAR_IMPRESORA = ("Debe de limpiar impresora!")

def desmontar_camara_gphoto2():
    '''
    Desmonta cámaras montadas por gphoto2/FUSE/GVFS.
    '''
    # Buscar puntos de montaje en /run/user/1000/gvfs/ que contengan gphoto2:
    gvfs_base = f"/run/user/{os.getuid()}/gvfs"
    if (os.path.exists(gvfs_base)):
        for entry in os.listdir(gvfs_base):
            if "gphoto2:" in entry:
                mount_path = os.path.join(gvfs_base, entry)
                print(f"Desmontando cámara gphoto2 en: {mount_path}")
                try:
                    subprocess.run(['gio', 'mount', '-u', mount_path], check=True)
                except Exception as e:
                    print(f"Error al desmontar {mount_path}: {e}")
                return
    print("No se encontró cámara gphoto2 montada.")

def ingresar_nombre_archivo():
    """Ingresar el nombre que le sigue a UY-UDELAR-AGU"""
    # Crear la ventana principal
    root = tk.Tk()
    root.title("Ingreso del nombre de archivo")

    # Obtener las dimensiones de la pantalla
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Obtener las dimensiones de la ventana
    window_width = 400  # Ancho de la ventana
    window_height = 200  # Alto de la ventana

    # Calcular las coordenadas de la posición central
    position_top = int(screen_height / 2 - window_height / 2)
    position_right = int(screen_width / 2 - window_width / 2)

    # Establecer la geometría de la ventana (concentrada)
    root.geometry(f'{window_width}x{window_height}+{position_right}+{position_top}')

    # Eviar que el usuario cierre la ventana sin ingresar datos
    def on_closing():
        if messagebox.askyesno("Salir", "¿Seguro que quieres salir?"):
            root.destroy()
            sys.exit()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Etiqueta para mostrar el mensaje
    label = tk.Label(
        root,
        text="Ingresa el nombre del archivo:\n" + PREFIJO_ARCHIVO,
        font=("Arial", 12)
    )
    label.pack(pady=10)

    # Campo de texto centrado con valor predeterminado
    nombre_archivo_var = tk.StringVar()
    
    # Establecer valor predeterminado si existe
    if CODIGO_REFERENCIA:
        nombre_archivo_var.set(CODIGO_REFERENCIA)

    # Crear un Entry centrado
    entry = tk.Entry(
        root,
        textvariable=nombre_archivo_var,
        font=("Arial", 12),
        justify="center"
    )
    entry.pack(pady=10)
    entry.focus()
    
    # Seleccionar todo el texto si hay un valor predeterminado
    if CODIGO_REFERENCIA:
        entry.select_range(0, tk.END)

    # Función de acción para el botón
    def on_ok():
        if nombre_archivo_var.get().strip():
            guardar_configuracion("CODIGO_REFERENCIA", nombre_archivo_var.get().upper().strip())
            root.destroy()  # Cerrar la ventana
        else:
            messagebox.showerror(
                "Error",
                "No ha ingresado el nombre del archivo.\nPor favor, ingrese nuevamente."
            )

    # Botón OK
    ok_button = tk.Button(root, text="OK", command=on_ok)
    ok_button.pack(pady=10)

    entry.bind("<Return>", lambda event: ok_button.invoke())
    entry.bind("<KP_Enter>", lambda event: ok_button.invoke())

    # Iniciar la ventana
    root.mainloop()

    return PREFIJO_ARCHIVO + '-' + nombre_archivo_var.get().upper().strip()

desmontar_camara_gphoto2()
NOMBRE_ARCHIVO = ingresar_nombre_archivo()
print(NOMBRE_ARCHIVO)

WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), CARPETA_DESTINO)
os.makedirs(WORK_DIR, exist_ok=True)

def seleccionar_directorio():
    """
    Selecciona donde se van a guardar las fotos
    """
    root = tk.Tk()
    root.withdraw()
    while True:
        carpeta_seleccionada = filedialog.askdirectory(
                                    title="Selecionar Carpeta",
                                    initialdir=WORK_DIR
                                )
        if carpeta_seleccionada:
            guardar_configuracion("DIRECTORIO", carpeta_seleccionada)
            return carpeta_seleccionada

        respuesta = messagebox.askretrycancel(
            "Error",
            "No se ha seleccionado ninguna carpeta. ¿Quieres intentarlo de nuevo?"
        )
        if not respuesta:  # Si el usuario presiona 'Cancelar'
            sys.exit() # cierra completamente el programa

directorio = seleccionar_directorio() if DIRECTORIO_GUARDADO and not os.path.exists(DIRECTORIO_GUARDADO) else DIRECTORIO_GUARDADO
print(f"Directorio inicial: {directorio}")

TITULO = NOMBRE_ARCHIVO

class CustomFileChooserListView(FileChooserListView):
    '''
    Clase para deshabilitar scroll en el FileChooserListView y permitir seleccionar solo carpetas.
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Habilitar solo la navegación por teclado
        self.do_scroll_y = False  # Deshabilitar el desplazamiento vertical
        self.do_scroll_x = False  # Deshabilitar el desplazamiento horizontal

        # Establecemos la selección inicial al primer elemento
        if self.files:
            self.selected = self.files[0]  # Seleccionar el primer archivo
        else:
            self.selected = None


    def is_selected(self, filename):
        '''
        Permitir seleccionar solo carpetas (no archivos).
        '''
        return os.path.isdir(filename) and not filename.startswith('.')

class MenuButton(ButtonBehavior, BoxLayout):
    '''Clase de los botones del menú'''
    text = StringProperty('')
    hover_text = StringProperty('')
    icon_path = StringProperty('')

    def __init__(self, icon_path='', **kwargs):
        super().__init__(
            orientation='vertical',
            size_hint=(None, None),  # Cambiado a (None, None)
            width=110,
            height=80,
            **kwargs
        )

        # Textura del fondo del botón
        texture_path = resource_find('atlas://data/images/defaulttheme/button')
        texture = CoreImage(texture_path).texture if texture_path else None

        with self.canvas.before:
            if icon_path:
                Color(1, 1, 1, 0)  # Fondo transparente si hay icono
                self.rect = Rectangle(pos=self.pos, size=self.size)
            else:
                Color(*COLOR_BOTONES)
                self.rect = Rectangle(texture=texture, pos=self.pos, size=self.size)

        self.bind(pos=self._update_rect, size=self._update_rect) # pylint: disable=E1101
        self.bind(text=self._on_text) # pylint: disable=E1101

        # Crear contenedor
        self.box = BoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            height=self.height * 0.8,
            pos_hint={'center_y': 0.5},
            padding=[0.5, 9, 0.5, 15],
            spacing=1
        )

        self.bind( # pylint: disable=E1101
            height=lambda instance,
            value: setattr(self.box, 'height', value)
        )

        # Crear labels pero con texto vacío inicialmente
        self.label_texto_1 = Label(
            halign="center",
            valign="middle",
            size_hint_y=0.5,
            bold=True,
            font_size=16,
            text_size=(100, None)  # Ancho inicial fijo, altura libre para wrapping
        )
        self.label_texto_1.bind(size=self._update_label_text_size) # pylint: disable=E1101
        self.label_texto_2 = Label(
                halign="center",
                valign="middle",
                size_hint_y=0.4,
                text_size=(100, None)  # Ancho inicial fijo para wrapping
            )
        self.label_texto_2.bind(size=self._update_label_text_size) # pylint: disable=E1101

        if not icon_path:
            self.box.add_widget(self.label_texto_1)
            self.box.add_widget(self.label_texto_2)
        else:
            icon_anchor = AnchorLayout(anchor_x='center', anchor_y='center', size_hint_y=0.9)
            icon_img = Image(source=icon_path, size_hint=(None, None), size=(70, 70))
            icon_anchor.add_widget(icon_img)
            self.box.add_widget(icon_anchor)

        self.add_widget(self.box)
        if not icon_path:
            self._on_text(self, self.text)

        Window.bind(mouse_pos=self.on_mouse_pos)
        self._hover = False

    def on_mouse_pos(self, window, pos):
        if self.collide_point(*self.to_widget(*pos)):
            if not self._hover:
                self._hover = True
                Window.set_system_cursor("hand")
                self.on_hover()
        else:
            if self._hover:
                self._hover = False
                Window.set_system_cursor("arrow")
                self.on_leave()

    def on_hover(self):
        # Cambia el texto del botón al hover_text
        if self.hover_text:
            self.label_texto_1.text = self.hover_text

    def on_leave(self):
        # Vuelve al texto original
        self._on_text(self, self.text)

    def _on_text(self, instance, value): # pylint: disable=W0613
        partes = value.split('\n')
        self.label_texto_1.text = partes[0] if partes else ''
        self.label_texto_2.text = partes[1] if len(partes) > 1 else ''
        self.label_texto_2.opacity = 1 if len(partes) > 1 else 0

    def _update_rect(self, *args): # pylint: disable=W0613
        self.rect.pos = self.pos
        self.rect.size = self.size

    def _update_label_text_size(self, instance, size):
        # Para label_texto_1, configurar text_size con el ancho disponible para permitir wrapping
        if instance == self.label_texto_1:
            # Usar el ancho del contenedor menos un margen mayor para evitar desbordamiento
            instance.text_size = (size[0] - 15, None)  # Ancho restringido con más margen, altura libre
        elif instance == self.label_texto_2:
            # Para el segundo label, también configurar wrapping
            instance.text_size = (size[0] - 15, None)  # Ancho restringido, altura libre
        else:
            # Para otros labels, comportamiento original
            instance.text_size = size

class CamApp(App):
    '''CammApp'''
    directorio_app = directorio
    print(f"Directorio app {directorio_app}")

    ruta_script = os.path.abspath(__file__)
    directorio_base = os.path.dirname(ruta_script)

    camaras_conectadas = False  # Flag para saber si las cámaras están conectadas
    reconnect_attempts = 0 # Contador de intentos
    max_retries = 10 # Número máximo de intentos

    layout = any

    def __init__(self, **kwargs):
        '''M{etodo de inicialización de la clase'''    
        super().__init__(**kwargs)

        self.color_botones = (1, 0, 0, 0.5)  # Color original (rojo traslúcido)
        self.camara_previ = '0'
        self.lview = False
        self.img1 = Image(source='Utils/logo.png', size=(1024,768))
        self.title = TITULO

        self.popup = None

        self.numero_de_rollo = ''
        self.estado_actual = ''
        self.popup = ''
        self.error_label = ''
        self.camera = ''
        self.textinput_digitos = ''
        self.muestro_nro_rollo = ''

        self.btn_digitalizar = ''
        self.btn_1px = ''
        self.btn_directorio = ''
        self.btn_salir = ''
        self.btn_abrir_carpeta = ''
        self.btn_contador = ''
        self.btn_pausar = ''
        self.descargar_imagenes_raw = ''

        self.count = 0
        self.template = ''
        self.next_shot = ''

        self.pausar_digitalizacion = True
        self.digitalizando = False
        self.limpiar_impresora = True
        self.mostrar_cuadricula = True
        self.primer_foto = True
        
        # NUEVO: Flag para controlar operaciones asíncronas
        self._digitalizacion_activa = False

        # Listas para manejo de archivos RAW y eliminación
        self.descargar_raw = []
        self.eliminar_foto = []
        
        # Variables para popups
        self.popup_limpieza = None
        self.popup_descargando_raw = None
        self.popup_contador = None
        self.popup_dir = None
        
        # Variables para timer y manejo de estado
        self.timer = None
        
        # Caché para optimizar búsqueda de imágenes en cámara
        self.last_found_folder = "/"
        
        # Variable para almacenar imagen verificada para mostrar en UI
        self._imagen_actual_verificada = None

        self.printer_pattern = ''
        #self.printer_pattern_16mm = [62, 54, 54, 52] # si no avanza lo suficiente alterno 62 y 63
        #self.printer_pattern_16mm = [55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 55, 54]
        self.printer_pattern_16mm = [10]
        self.printer_pattern_35mm = [22]

        # Zona de analisis de perforación
        self.zona_x_inicio = ''
        self.zona_x_fin = ''
        self.zona_y_inicio = ''
        self.zona_y_fin = ''

        # Zona de 16mm
        self.zona_x_inicio_16mm = 200
        self.zona_x_fin_16mm = 290
        self.zona_y_inicio_16mm = 160
        self.zona_y_fin_16mm = 240

        # Zona de 35mm
        self.zona_x_inicio_35mm = 175 # TODO: ajustar
        self.zona_x_fin_35mm = 250 # TODO: ajustar
        self.zona_y_inicio_35mm = 70 # TODO: ajustar
        self.zona_y_fin_35mm = 155 # TODO: ajustar

        # Zona
        self.zona_xi = 0
        self.zona_xf = 0
        self.zona_yi = 0
        self.zona_yf = 0
        self.umbral_grey = 0

        self.cantidad_perforaciones = 0
        self.formato_digitalizar = ''
        
        # self.umbral_px_blancos = 5000
        self.umbral_px_blancos_16mm = 2400
        self.umbral_px_blancos_35mm = 1850
        self.umbral_px_blancos = ''
        
        self.mostrar_debug = False

        self.tecla_digitalizar = 'z'
        self.tecla_1px = 'c'
        self.tecla_pausar = 'p'
        self.tecla_cambiar_dir = ','
        self.tecla_abrir_dir = '-'
        self.tecla_aumentar_frame = '+'
        self.tecla_aumentar_frame_num = 'Ď'
        self.tecla_editar_frame = 'b'
        self.tecla_ajustes = 'e'
        self.tecla_salir = 'q'
        self.tecla_mostrar_cuadricula = 'l'
        self.tecla_descargar_raw = 'd'

        self.icono_play = 'Utils/Iconos/play.png'
        self.icono_adelantar = 'Utils/Iconos/ff.png'
        self.icono_pausa = 'Utils/Iconos/pause.png'

        self.configurar_logger_en_directorio()

    def build(self):
        '''Crea la aplicación'''
        Window.maximize()
        Window.top = 0
        Window.left = 0

        # Layout principal horizontal
        main_layout = BoxLayout(orientation='horizontal')

        # Layout vertical para imagen y botones
        left_layout = BoxLayout(orientation='vertical')

        # Estado actual arriba de la imagen
        self.estado_actual = Button(
            text=f"Directorio: {self.directorio_app} \n Frame: {self.count}",
            size_hint=(1, 0.04),
            background_color=(0.1, 0.1, 0.1, 0.2),
            valign='middle',
            halign='center',
            font_size=18
        )
        left_layout.add_widget(self.estado_actual)

        # Imagen principal
        left_layout.add_widget(self.img1)

        self.asignar_camaras()

        # Botones de acción abajo, centrados
        bottom_layout = BoxLayout(
            orientation='horizontal',
            size_hint=(None, 1),
            width=350,
            height=100
        )

        self.btn_digitalizar = MenuButton(icon_path=self.icono_play, text=f"\n({self.tecla_digitalizar})")
        self.btn_pausar = MenuButton(icon_path=self.icono_pausa, text=f"\n({self.tecla_pausar})")
        self.btn_1px = MenuButton(icon_path=self.icono_adelantar, text=f"\n({self.tecla_1px})")

        self.btn_digitalizar.bind(on_press=lambda *args: self.digitalizar())
        self.btn_pausar.bind(on_press=self.pausar)
        self.btn_1px.bind(on_press=lambda *args: self.mover_x_px())

        bottom_layout.add_widget(self.btn_digitalizar)
        bottom_layout.add_widget(self.btn_pausar)
        bottom_layout.add_widget(self.btn_1px)

        # Centrar los botones debajo de la imagen
        anchor_bottom = AnchorLayout(anchor_x='center', anchor_y='center', size_hint=(1, None), height=100)
        anchor_bottom.add_widget(bottom_layout)
        left_layout.add_widget(anchor_bottom)
        left_layout.add_widget(Widget(size_hint_y=None, height=30))

        # Sidebar a la derecha
        self.sidebar_expanded = True
        self.sidebar = BoxLayout(
            orientation='vertical',
            size_hint=(None, 1),
            width=120 if self.sidebar_expanded else 40,
            padding=0,
            spacing=0
        )
        self.btn_toggle_sidebar = Button(
            text='>' if self.sidebar_expanded else '<',
            size_hint=(None, None),
            size=(40, 40),
            pos_hint={'top': 1}
        )
        with self.sidebar.canvas.before:
            Color(0.3, 0.3, 0.3, 1)  # Gris sólido
            self.sidebar_rect = Rectangle(pos=self.sidebar.pos, size=self.sidebar.size)
        self.buttons_container = BoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            spacing=0,
            padding=0
        )

        self.sidebar.bind(pos=lambda instance, value: setattr(self.sidebar_rect, 'pos', value))
        self.sidebar.bind(size=lambda instance, value: setattr(self.sidebar_rect, 'size', value))
        self.btn_toggle_sidebar.bind(on_press=self.toggle_sidebar)

        self.btn_directorio = MenuButton(text=f"Cambiar Dir\n({self.tecla_cambiar_dir})")
        self.btn_salir = MenuButton(text=f"Salir\n({self.tecla_salir})")
        self.btn_abrir_carpeta = MenuButton(text=f"Abrir Carpeta\n({self.tecla_abrir_dir})")
        self.btn_contador = MenuButton(text=f"Contador\n({self.tecla_aumentar_frame})")
        self.btn_config_camaras = MenuButton(text=f"Ajustes\n({self.tecla_ajustes})")
        self.btn_editar_contador = MenuButton(text=f"Editar # Frame\n({self.tecla_editar_frame})")
        self.descargar_imagenes_raw = MenuButton(text=f"Descargar RAWs\n({self.tecla_descargar_raw})")

        self.btn_salir.bind(on_press=self.btn_exit_callback)
        self.btn_directorio.bind(on_press=self.cambiar_directorio)
        self.btn_contador.bind(on_press=self.aumentar_1_contador)
        self.btn_abrir_carpeta.bind(on_press=self.abrir_carpeta)
        self.btn_config_camaras.bind(on_press=lambda *args: self.abrir_entangle())
        self.btn_editar_contador.bind(on_press=lambda *args: self.editar_contador())
        self.descargar_imagenes_raw.bind(on_press=self.descargar_archivos_raw)

        # Agrega los botones al sidebar
        self.buttons_container.add_widget(self.btn_config_camaras)
        self.buttons_container.add_widget(self.btn_abrir_carpeta)
        self.buttons_container.add_widget(self.btn_directorio)
        self.buttons_container.add_widget(self.btn_contador)
        self.buttons_container.add_widget(self.btn_editar_contador)
        self.buttons_container.add_widget(self.descargar_imagenes_raw)
        self.buttons_container.add_widget(self.btn_salir)

        # Binding para actualizar el color del botón cuando cambie de posición/tamaño
        self.descargar_imagenes_raw.bind(pos=self._actualizar_posicion_boton_raw, size=self._actualizar_posicion_boton_raw)

        self.sidebar.add_widget(self.btn_toggle_sidebar)
        self.sidebar.add_widget(self.buttons_container)

        # Agregar layouts al principal
        main_layout.add_widget(left_layout)
        main_layout.add_widget(self.sidebar)

        # Inicializar color del botón descargar RAW
        Clock.schedule_once(lambda dt: self.actualizar_color_boton_descargar_raw(), 0.1)

        return main_layout

    def toggle_sidebar(self, *args):
        print(f"self.sidebar_expanded antes: {self.sidebar_expanded}")
        self.sidebar_expanded = not self.sidebar_expanded
        print(f"self.sidebar_expanded despues: {self.sidebar_expanded}")
        self.sidebar.width = 120 if self.sidebar_expanded else 40
        self.btn_toggle_sidebar.text = '>' if self.sidebar_expanded else '<'

        self.sidebar.clear_widgets()

        # Agregar primero el botón toggle
        self.btn_toggle_sidebar.size_hint = (None, None)
        self.btn_toggle_sidebar.size = (40, 40)
        self.btn_toggle_sidebar.pos_hint = {'top': 1}
        self.sidebar.add_widget(self.btn_toggle_sidebar)

        if self.sidebar_expanded:
            self.buttons_container.opacity = 1
            self.buttons_container.size_hint = (1, 1)
            self.buttons_container.height = self.sidebar.height - self.btn_toggle_sidebar.height
            self.sidebar.add_widget(self.buttons_container)
        else:
            self.buttons_container.opacity = 0
            self.buttons_container.size_hint = (None, None)
            self.buttons_container.width = 0
            self.buttons_container.height = 0
        
        # Forzar actualización del layout
        Clock.schedule_once(lambda dt: self.sidebar.do_layout(), 0)

    def configurar_logger_en_directorio(self):
        '''Configura el logger para que escriba scanner.log en el directorio de trabajo seleccionado'''
        log_path = os.path.join(directorio, f"scanner_{NOMBRE_ARCHIVO}.log")

        logger = logging.getLogger(f"scanner_{id(self)}")
        # Logger Level (Nivel de log)
        logger.setLevel(logging.WARNING) # DEBUG, INFO, WARNING, ERROR, CRITICAL

        # Eliminar handlers previos si existen (para no duplicar logs)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Handler de archivo
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Handler de consola (opcional)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        logger.addHandler(console_handler)

        self.logger = logger
        self.logger.info("✅ Logger inicializado en: %s", log_path)
    
    def detectar_ubicacion_impresora(self):
        '''Configurar impresora'''
        caminos = glob.glob("/dev/usb/lp*")
        if not caminos:
            raise RuntimeError("No se detectó ninguna impresora USB")
            
        ruta_impresora = caminos[0]
        # print(f"Impresora detectada en: {ruta_impresora}")
        if not os.access(ruta_impresora, os.W_OK):
            raise PermissionError(
                f"No tenés permisos para acceder a {ruta_impresora}. "
                "Asegurate de tener una regla udev o estar en el grupo 'lp'."
                "Puedes ejecutar sudo usermod -aG lp $USER en tu terminal y reiniciar el sistema."
            )

        # print(f"Impresora detectada y accesible: {ruta_impresora}")
        return printer.File(ruta_impresora)
    
    def mostrar_popup_formato(self):
        print("ENTRA A MOSTRAR POPUP FORMATO")
        try:
            layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
            label = Label(text="Selecciona el Formato", font_size=22, size_hint=(1, 0.3))
            layout.add_widget(label)

            # Centrar los botones usando AnchorLayout
            container = BoxLayout(
                orientation='vertical',
                size_hint=(1, 1),
                padding=[0, 20]  # Padding vertical para separar del título
            )
            botones_layout = BoxLayout(
                orientation='horizontal',
                spacing=30,
                size_hint=(None, None),
                width=500,
                height=150,
                pos_hint={'center_x': 0.5, 'center_y': 0.5}
            )

            btn_8mm = Button(text="8mm", size_hint=(1, None), size=(110, 100), font_size=20)
            btn_super8 = Button(text="Super 8", size_hint=(1, None), size=(110, 100), font_size=20)
            btn_16mm = Button(text="16mm", size_hint=(1, None), size=(110, 100), font_size=20)
            btn_35mm = Button(text="35mm", size_hint=(1, None), size=(110, 100), font_size=20)

            botones_layout.add_widget(btn_8mm)
            botones_layout.add_widget(btn_super8)
            botones_layout.add_widget(btn_16mm)
            botones_layout.add_widget(btn_35mm)
            container.add_widget(botones_layout)
            layout.add_widget(container)

            popup = Popup(title="Selecciona el Formato", content=layout, size_hint=(None, None), size=(800, 300), auto_dismiss=False)

            def seleccionar_8mm(instance):
                self.formato_digitalizar = "8mm"
                print(f"Formato seleccionado: {self.formato_digitalizar}")
                popup.dismiss()
                # Iniciar previsualización y refrescar imagen
                self.arranca_callback()
            def seleccionar_super8(instance):
                self.formato_digitalizar = "super8"
                print(f"Formato seleccionado: {self.formato_digitalizar}")
                popup.dismiss()
                # Iniciar previsualización y refrescar imagen
                self.arranca_callback()
            def seleccionar_16mm(instance):
                self.formato_digitalizar = "16mm"
                self.actualizar_cuadricula_por_formato()
                popup.dismiss()
                # Iniciar previsualización y refrescar imagen
                self.arranca_callback()

            def seleccionar_35mm(instance):
                self.formato_digitalizar = "35mm"
                self.actualizar_cuadricula_por_formato()
                popup.dismiss()
                # Iniciar previsualización y refrescar imagen
                self.arranca_callback()

            btn_8mm.bind(on_press=seleccionar_8mm)
            btn_super8.bind(on_press=seleccionar_super8)
            btn_16mm.bind(on_press=seleccionar_16mm)
            btn_35mm.bind(on_press=seleccionar_35mm)

            popup.open()
        except Exception as e:
            self.logger.error("Error al mostrar popup de formato: %s", e)
            return

    def actualizar_color_boton_descargar_raw(self):
        if hasattr(self, "descargar_imagenes_raw"):
            # Limpiar canvas antes de aplicar nuevos colores
            self.descargar_imagenes_raw.canvas.before.clear()
            
            with self.descargar_imagenes_raw.canvas.before:
                if self.descargar_raw and len(self.descargar_raw) > 0:
                    Color(1, 0, 0, 1)  # Rojo opaco cuando hay RAWs pendientes
                else:
                    Color(*COLOR_BOTONES)  # Color azul por defecto
                
                # Obtener textura del botón
                texture_path = resource_find('atlas://data/images/defaulttheme/button')
                texture = CoreImage(texture_path).texture if texture_path else None
                Rectangle(pos=self.descargar_imagenes_raw.pos, size=self.descargar_imagenes_raw.size, texture=texture)

    def _actualizar_posicion_boton_raw(self, *args):
        """Callback para actualizar la posición del canvas del botón cuando cambie de posición/tamaño"""
        Clock.schedule_once(lambda dt: self.actualizar_color_boton_descargar_raw(), 0)

    def liberar_usb_camara(self):
        folder = "/"
        try:
            files = self.camara.folder_list_files(folder)
            nombres = [files.get_name(i) for i in range(files.count())]
            # pendientes = [f for f in nombres if f.lower().endswith((".cr3", ".jpg"))]
            pendientes = [f for f in nombres if f.lower().endswith((".jpg"))]
            # print(f"Pendientes {pendientes}")
            for nombre in pendientes:
                path_destino = os.path.join("/tmp", nombre)
                file = gp.CameraFile()
                self.camara.file_get(folder, nombre, gp.GP_FILE_TYPE_NORMAL, file)
                file.save(path_destino)
                del file
                self.camara.file_delete(folder, nombre)
            if pendientes:
                self.logger.info("Limpieza de búfer: %s", pendientes)
        except Exception as e:
            self.logger.error("Error al limpiar buffer: %s", e)

    def reiniciar_camara_seguro(self):
        '''Intenta cerrar y reinicializar la cámara completamente'''
        try:
            self.logger.info("Intentando liberar la cámara...")

            # 1. Salir y destruir cámara actual
            if hasattr(self, 'camera') and self.camera:
                try:
                    self.camera.exit()
                    self.logger.debug("✅ Cámara .exit() ejecutado")
                except gp.GPhoto2Error as e:
                    self.logger.error(".exit() falló: %s", e)
                del self.camera
                self.camera = None
                time.sleep(2.5)  # Tiempo para liberar el descriptor USB

             # 2. Volver a detectar la cámara
            autodetect = gp.Camera.autodetect()
            if autodetect.count() == 0:
                raise RuntimeError("Cámara no detectada.")
            
            name, addr = autodetect.get_name(0), autodetect.get_value(0)
            self.logger.debug("Detectada cámara en: %s", addr)

            # 3. Reasignar puerto y crear nueva instancia
            port_info_list = gp.PortInfoList()
            port_info_list.load()
            idx = port_info_list.lookup_path(addr)

            camera = gp.Camera()
            camera.set_port_info(port_info_list[idx])
            time.sleep(1.5)  # Esperar antes de iniciar

            camera.init()
            self.camera = camera

            self.logger.info("Cámara reiniciada correctamente")

        except Exception as e:
            self.logger.error("Error al reiniciar cámara: %s", e)


    def asignar_camaras(self):
        """Asignar las cámaras disponibles basadas en los seriales."""
        asignacion_ok = True
        self.logger.debug("Comenzando asignación de cámaras")

        try:
            # Liberar cualquier cámara previamente asignada
            if hasattr(self, 'camera') and self.camera:
                self.camera = None
            if hasattr(self, 'camara') and self.camara:
                self.camara = None

            autodetected = gp.Camera.autodetect()
            camera_list = [
                (autodetected.get_name(i), autodetected.get_value(i))
                for i in range(autodetected.count())
            ]
            self.logger.debug("Cámaras autodetectadas: %s", camera_list)
            camera_list.sort(key=lambda x: x[0]) # Ordena las cámaras por nombre (o dirección)

            port_info_list = gp.PortInfoList() # pylint: disable=no-member
            port_info_list.load() # Carga la lista de puertos disponibles

            for name, addr in camera_list:
                self.logger.debug("Asignando cámara: %s en %s", name, addr)                
                self.camara = gp.Camera()  # Inicializa la cámara que se va a asignar
                idx = port_info_list.lookup_path(addr)  # Busca la cámara en la lista de puertos
                self.camara.set_port_info(port_info_list[idx])  # Asigna puerto a la cámara

                try:
                    self.logger.debug("Inicializando cámara...")
                    self.camara.exit()
                    self.camara.init()

                    # Configurar capturetarget para guardar en SD card
                    try:
                        config = self.camara.get_config()
                        ok, capture_target_widget = gp.gp_widget_get_child_by_name(config, 'capturetarget')
                        if ok >= gp.GP_OK:
                            count = gp.gp_widget_count_choices(capture_target_widget)
                            for i in range(count):
                                choice = gp.gp_widget_get_choice(capture_target_widget, i)
                                self.logger.debug(f"Opción capturetarget[{i}]: {choice}")
                            gp.gp_widget_set_value(capture_target_widget, 'Memory card')
                            self.camara.set_config(config)
                            self.logger.info("✅ Cámara configurada para guardar en la tarjeta SD.")
                        else:
                            self.logger.warning("No se encontró el parámetro 'capturetarget'")
                    except Exception as e:
                        self.logger.warning("Error configurando 'capturetarget': %s", e)
                    
                    # Obtener número de serie para verificar si es la cámara esperada
                    config_camara = self.camara.get_config()
                    self.logger.debug("config_camara: %s", config_camara)
                    name = 'serialnumber'
                    gp_ok, serialnumber_config = gp.gp_widget_get_child_by_name(config_camara, name)

                    self.logger.debug("gp_ok: %s", gp_ok)
                    self.logger.debug("gp.GP_OK: %s", gp.GP_OK)                    
                    self.logger.debug("p_ok >= gp.GP_OK: %s", gp_ok >= gp.GP_OK)

                    if gp_ok >= gp.GP_OK: # pylint: disable=no-member
                        raw_value = serialnumber_config.get_value()
                        self.logger.debug("Raw Value: %s", raw_value)

                        if raw_value == CAMARA:
                            self.camera = self.camara
                        else:
                            self.logger.warning("No se asignó la cámara con serial %s.", raw_value)
                            asignacion_ok = False
                except gp.GPhoto2Error as e:
                    self.logger.error("Error al inicializar cámara %s: %s", name, e)

            if asignacion_ok:
                self.logger.info("Cámaras asignadas correctamente.")
        except gp.GPhoto2Error as e:
            self.logger.error("Error de GPhoto2: %s", e)
        except ValueError as e:        
            self.logger.error("Error de valor: %s", e)
        except OSError as e:
            self.logger.error("Error del sistema operativo: %s", e)

    def key_action(self, *args):
        '''Teclas'''
        self.logger.debug("Tecla presionada: %s", args[3])
        if args[3] == self.tecla_digitalizar:
            self.digitalizar()
        elif args[3] == self.tecla_1px:
            self.mover_x_px()
        elif args[3] == self.tecla_aumentar_frame or args[3] == self.tecla_aumentar_frame_num:
            self.aumentar_1_contador()
        elif args[3] == self.tecla_abrir_dir:
            self.retroceder_1_px()
        elif args[3] == self.tecla_mostrar_cuadricula:
            self.toggle_cuadricula()
        elif args[3] == self.tecla_pausar:
            self.pausar_digitalizacion = True
            # self.pausar()
        elif args[3] == self.tecla_cambiar_dir:
            self.cambiar_directorio()
        elif args[3] == self.tecla_abrir_dir:
            self.abrir_carpeta()
        elif args[3] == self.tecla_editar_frame:
            self.editar_contador()
        elif args[3] == self.tecla_ajustes:
            self.abrir_entangle()
        elif args[3] == self.tecla_salir:
            self.btn_exit_callback()
        elif args[3] == self.tecla_descargar_raw:
            self.descargar_archivos_raw()
        elif args[3] == '¡':
            self.debug_camptura()
        return True

    def on_start(self):
        # Tamaño de la pantalla
        Window.clearcolor = (0.1, 0.1, 0.1, 0.2)
        Window.bind(on_request_close=self.btn_exit_callback)

        self.configurar_logger_en_directorio()
        print("Abre popup formatos")
        self.mostrar_popup_formato()

        Window.bind(on_key_down=self.key_action)
        self.logger.debug("Aplicación iniciada. Esperando interacción del usuario...")

    def editar_contador(self):
        '''Popup para pedir el número de contador'''
        Window.unbind(on_key_down=self.key_action)

        # Crear layout para popup
        cartel_contador = GridLayout(cols = 1, rows = 3)
        box = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        # Etiqueta para el mensaje
        cartel = Label(
            text=MENSAJE_PIDO_CONTADOR,
            valign='middle'
        )

        # Etiqueta para el mensaje de error
        self.error_label = Label(text='', color=(1, 0, 0, 1)) # Rojo para el mensaje de error

        #Botón para continuar
        boton_continuar = Button(text = "Continuar")
        boton_cancelar = Button(text="Cancelar")

        # Campo de entrada para el número de rollo
        self.textinput = TextInput(
            text=str(self.count),
            unfocus_on_touch=False,
            multiline = False,
            input_filter='int',
            hint_text="Número de Contador",
            size_hint=(1, None),
            height=30
        )

        cartel_contador.add_widget(cartel)
        cartel_contador.add_widget(self.textinput)
        
        # agregar en un contendor para los botones
        box.add_widget(boton_continuar)
        box.add_widget(boton_cancelar)
        cartel_contador.add_widget(box)

        self.popup_contador = Popup(
            title='Ingrese Número de Contador',
            content=cartel_contador,
            size_hint=(None, None),
            size=(400, 200),
            auto_dismiss=False
        )

        self.popup_contador.open()

        # Función para poner el foco en el campo de texto
        def focus_input(*args):
            self.textinput.focus = True
            self.textinput.select_all()
        Clock.schedule_once(focus_input, 0.1)

        # Vincular el botón "Continuar" a la función de asignación del número de rollo
        boton_continuar.bind(on_press=self.asignar_numero_contador)
        boton_cancelar.bind(on_press=self.popup_contador.dismiss)

        # Vincular Enter (on_text_validate) al mismo método del botón
        # pylint: disable=no-member
        self.textinput.bind(
            on_text_validate=lambda instance: boton_continuar.trigger_action(duration=0.1)
        )

    def pido_rollo(self):
        '''Ventana emergente para pedir el número de rollo'''
        Window.unbind(on_key_down=self.key_action)

        path = self.directorio_app
        ultimo_rollo = ""
        self.logger.debug("Data: %s", self.numero_de_rollo)

        # Crear el layout del popup
        self.cartel_rollo = GridLayout(cols = 1, rows = 7)

        # Etiqueta para el mensaje
        cartel = Label(
            text=MENSAJE_PIDO_ROLLO,
            valign='middle'
        )

        # Etiqueta para el mensaje de error
        self.error_label = Label(text='', color=(1, 0, 0, 1)) # Rojo para el mensaje de error

        #Botón para continuar
        archivo_nuevo = Button(text = "Continuar")

        # Agregar widgets al layout
        self.cartel_rollo.add_widget(cartel)

        # Etiqueta "Cantidad de dígitos"
        label_digitos = Label(
            text="Cantidad de dígitos",
            size_hint_y=None,
            height=30,
            valign='middle'
        )

        if self.textinput_digitos:
            digitos = self.textinput_digitos.text
        else:
            digitos = '4'

        # Input para asignar entre 1 y 4
        self.textinput_digitos = TextInput(
            text=digitos,
            input_filter='int',
            multiline=False,
            hint_text="Cantidad de dígitos"
        )

        # Etiqueta "Número de rollo"
        label_num_rollo = Label(
            text="Número de Rollo",
            size_hint_y=None,
            height=30,
            valign='middle'
        )

        if self.numero_de_rollo:
            ultimo_rollo = int(self.numero_de_rollo)

        # Campo de entrada para el número de rollo
        self.textinput = TextInput(
            text=str(ultimo_rollo),
            unfocus_on_touch=False,
            multiline = False,
            input_filter='int',
            hint_text="Número de Rollo",
        )

        # Agrega la etiqueta y el spinner al layout
        self.cartel_rollo.add_widget(label_digitos)
        self.cartel_rollo.add_widget(self.textinput_digitos)
        self.cartel_rollo.add_widget(label_num_rollo)
        self.cartel_rollo.add_widget(self.textinput)
        self.cartel_rollo.add_widget(self.error_label)

        # Agregar el botón "Continuar"
        self.cartel_rollo.add_widget(archivo_nuevo)

        self.popup = Popup(
            title='Ingrese Número de Rollo y Cantidad de Dígitos',
            content=self.cartel_rollo,
            size_hint=(None, None),
            size=(450, 400),
            auto_dismiss=False
        )
        self.popup.open()

        # Función para poner el foco en el campo de texto
        def focus_input(*args):
            self.textinput.focus = True
        Clock.schedule_once(focus_input, 0.1)

        # Vincular el botón "Continuar" a la función de asignación del número de rollo        
        archivo_nuevo.bind(on_press=self.asignar_numero_rollo)

        # Vincular Enter (on_text_validate) al mismo método del botón        
        self.textinput.bind(
            on_text_validate=lambda instance: archivo_nuevo.trigger_action(duration=0.1)
        )

    def guardar_ultimo_cr3_pendiente(self):
        try:
            folder = "/"
            camera_list = self.camera.folder_list_files(folder)
            file_names = [camera_list.get_name(i) for i in range(camera_list.count())]
            self.logger.debug("Archivos pendientes en cámara: %s", file_names)
            cr3_files = sorted([f for f in file_names if f.lower().endswith(".cr3")])
            if not cr3_files:
                self.logger.debug("No hay CR3 pendientes por guardar.")
            else:
                count_anterior = self.count - 1
                # Guardar todos los CR3 pendientes de atrás hacia adelante
                for last_cr3 in reversed(cr3_files):
                    if count_anterior < 0:
                        break
                    cr3_path = (self.template % count_anterior).replace(".jpg", ".cr3")
                    cr3_file = gp.CameraFile()
                    self.camera.file_get(folder, last_cr3, gp.GP_FILE_TYPE_NORMAL, cr3_file)
                    cr3_file.save(cr3_path)
                    self.camera.file_delete(folder, last_cr3)
                    self.logger.info("Guardado CR3 pendiente como: %s", cr3_path)
                    count_anterior -= 1
            
            # Limpieza de archivos residuales
            camera_list = self.camera.folder_list_files(folder)
            file_names = [camera_list.get_name(i) for i in range(camera_list.count())]
            self.logger.debug("Archivos pendientes en cámara: %s", file_names)
            if file_names:
                for name in sorted(file_names):
                    self.camera.file_delete(folder, name)
                    self.logger.debug("Eliminando pendiente: %s", name)
        except Exception as e:
            self.logger.error("Error al guardar CR3 pendientes: %s", e)

    def asignar_numero_contador(self, *args): # pylint: disable=unused-argument
        '''Asigna el número del contador'''
        try:
            Window.bind(on_key_down=self.key_action)
            numero_de_contador = self.textinput.text.strip()

            if numero_de_contador:
                self.count = int(numero_de_contador)
                self.btn_contador.text = "Frame\n(+)"
                self.estado_actual.text = f"Directorio: {self.directorio_app} \n Frame: {self.count}"
                self.logger.debug("Nuevo número de frame asignado: %s", self.count)

                Window.bind(on_key_down=self.key_action)
                self.popup_contador.dismiss()

                self.configurar_logger_en_directorio()
            else:
                # Si el campo está vacío, mostrar mensaje de error
                self.error_label.text = "Por favor, ingrese un número válido."
                self.textinput.text = '' # Limpiar el campo texto
        except ValueError:
            # Si el valor no se puede conovertir a número, mostrar mensaje de error
            self.error_label.text = "Debe ingresar un número válido." # Mensaje de error
            self.textinput.text = '' # Limpiar el campo texto 

    def asignar_numero_rollo(self, *args): # pylint: disable=unused-argument
        '''Asigna el numero de rollo'''
        try:
            Window.bind(on_key_down=self.key_action)
            # Obtener el texto ingresado y quitar espacios extra
            self.numero_de_rollo = self.textinput.text.strip()

            # Verificar que el campo no esté vacío
            if self.numero_de_rollo:
                # Intentar convertir a entero para asegurar que es un número
                num_rollo = int(self.numero_de_rollo)

                cantidad_digitos_text = self.textinput_digitos.text.strip()
                if cantidad_digitos_text:
                    cantidad_digitos = int(cantidad_digitos_text)
                else:
                    self.error_label.text = "Por favor, ingrese la cantidad de dígitos."
                    return

                # Formatear con ceros a la izquierda
                self.numero_de_rollo = f"{num_rollo:0{cantidad_digitos}d}"

                # Actualizar la interfaz con el número de rollo
                self.muestro_nro_rollo.text = self.numero_de_rollo
                self.logger.debug("Número de rollo asignado: %s", self.numero_de_rollo)
                self.title = NOMBRE_ARCHIVO + self.numero_de_rollo

                Window.bind(on_key_down=self.key_action)

                self.popup.dismiss()
                self.configurar_logger_en_directorio()

                self.arranca_callback()
            else:
                # Si el campo está vacío, mostrar mensaje de error
                self.error_label.text = "Por favor, ingrese un número válido."
                self.textinput.text = '' # Limpiar el campo texto
        except ValueError:
            # Si el valor no se puede conovertir a número, mostrar mensaje de error
            self.error_label.text = "Debe ingresar un número válido." # Mensaje de error
            self.textinput.text = '' # Limpiar el campo texto

    def aumentar_1_nro_rollo(self, *args): # pylint: disable=W0613
        '''Función para aumentar en 1 el nro de rollo'''
        self.textinput.text = str(int(self.numero_de_rollo) + 1)
        self.logger.debug("Nuevo número de rollo: %s", self.textinput.text)
        self.asignar_numero_rollo()

    def aumentar_1_contador(self, *args): # pylint: disable=W0613
        '''Función para aumentar en 1 el nro de rollo'''
        self.count += 1
        self.btn_contador.text = "Frame\n(+)"
        self.estado_actual.text = f"Directorio: {self.directorio_app} \n Frame: {self.count}"
        self.logger.debug("Nuevo número de frame: %s", self.count)

    
    def abrir_carpeta(self, *args): # pylint: disable=W0613
        '''Función para abrir la carpeta desitno'''
        try:
            subprocess.run(["xdg-open", self.directorio_app], check=False)
        except subprocess.CalledProcessError as e:
            # print(f"Occurió un error al intentar abrir la carpeta: {e}")
            self.logger.error("Error al abrir la carpeta: %s", e)
    
    def pausar(self, *args):
        '''Pausa la digitalización y captura de imágenes'''
        self.logger.warning("Pausando digitalización...")
        self.pausar_digitalizacion = True

        try:
            Clock.unschedule(self.capture_frame_wrapper)
            self.logger.debug("Clock de captura detenido.")
        except Exception as e:
            self.logger.error(f"No se pudo detener Clock: {e}")

        # Si justo se disparó una foto antes de pausar, elimínala de la cámara
        '''
        time.sleep(1.0)
        folder, last_jpg = self.buscar_imagen_en_camara(self.camera)
        if last_jpg:
            raw_name = last_jpg.replace('.jpg', '.cr3')
            self.eliminar_foto.append(last_jpg)
            self.eliminar_foto.append(raw_name)

        '''
        if hasattr(self, 'popup_limpieza') and self.popup_limpieza and self.popup_limpieza.parent:
            self.popup_limpieza.dismiss()

        self.p._raw(b'\x1b@')
        time.sleep(2)
        # self.eliminar_archivos_residuales()
        self.logger.info("Digitalización pausada")

        # Resetear el flag de digitalización para reanudar live view
        self.digitalizando = False
        
        Clock.schedule_once(lambda dt: self._reanudar_previsualizacion(), 0)
        Window.bind(on_key_down=self.key_action)

    def descargar_archivos_raw(self, *args):
        '''Descarga los archivos RAW de la cámara'''
        self.logger.debug("Iniciando descarga de archivos RAW...")
        self.loading_cursor(True)
        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.update)
            self.timer = None

        Clock.schedule_once(lambda dt: self._abrir_popup_descargando_raw(), 0)

        def tarea_descarga():
            error_ocurrido = False
            try:
                if not hasattr(self, 'descargar_raw') or not self.descargar_raw:
                    self.logger.info("No hay archivos RAW para descargar.")
                    Clock.schedule_once(lambda dt: self._cerrar_popup_descargando_raw(), 0)
                    return

                total_raws = len(self.descargar_raw)
                for index, raw_image in enumerate(self.descargar_raw, 1):
                    raw_name = raw_image[0]
                    raw_download_name = raw_image[1].replace('.jpg', '.cr3')
                    
                    # Actualizar progreso
                    progress_text = f"Descargando {index}/{total_raws} archivos RAW"
                    progress_value = (index / total_raws) * 100
                    Clock.schedule_once(lambda dt, text=progress_text, value=progress_value: self._actualizar_progreso_descarga(text, value), 0)
                    
                    self.logger.debug(f"Descargando RAW: {raw_name} como {raw_download_name}")
                    folder, raw_file = self.buscar_imagen_en_camara(self.camera, nombre=raw_name, raw=True)
                    if raw_file:
                        raw_path = os.path.join(self.directorio_app, raw_download_name)
                        try:
                            camera_file = gp.CameraFile()
                            self.camera.file_get(folder, raw_file, gp.GP_FILE_TYPE_NORMAL, camera_file)
                            camera_file.save(raw_path)
                            self.logger.info(f"Descargado RAW: {raw_path}")
                            self.camera.file_delete(folder, raw_file)
                            self.logger.info(f"Eliminado RAW de la cámara: {folder}/{raw_file}")
                        except Exception as e:
                            self.logger.error(f"Error al descargar/eliminar RAW {raw_file}: {e}")
                            error_ocurrido = True
                            break
                    else:
                        self.logger.info(f"No se encontró RAW {folder}/{raw_name} en la cámara.")

                if not error_ocurrido:
                    self.descargar_raw.clear()
                    Clock.schedule_once(lambda dt: self.actualizar_color_boton_descargar_raw(), 0)
            except Exception as e:
                self.logger.error(f"Error al descargar archivos RAW: {e}")
                error_ocurrido = True
            finally:
                # Programar finalización en el hilo principal
                Clock.schedule_once(lambda dt: self._cerrar_popup_descargando_raw(), 0)
                Clock.schedule_once(lambda dt: self._reanudar_previsualizacion(), 0)
                self.loading_cursor(False)
                if error_ocurrido:
                    # Mostrar popup de error
                    Clock.schedule_once(lambda dt: self._show_error_popup("Ocurrió un error al guardar los archivos RAW."), 0)

        threading.Thread(target=tarea_descarga, daemon=True).start()

    def _abrir_popup_descargando_raw(self):
        box = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Label para mostrar el progreso
        self.progress_label = Label(text="Preparando descarga...", font_size=16)
        box.add_widget(self.progress_label)
        
        # Crear la barra de progreso
        from kivy.uix.progressbar import ProgressBar
        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=20)
        box.add_widget(self.progress_bar)
        
        self.popup_descargando_raw = Popup(
            title='Descargando RAWs',
            content=box,
            size_hint=(None, None),
            size=(400, 180),
            auto_dismiss=False
        )
        self.popup_descargando_raw.open()

    def _cerrar_popup_descargando_raw(self):
        if hasattr(self, 'popup_descargando_raw') and self.popup_descargando_raw:
            self.popup_descargando_raw.dismiss()
            self.logger.info("Descarga de archivos RAW finalizada.")

    def eliminar_archivos_residuales(self):
        if not hasattr(self, 'eliminar_foto') or not self.eliminar_foto:
            self.logger.info("No hay archivos residuales para eliminar.")
            return
            
        self.logger.info("Eliminando archivos residuales de la cámara...")
        self.logger.debug("Archivos a eliminar: %s", self.eliminar_foto)
        # Busca en todas las carpetas posibles
        def eliminar_en_carpeta(camera, folder, nombres):
            camera_list = camera.folder_list_files(folder)
            files_names = [camera_list.get_name(i) for i in range(camera_list.count())]
            for nombre in nombres:
                if nombre in files_names:
                    try:
                        camera.file_delete(folder, nombre)
                        self.logger.info(f"Eliminado: {folder}/{nombre}")
                    except Exception as e:
                        self.logger.error(f"Error al eliminar {folder}/{nombre}: {e}")

        def buscar_y_eliminar(camera, folder, nombres):
            eliminar_en_carpeta(camera, folder, nombres)
            folders = camera.folder_list_folders(folder)
            for i in range(folders.count()):
                subfolder = os.path.join(folder, folders.get_name(i))
                buscar_y_eliminar(camera, subfolder, nombres)

        buscar_y_eliminar(self.camera, "/", self.eliminar_foto)
        self.eliminar_foto.clear()

    def cambiar_directorio(self, *args): # pylint: disable=unused-argument
        '''Solucionar la selección'''
        chooser = CustomFileChooserListView(dirselect=True)

        # Establecer el directorio inicial
        if self.directorio_app == '':
            chooser.path = WORK_DIR
        else:
            chooser.path = self.directorio_app

        # Crear un botón adicional dentro del Popup
        btn_aceptar = Button(text="Aceptar", size_hint=(None, None), width=200)
        # pylint: disable=no-member
        btn_aceptar.bind(on_press=lambda *args: self.selecciona_directorio(chooser.selection))

        # Crear un label para mostrar la ruta
        self.path_label = Label(text='Ruta: ', size_hint_y=None, height=30)

        # Función para actualizar la ruta cuando el usuario seleccione un archivo o carpeta
        def update_label(instance, value):
            if value:
                selected_path = value[0]
                if os.path.isfile(selected_path):
                    # Si es un archivo, obtener su carpeta
                    selected_path = os.path.dirname(selected_path)
                self.path_label.text = f"Ruta: {selected_path}"
            else:
                self.path_label.text = f'Ruta: {instance.path}'


        # Vincular la propiedad 'selection' del FileChooserIconView con la función update_label
        chooser.bind(selection=update_label)

        # Usar un ScrollView para permitir el desplazamiento solo cuando sea necesario
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        scroll.add_widget(chooser)

        # Layout para la parte inferior (botón y ruta)
        box2 = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        box2.add_widget(self.path_label)
        box2.add_widget(btn_aceptar)

        # Layout del Popup (contendrá tanto el selector como el botón adicional)
        popup_layout = BoxLayout(orientation='vertical')
        popup_layout.add_widget(scroll) # El selector de directorios está dentro de un ScrollView
        popup_layout.add_widget(box2) # El BoxLayout estará en la parte inferior

        # Crear el popup
        self.popup_dir = Popup(title="Seleccionar Carpeta", content=popup_layout, size_hint=(0.8, 0.8))
        self.popup_dir.open()

    def arranca_callback(self):
        '''Callback'''
        if self.lview:
            self.timer = Clock.unschedule(self.update, 1)

        try:
            self.p = self.detectar_ubicacion_impresora()
            self.p._raw(b'\x1b@')
            self.p.profile.media['width']['pixels'] = 35
        except Exception as e:
            self.logger.error("Error al detectar la impresora: %s", e)
            self.show_error_dialog("Verifique si la impresora está encendida y conectada.", True)
            try:
                self.p = self.detectar_ubicacion_impresora()
                self.logger.info("Impresora detectada correctamente.")
            except Exception as reconectar_error:
                self.logger.error("No se pudo reconectar la impresora: %s", reconectar_error)

        self.lview = True
        self.title = NOMBRE_ARCHIVO
        if self.camera:
            self.timer = Clock.schedule_interval(self.update, 1.0/24.0)
        else:
            self.logger.error("No hay cámara asignada. No se puede iniciar la digitalización.")
            self.show_error_dialog("No hay cámara asignada. No se puede iniciar la digitalización.", True)
            return

        self.loading_cursor(False)

    def loading_cursor(self, wait = True):
        '''Cargando'''
        if wait:
            Window.set_system_cursor("wait")
        else:
            Window.set_system_cursor("arrow")

    def btn_exit_callback(self, *args): # pylint: disable=unused-argument
        '''Salir del programa'''
        # self.guardar_ultimo_cr3_pendiente()
        self.loading_cursor(True)
        self.pausar_digitalizacion = True
        self.pausar()
        
        # Verificar si hay RAWs pendientes
        if hasattr(self, 'descargar_raw') and self.descargar_raw:
            # Mostrar diálogo de confirmación
            self._mostrar_dialogo_confirmacion_raw()
        else:
            # No hay RAWs pendientes, salir directamente
            self._finalizar_salida()

    def _actualizar_progreso_descarga(self, texto, valor):
        '''Actualiza la barra de progreso de descarga de RAW'''
        if hasattr(self, 'progress_label') and self.progress_label:
            self.progress_label.text = texto
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.value = valor

    def _mostrar_dialogo_confirmacion_raw(self):
        '''Muestra un diálogo de confirmación para guardar archivos RAW pendientes'''
        # Desbloquear teclado temporalmente para el diálogo
        Window.unbind(on_key_down=self.key_action)
        
        # Contar archivos RAW pendientes
        num_raws = len(self.descargar_raw) if hasattr(self, 'descargar_raw') else 0
        
        mensaje = f"Hay {num_raws} archivo{'s' if num_raws != 1 else ''} RAW pendiente{'s' if num_raws != 1 else ''} de descarga.\n\n¿Desea guardarlos antes de salir?"
        
        # Crear popup de confirmación
        popup_confirmacion = Popup(
            title="Confirmar salida",
            size_hint=(None, None),
            size=(500, 250),
            auto_dismiss=False
        )
        
        def guardar_y_salir(instance):
            '''Descargar RAWs y luego salir'''
            popup_confirmacion.dismiss()
            Window.bind(on_key_down=self.key_action)  # Restaurar teclado
            self.descargar_archivos_raw_sincronico()
        
        def salir_sin_guardar(instance):
            '''Salir sin descargar RAWs'''
            popup_confirmacion.dismiss()
            Window.bind(on_key_down=self.key_action)  # Restaurar teclado
            # Limpiar la lista de RAWs pendientes
            if hasattr(self, 'descargar_raw'):
                self.descargar_raw.clear()
            self._finalizar_salida()
        
        def cancelar_salida(instance):
            '''Cancelar la operación de salida'''
            popup_confirmacion.dismiss()
            Window.bind(on_key_down=self.key_action)  # Restaurar teclado
        
        # Crear layout del diálogo
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Mensaje
        mensaje_label = Label(
            text=mensaje, 
            text_size=(450, None),
            halign='center',
            valign='middle',
            font_size=16
        )
        layout.add_widget(mensaje_label)
        
        # Layout de botones
        botones_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=50)
        
        # Botón "Sí, guardar"
        btn_si = Button(text="Sí, guardar", size_hint=(1, 1))
        btn_si.bind(on_press=guardar_y_salir)
        botones_layout.add_widget(btn_si)
        
        # Botón "No, salir sin guardar"
        btn_no = Button(text="No, salir sin guardar", size_hint=(1, 1))
        btn_no.bind(on_press=salir_sin_guardar)
        botones_layout.add_widget(btn_no)
        
        # Botón "Cancelar"
        btn_cancelar = Button(text="Cancelar", size_hint=(1, 1))
        btn_cancelar.bind(on_press=cancelar_salida)
        botones_layout.add_widget(btn_cancelar)
        
        layout.add_widget(botones_layout)
        
        # Asignar el contenido al popup y abrirlo
        popup_confirmacion.content = layout
        self.loading_cursor(False)
        popup_confirmacion.open()

    def _finalizar_salida(self):
        '''Finaliza la salida de la aplicación'''
        self.kill_printer_processes()
        App.get_running_app().stop()

    def descargar_archivos_raw_sincronico(self):
        '''Descarga los archivos RAW de la cámara de forma síncrona antes de salir'''
        self.logger.debug("Iniciando descarga de archivos RAW antes de salir...")

        # Pausar la previsualización si está activa
        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.update)
            self.timer = None

        # Mostrar popup de descarga
        self._abrir_popup_descargando_raw()

        def tarea_descarga():
            error_ocurrido = False
            try:
                if not hasattr(self, 'descargar_raw') or not self.descargar_raw:
                    self.logger.info("No hay archivos RAW para descargar.")
                    Clock.schedule_once(lambda dt: self._finalizar_descarga_y_salida(), 0)
                    return

                total_raws = len(self.descargar_raw)
                for index, raw_image in enumerate(self.descargar_raw, 1):
                    raw_name = raw_image[0]
                    raw_download_name = raw_image[1].replace('.jpg', '.cr3')
                    
                    # Actualizar progreso
                    progress_text = f"Guardando {index}/{total_raws} archivos RAW"
                    progress_value = (index / total_raws) * 100
                    Clock.schedule_once(lambda dt, text=progress_text, value=progress_value: self._actualizar_progreso_descarga(text, value), 0)
                    
                    self.logger.debug(f"Descargando RAW: {raw_name} como {raw_download_name}")
                    folder, raw_file = self.buscar_imagen_en_camara(self.camera, nombre=raw_name, raw=True)
                    if raw_file:
                        raw_path = os.path.join(self.directorio_app, raw_download_name)
                        try:
                            camera_file = gp.CameraFile()
                            self.camera.file_get(folder, raw_file, gp.GP_FILE_TYPE_NORMAL, camera_file)
                            camera_file.save(raw_path)
                            self.logger.info(f"Descargado RAW: {raw_path}")
                            self.camera.file_delete(folder, raw_file)
                            self.logger.info(f"Eliminado RAW de la cámara: {folder}/{raw_file}")
                        except Exception as e:
                            self.logger.error(f"Error al descargar/eliminar RAW {raw_file}: {e}")
                            error_ocurrido = True
                            break
                    else:
                        self.logger.info(f"No se encontró RAW {folder}/{raw_name} en la cámara.")

                if not error_ocurrido:
                    self.descargar_raw.clear()
                    self.logger.info("Descarga de RAWs completada antes de salir.")
            except Exception as e:
                self.logger.error(f"Error al descargar archivos RAW: %e")
                error_ocurrido = True
            finally:
                # Programar finalización en el hilo principal
                if not error_ocurrido:
                    Clock.schedule_once(lambda dt: self._finalizar_descarga_y_salida(), 0)
                else:
                    # Mostrar popup de error y NO cerrar
                    if hasattr(self, 'popup_descargando_raw') and self.popup_descargando_raw:
                        self.popup_descargando_raw.dismiss()
                    Clock.schedule_once(lambda dt: self._show_error_popup("Ocurrió un error al guardar los archivos RAW."), 0)

                    # También puedes reactivar la interfaz si lo necesitas

        # Ejecutar descarga en hilo separado
        threading.Thread(target=tarea_descarga, daemon=True).start()

    def _finalizar_descarga_y_salida(self):
        '''Finaliza la descarga y procede a salir de la aplicación'''
        # Cerrar popup de descarga
        if hasattr(self, 'popup_descargando_raw') and self.popup_descargando_raw:
            self.popup_descargando_raw.dismiss()
        
        # Proceder con la salida normal
        self._finalizar_salida()

    def _finalizar_salida(self):
        '''Finaliza la salida de la aplicación'''
        self.kill_printer_processes()
        App.get_running_app().stop()

    def kill_printer_processes(self, device_path="/dev/usb/lp0"):
        ''' Mata los procesos que tenga la impresora '''
        self.logger.info("Terminando los procesos pendientes en la impresora...")
        try:
            # Verificar si hay procesos usando el dispositivo
            result = subprocess.run(
                ["sudo", "fuser", device_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            
            if result.returncode == 0:
                # Si el comando fuser devuelve un PID, matamos el proceso
                pids = result.stdout.decode().strip().split()
                self.logger.debug("Procesos ocupando el dispositivo %s: %s", device_path, pids)
                
                # Matar los procesos identificados
                for pid in pids:
                    self.logger.debug("Matar el proceso con PID %s...", pid)
                    subprocess.run(["sudo", "kill", "-9", pid])
                self.logger.debug("Procesos terminados.")
            else:
                self.logger.debug("No hay procesos ocupando el dispositivo %s.", device_path)
        
        except Exception as e:
            self.logger.error("Error al intentar matar los procesos: %s", e)

    def empty_event_queue(self, camera):
        while True:
            type_, data = camera.wait_for_event(10)
            if type_ == gp.GP_EVENT_TIMEOUT:
                return
            # if type_ == gp.GP_EVENT_FILE_ADDED:
                # self.logger.debug("Unexpected new file %s", data.folder + data.name)

    def selecciona_directorio(self, seleccion):
        '''Selecciona directorio'''
        if not seleccion:
            self.logger.warning("No se seleccionó ninguna carpeta.")
            return  # Evita continuar si no hay selección

        selected_path = seleccion[0]
        if os.path.isfile(selected_path):
            selected_path = os.path.dirname(selected_path)

        if selected_path != self.directorio_app:
            self.directorio_app = selected_path
            self.estado_actual.text = f"Directorio: {selected_path}"
            self.logger.debug("Carpeta seleccionada: %s", self.directorio_app)
            
            # Guardar el directorio seleccionado en config.json
            try:
                guardar_configuracion("DIRECTORIO", selected_path)
                self.logger.info("Directorio guardado en configuración: %s", selected_path)
            except Exception as e:
                self.logger.error("Error al guardar directorio en configuración: %s", e)
        else:
            self.logger.debug("La carpeta seleccionada es la misma: %s", self.directorio_app)

        # Cerrar popup de manera segura
        if hasattr(self, 'popup_dir') and self.popup_dir and self.popup_dir.parent:
            self.popup_dir.dismiss()
    
    def show_error_dialog(self, message, is_config_cam = False):
        """Muestra un popup de error con un botón para cerrar la aplicación."""
        if self.popup and hasattr(self, 'popup') and self.popup.parent:
            # Si el popup ya está abierto, no lo volvemos a mostrar
            # print("El popup ya está abierto, no se abrirá nuevamente")
            self.popup.dismiss()

        def close_app(instance): # pylint: disable=unused-argument
            popup.dismiss()
            Clock.schedule_once(lambda dt: App.get_running_app().stop())
            #sys.exit() # Cierra la aplicación cuando el usuario presiona "Cerrar"
        
        def reintentar_app(instance): # pylint: disable=unused-argument
            popup.dismiss()
            self.arranca_callback()

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        bottom_layout = BoxLayout(
            orientation='horizontal',
            size_hint=(1,None),
        )

        # Etiqueta para mostrar el mensaje de error
        message_label = Label(text=message, size_hint=(1, 0.7))

        # Botón "Cerrar"
        close_button = Button(text="Cerrar", size_hint=(1, 0.3))
        close_button.bind(on_press=close_app) # pylint: disable=E1101

        if is_config_cam:
            # Botón "Reintentar"
            retry_button = Button(text="Reintentar", size_hint=(1, 0.3))
            retry_button.bind(on_press=reintentar_app) # pylint: disable=E1101
            bottom_layout.add_widget(retry_button)

        bottom_layout.add_widget(close_button)

        # Agregar elementos al layout
        layout.add_widget(message_label)
        layout.add_widget(bottom_layout)
        # layout.add_widget(close_button)

        popup = Popup(
            title="Error",
            content=layout,
            size_hint=(None, None),
            size=(500, 200),
            auto_dismiss=False  # Evita que el usuario cierre el popup sin el botón
        )

        popup.open()

    def capture_preview_from_camara(self, camera):
        '''Captura la vista previa de la cámara indicada'''
        if not hasattr(camera, "capture_preview"):
            error_message = (f"Error: La cámara no está disponible o es inválida.\n"+
                             "Debe de reiniciar o encender las cámaras")
            # print(error_message)
            self.logger.error(error_message)
            Clock.schedule_once(lambda dt: self.show_error_dialog(error_message))
            #self.show_error_dialog(error_message)
            return None
        try:
            # print(f"Capturando vista previa de la cámara {camera_id}...")
            preview_file = gp.CameraFile()
            camera.capture_preview(preview_file)
            return preview_file
            # return camera.capture_preview()
        except gp.GPhoto2Error as e:
            # print(f"Error al capturar la vista previa de la cámara: {e}")
            self.logger.error("Error al capturar la vista previa de la cámara: %s", e)
            try:
                # print("Intentando reinicializar la cámara...")
                self.logger.info("Intentando reinicializar la cámara...")
                camera.exit()
                camera.init()
                # print("Cámara reinicializada.")
                self.logger.info("Cámara reinicializada.")
            except Exception as e:
                # print("Error al reiniciar la cárama:", e)
                self.logger.error("Error al reiniciar la cárama: %s", e)

    def update(self, *args): # pylint: disable=unused-argument
        '''Update'''
        # Pequeña pausa durante captura activa para evitar interferencias
        if hasattr(self, 'digitalizando') and self.digitalizando:
            return
            
        capture = None
        capture = self.capture_preview_from_camara(self.camera)
        # print(f"Capture en update: {capture}")

        if capture:
            # Procesamiento de la imagen
            filedata = capture.get_data_and_size()
            image = Imge.open(io.BytesIO(filedata))
            image_array = np.asarray(image)

            # Convertir la imagen a formato OpenCV y rotar la imagen
            # se agrega k=3 para rotar 90 en el sentido inverso
            rotated_image = np.rot90(np.swapaxes(image_array, 0, 1), k=1)
            #rotated_image = image_array

            preview_array = rotated_image
            if self.mostrar_cuadricula:
                preview_array = self.aplicar_cuadricula(preview_array)

            # Crear una textura con la imagen para Kivy
            video_texture = Texture.create(
                size=(preview_array.shape[1], preview_array.shape[0]),
                colorfmt='rgb'
            )
            video_texture.blit_buffer(
                preview_array.tobytes(),
                colorfmt='rgb',
                bufferfmt='ubyte'
            )

            # Asignar la textura a la iagen de Kivy
            self.img1.texture = video_texture
            self.img1.size = video_texture.size
            self.img1.size_hint = (1, 1)
            self.img1.fit_mode = 'contain'
        else:
            # print("No se pudo capturar la vista previa.")
            self.logger.error("No se pudo capturar la vista previa.")

    @mainthread
    def update_image_texture(self, image_bgr):
        '''Actualizar textura de la imagen en Kivy de forma segura desde hilos'''
        self.logger.info(f"🖼️ MOSTRANDO IMAGEN CAPTURADA - shape: {image_bgr.shape if image_bgr is not None else 'None'}")
        
        # Validar que la imagen no sea None y tenga el formato correcto
        if image_bgr is None:
            self.logger.error("❌ update_image_texture: imagen es None")
            return
        
        if not hasattr(image_bgr, 'shape') or len(image_bgr.shape) != 3:
            self.logger.error("❌ update_image_texture: imagen tiene formato incorrecto")
            return
        
        try:
            # Solo crear la textura si no existe o cambió de tamaño
            self._cached_texture = Texture.create(
                size=(image_bgr.shape[1], image_bgr.shape[0]),
                colorfmt='rgb'
            )
            self._cached_texture.flip_vertical()
            self.img1.texture = self._cached_texture
            self.img1.size = self._cached_texture.size
            self.img1.size_hint = (1, 1)
            self.img1.fit_mode = 'contain'

            imS_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            self._cached_texture.blit_buffer(
                imS_rgb.tobytes(),
                colorfmt='rgb',
                bufferfmt='ubyte'
            )
            self.logger.info(f"✅ IMAGEN MOSTRADA EXITOSAMENTE en self.img1")
        except Exception as e:
            self.logger.error(f"❌ Error en update_image_texture: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    @mainthread
    def _mostrar_imagen_capturada_seguro(self, image_bgr, frame_number):
        """Método seguro para mostrar imagen capturada en el hilo principal de Kivy"""
        try:
            self.logger.info(f"🎯 EJECUTANDO mostrar imagen capturada - Frame: {frame_number}")
            
            if image_bgr is None:
                self.logger.error(f"❌ Imagen BGR es None en _mostrar_imagen_capturada_seguro - Frame: {frame_number}")
                self.logger.error(f"❌ Tipo de image_bgr: {type(image_bgr)}")
                return
            
            # Crear textura directamente (más confiable que update_image_texture)
            self.logger.debug(f"Creando textura para imagen {image_bgr.shape}")
            
            texture = Texture.create(
                size=(image_bgr.shape[1], image_bgr.shape[0]),
                colorfmt='rgb'
            )
            texture.flip_vertical()
            
            # Convertir BGR a RGB
            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            
            # Actualizar textura
            texture.blit_buffer(
                image_rgb.tobytes(),
                colorfmt='rgb',
                bufferfmt='ubyte'
            )
            
            # Asignar a la imagen de Kivy
            self.img1.texture = texture
            self.img1.size = texture.size
            self.img1.size_hint = (1, 1)
            self.img1.fit_mode = 'contain'
            
            self.logger.info(f"✅ IMAGEN FRAME {frame_number} MOSTRADA EXITOSAMENTE")
            
        except Exception as e:
            self.logger.error(f"❌ Error en _mostrar_imagen_capturada_seguro: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            # FALLBACK: Intentar con método original
            try:
                self.logger.info("🔄 Intentando fallback con update_image_texture")
                self.update_image_texture(image_bgr)
            except Exception as e2:
                self.logger.error(f"❌ Fallback también falló: {e2}")

    def actualizar_cuadricula_por_formato(self):
        if self.formato_digitalizar == "16mm":
            self.cuadricula_linea_x1 = 150
            self.cuadricula_linea_x2 = 290
            self.cuadricula_linea_x3 = 810
            self.cuadricula_x1 = 200
            self.cuadricula_x2 = 290
            self.cuadricula_y1 = 480
            self.cuadricula_y2 = 400
        elif self.formato_digitalizar == "35mm":
            self.cuadricula_linea_x1 = 135
            self.cuadricula_linea_x2 = 240
            self.cuadricula_linea_x3 = 750
            self.cuadricula_x1 = 180
            self.cuadricula_x2 = 240
            self.cuadricula_y1 = 560
            self.cuadricula_y2 = 490
            

    def digitalizar(self):
        if self.formato_digitalizar == '16mm':
            self.digitalizar_16mm()
        elif self.formato_digitalizar == '35mm':
            self.digitalizar_35mm()
        else:
            self.logger.error(f"Formato de digitalización desconocido: {self.formato_digitalizar}")
            self.show_error_dialog(f"Formato de digitalización desconocido: {self.formato_digitalizar}")

    def digitalizar_35mm(self):
        ''' Función para digitralizar films 35mm '''
        self.logger.warning("COMIENZO DIGITALIZACIÓN 35mm")

        self.cantidad_perforaciones = 3
        self.zona_xi = self.zona_x_inicio_35mm
        self.zona_xf = self.zona_x_fin_35mm
        self.zona_yi = self.zona_y_inicio_35mm
        self.zona_yf = self.zona_y_fin_35mm
        self.umbral_grey = 245

        self.pausar_digitalizacion = False
        self.limpiar_impresora = False

        # 🔧 CRÍTICO: Resetear flag de digitalización para permitir primera captura
        self.digitalizando = False

        self.primer_foto = True

        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.timer)
            self.timer = None
            # print("Temporizador cancelado")
            self.logger.info("Temporizador cancelado")

        self.timer = Clock.unschedule(self.update)
        #Clock.schedule_once(self._despues_de_esperar, TIEMPO_ESPERA)

        #if not os.path.exists(WORK_DIR):
        #    os.makedirs(WORK_DIR)
        self.template = os.path.join(self.directorio_app, f'{NOMBRE_ARCHIVO}-%05d.jpg')
        self.next_shot = time.time() + INTERVAL
        self.print_size = 0
        self.printer_pattern = self.printer_pattern_35mm
        self.umbral_px_blancos = self.umbral_px_blancos_35mm

        try:
            self.camera.exit()
            self.camera.init()
            # self.liberar_usb_camara()
            # self.reiniciar_camara_seguro()
        except gp.GPhoto2Error as e:
            #print("Reinicialización de cámara falló:", e)
            self.logger.error("Reinicialización de cámara falló: %s", e)
            return 0
   
        try:
            self.eliminar_archivos_residuales()
            # Clock.schedule_interval(self.capture_frame, INTERVAL)
            Clock.schedule_once(self.capture_frame_wrapper, 0)
        except Exception as e:
            # print(f"Error no esperado en digitalizar_35mm: {e}")
            self.logger.error(f"Error no esperado en digitalizar_35mm: %e")
            return 0

    def digitalizar_16mm(self):
        ''' Función para digitralizar films 16mm '''
        self.logger.warning("COMIENZO DIGITALIZACIÓN 16mm")

        self.cantidad_perforaciones = 1        
        self.zona_xi = self.zona_x_inicio_16mm
        self.zona_xf = self.zona_x_fin_16mm
        self.zona_yi = self.zona_y_inicio_16mm
        self.zona_yf = self.zona_y_fin_16mm
        self.umbral_grey = 245

        self.pausar_digitalizacion = False
        self.limpiar_impresora = False

        # 🔧 CRÍTICO: Resetear flag de digitalización para permitir primera captura
        self.digitalizando = False

        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.timer)
            self.timer = None
            # print("Temporizador cancelado")
            self.logger.info("Temporizador cancelado")

        self.timer = Clock.unschedule(self.update)
        #Clock.schedule_once(self._despues_de_esperar, TIEMPO_ESPERA)

        #if not os.path.exists(WORK_DIR):
        #    os.makedirs(WORK_DIR)
        self.template = os.path.join(self.directorio_app, f'{NOMBRE_ARCHIVO}-%05d.jpg')
        self.next_shot = time.time() + INTERVAL
        self.print_size = 0
        self.printer_pattern = self.printer_pattern_16mm
        self.umbral_px_blancos = self.umbral_px_blancos_16mm

        try:
            self.camera.exit()
            self.camera.init()
            # self.liberar_usb_camara()
            # self.reiniciar_camara_seguro()
        except gp.GPhoto2Error as e:
            #print("Reinicialización de cámara falló:", e)
            self.logger.error("Reinicialización de cámara falló: %s", e)
            return 0
   
        try:
            self.eliminar_archivos_residuales()
            # Clock.schedule_interval(self.capture_frame, INTERVAL)
            Clock.schedule_once(self.capture_frame_wrapper, 0)
        except Exception as e:
            # print(f"Error no esperado en digitalizar_16mm: {e}")
            self.logger.error(f"Error no esperado en digitalizar_16mm: %e")
            return 0

    def capture_frame_wrapper(self, dt=None):
        ''' Función que envuelve la captura de frame para manejar excepciones y pausas '''
        if self.pausar_digitalizacion or self.limpiar_impresora:
            self.logger.info("Digitalización pausada, no se capturará el frame.")
            if self.pausar_digitalizacion:
                self.pausar()
            return

        start = time.time()

        try:
            self.capture_frame(0)
        except Exception as e:
            self.logger.error("Error en capture_frame_wrapper: %s", e)
            return

        elapsed = time.time() - start

        intervalo_siguiente = max(elapsed + 0.01, INTERVAL)  # 0.1 s de margen
        self.logger.info(f"Proxima captura en {intervalo_siguiente:.2f} s")
        # Only schedule next capture if not paused or cleaning
        if not self.pausar_digitalizacion and not self.limpiar_impresora:
            Clock.schedule_once(self.capture_frame_wrapper, intervalo_siguiente)

    def capture_frame(self, dt):
        ''' Función que realiza la captura y analiza la ubicación de la perforación'''
        self.start = time.time()
        self.logger.info(f"🎬 INICIANDO capture_frame - Frame: {self.count}")
        
        # Verificar si se debe pausar la digitalización
        if self.pausar_digitalizacion or self.limpiar_impresora:
            self.logger.info("⏸️ Captura pausada - pausar_digitalizacion o limpiar_impresora")
            return
        if self.digitalizando:
            # print("Otra operación está en curso. Espera a que termine.")
            self.logger.warning("⚠️ Otra operación está en curso. Espera a que termine.")
            return

        self.digitalizando = True
        print_size = self.printer_pattern[self.count % len(self.printer_pattern)]

        try:
            if time.time() < self.next_shot:
                self.logger.info("Esperando el intervalo de captura...")
                return

            if not self.camera:
                self.logger.error("La cámara no está inicializada.")
                raise RuntimeError("La cámara no está inicializada.")
            
            # folder = "/"
            max_intentos = 100
            intentos = 0
            alineado = False
            contador_perforaciones = 0 # TODO: 16mm

            while intentos < max_intentos:
                # 1. Captura la vista previa (live view) - optimizado
                preview_file = None
                for _ in range(5):
                    preview_file = self.capture_preview_from_camara(self.camera)
                    time.sleep(0.05)
                
                if not preview_file:
                    self.logger.error("No se pudo capturar la vista previa.")
                    intentos += 1
                    continue

                filedata = preview_file.get_data_and_size()
                image = Imge.open(io.BytesIO(filedata))
                image_array = np.asarray(image)

                # 2. Analiza la alineación
                if self.alinear_perforacion(image_array):
                    self.logger.info("Perforación alineada correctamente.")
                    if contador_perforaciones == self.cantidad_perforaciones or self.primer_foto:
                        alineado = True
                        if self.formato_digitalizar == "35mm":
                            self.primer_foto = False
                        
                        # SOLUCIÓN CRÍTICA: Guardar la imagen verificada para usar en UI
                        # Convertir a formato OpenCV para update_image_texture
                        # La imagen está en RGB, hay que rotar y convertir a BGR
                        rotated_image = np.rot90(np.swapaxes(image_array, 0, 1), k=1)
                        image_bgr = cv2.cvtColor(rotated_image, cv2.COLOR_RGB2BGR)
                        self._imagen_actual_verificada = image_bgr
                        self.logger.debug("Imagen verificada guardada en memoria para UI")
                        
                        break
                    else:
                        contador_perforaciones += 1
                        self.logger.error(f"Perforación {contador_perforaciones}/{self.cantidad_perforaciones} alineada, avanzando film...")
                        self.mover_x_px(print_size)
    
                # Solo log cada 10 intentos para no saturar
                if intentos % 10 == 0:
                    self.logger.debug("Perforación no alineada, moviendo film...")
                intentos += 1

            if not alineado:
                self.logger.warning("No se logró alinear la perforación.")
                return 0

            # 3. Si está alineado, dispara la cámara y guarda la foto
            self.empty_event_queue(self.camera)
            
            # Pre-calcular path para evitar cálculos repetidos
            jpg_path = self.template % self.count
            
            # IMPORTANTE: Capturar la ruta INMEDIATAMENTE después de definirla para evitar problemas de timing
            captured_jpg_path = jpg_path  # Preservar la ruta correcta del archivo antes de cualquier incremento
            
            # Disparar cámara con gestión optimizada de eventos
            self.camera.capture(gp.GP_CAPTURE_IMAGE)

            # Espera optimizada usando eventos de gphoto2
            start_wait = time.time()
            folder, last_jpg = None, None
            
            # Búsqueda optimizada con polling más inteligente
            poll_interval = 0.05  # Empezar con polling rápido
            max_poll_interval = 0.2  # Máximo intervalo de polling
            
            while True:
                # Verificar eventos primero (más eficiente que buscar archivos)
                try:
                    event_type, event_data = self.camera.wait_for_event(50)  # 50ms timeout
                    if event_type == gp.GP_EVENT_FILE_ADDED:
                        # Nuevo archivo detectado por evento
                        folder = event_data.folder
                        last_jpg = event_data.name
                        if last_jpg.lower().endswith('.jpg'):
                            break
                except:
                    pass  # Timeout o error, continuar con búsqueda manual
                
                # Fallback: búsqueda manual si eventos no funcionan
                time.sleep(poll_interval)
                folder, last_jpg = self.buscar_imagen_en_camara(self.camera)
                if last_jpg:
                    break
                    
                # Incrementar intervalo de polling gradualmente para reducir CPU
                poll_interval = min(poll_interval * 1.2, max_poll_interval)
                
                if time.time() - start_wait > 8:  # Reducido aún más el timeout
                    self.logger.error("Timeout esperando nueva imagen JPG...")
                    return 0

            # Procesar archivo de manera ultra-optimizada
            jpg_file = gp.CameraFile()
            self.camera.file_get(folder, last_jpg, gp.GP_FILE_TYPE_NORMAL, jpg_file)
            
            # Guardar JPG tal como viene de la cámara (SIN modificaciones)
            jpg_file.save(jpg_path)
            
            # CRÍTICO: Preparar imagen para mostrar en UI (CON transformaciones)
            # Obtener los datos de la imagen JPG real para procesar solo para visualización
            filedata = jpg_file.get_data_and_size()
            image_real = Imge.open(io.BytesIO(filedata))
            image_real_array = np.asarray(image_real)
            
            # Aplicar transformaciones SOLO para la visualización en UI
            # Convertir a formato OpenCV para update_image_texture
            rotated_real_image = np.rot90(np.swapaxes(image_real_array, 0, 1), k=1)
            
            # NUEVO: Rotar 180 grados para que coincida con el live preview (SOLO PARA UI)
            rotated_real_image_180 = np.rot90(rotated_real_image, k=2)
            
            # NUEVO: Invertir horizontalmente después de la rotación 180° (SOLO PARA UI)
            flipped_real_image = np.fliplr(rotated_real_image_180)
            
            real_image_bgr = cv2.cvtColor(flipped_real_image, cv2.COLOR_RGB2BGR)
            self._imagen_actual_verificada = real_image_bgr
            self.logger.debug("JPG guardado sin modificaciones. Imagen para UI procesada (rotada 180° y flippeada horizontalmente)")
            
            # Actualización crítica del contador - HACER ANTES DE MOSTRAR IMAGEN
            current_frame_number = self.count  # Capturar el número antes de incrementar
            
            # 🎯 MOSTRAR IMAGEN INMEDIATAMENTE - Llamada directa con @mainthread
            self.logger.info(f"🖼️ PROGRAMANDO mostrar imagen capturada - Frame: {current_frame_number}")
            try:
                # Validación antes de llamar al método
                if real_image_bgr is not None:
                    self.logger.debug(f"✅ real_image_bgr válida, shape: {real_image_bgr.shape}")
                    # Llamada directa al método decorado con @mainthread
                    self._mostrar_imagen_capturada_seguro(real_image_bgr, current_frame_number)
                    self.logger.debug("✅ Programación de imagen exitosa")
                else:
                    self.logger.error(f"❌ real_image_bgr es None en capture_frame - Frame: {current_frame_number}")
            except Exception as e:
                self.logger.error(f"❌ Error programando mostrar imagen: {e}")
            
            # Preparar datos RAW inmediatamente (sin operaciones de string costosas)
            if last_jpg.upper().endswith('.JPG'):
                raw_name = last_jpg[:-4] + '.CR3'
            else:
                raw_name = last_jpg.rsplit('.', 1)[0] + '.CR3'
            
            self.descargar_raw.append([raw_name, jpg_path])
            
            # Limpiar archivo de cámara y liberar memoria inmediatamente
            try:
                self.camera.file_delete(folder, last_jpg)
            except:
                pass  # No fallar si no se puede eliminar
            finally:
                del jpg_file  # Forzar liberación de memoria
            
            # Actualizar UI de manera completamente asíncrona
            Clock.schedule_once(lambda dt: self.actualizar_color_boton_descargar_raw(), 0)
            
            # Continuar con operaciones críticas en hilo principal
            self.next_shot += INTERVAL

            # Imprimir y avanzar film - operación crítica que debe ser síncrona
            self.mover_x_px(print_size)
            
            # Incrementar contador después de mostrar imagen
            self.count += 1
            
            # Hacer una copia de la imagen verificada para el hilo asíncrono
            imagen_verificada_copia = self._imagen_actual_verificada.copy() if self._imagen_actual_verificada is not None else None
            
            # Preparar y ejecutar todas las operaciones post-captura de manera asíncrona
            def operaciones_post_captura_async():
                try:
                    # 🎯 PRIORIDAD: Mostrar imagen capturada inmediatamente
                    if imagen_verificada_copia is not None:
                        self.logger.info(f"🖼️ Usando imagen desde memoria - Frame: {current_frame_number}")
                        self.logger.debug(f"✅ imagen_verificada_copia válida, shape: {imagen_verificada_copia.shape}")
                        # Usar método decorado con @mainthread directamente
                        self._mostrar_imagen_capturada_seguro(imagen_verificada_copia, current_frame_number)
                    else:
                        self.logger.warning(f"❌ imagen_verificada_copia es None en hilo asíncrono - Frame: {current_frame_number}")
                        # FALLBACK: Cargar desde disco
                        self.logger.info(f"🖼️ Cargando imagen desde disco - Frame: {current_frame_number}")
                        time.sleep(0.1)  # Pequeña espera
                        
                        captured_jpg_path = self.template % current_frame_number
                        image = cv2.imread(captured_jpg_path)
                        if image is not None:
                            # Aplicar transformaciones SOLO para visualización en UI
                            # El JPG en disco se mantiene sin modificaciones
                            
                            # NUEVO: Rotar 180 grados para que coincida con el live preview (SOLO PARA UI)
                            image_rotated_180 = cv2.rotate(image, cv2.ROTATE_180)
                            
                            # NUEVO: Invertir horizontalmente después de la rotación 180° (SOLO PARA UI)
                            image_flipped = cv2.flip(image_rotated_180, 1)  # 1 = flip horizontal
                            
                            # Usar método decorado con @mainthread directamente
                            self._mostrar_imagen_capturada_seguro(image_flipped, current_frame_number)
                            self.logger.debug(f"JPG sin modificaciones en disco. Imagen para UI procesada (rotada 180° y flippeada): {captured_jpg_path}")
                        else:
                            self.logger.warning(f"❌ No se pudo cargar imagen desde: {captured_jpg_path}")
                        
                    # Actualizar contador en UI thread usando @mainthread
                    self._actualizar_contador_post_captura()
                        
                except Exception as e:
                    self.logger.error(f"❌ Error en operaciones post-captura: {e}")
                    import traceback
                    self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Ejecutar operaciones pesadas en hilo separado
            threading.Thread(target=operaciones_post_captura_async, daemon=True).start()

            # Solo verificar archivos residuales cada 25 capturas (menos frecuente)
            if self.count % 25 == 0:
                def verificar_residuos_async():
                    try:
                        camera_list = self.camera.folder_list_files("/")
                        residuos = [
                            camera_list.get_name(i)
                            for i in range(camera_list.count())
                            if camera_list.get_name(i).lower().endswith((".jpg"))
                        ]
                        if residuos:
                            self.logger.warning("Archivos residuales en cámara: %s", residuos)
                    except Exception as e:
                        self.logger.debug("Error verificando residuos: %s", e)  # Debug level
                
                threading.Thread(target=verificar_residuos_async, daemon=True).start()

            # Verificación de limpieza cada 500 capturas
            if self.count % 500 == 0 and self.count > 0:
                self.logger.warning("Se ha alcanzado el límite de 500 capturas, programando limpieza de impresora.")
                Clock.unschedule(self.capture_frame_wrapper)
                self.limpiar_impresora = True
                self.popup_limpiar_impresora()

            # Log menos frecuente para no saturar
            if self.count % 5 == 0:  # Solo cada 5 capturas
                self.logger.info(f"Frame {self.count} - Tiempo: {time.time() - self.start:.3f} s")
            return 0

        except gp.GPhoto2Error as e:
            self.logger.error("Error de GPhoto2 al capturar imagen: %s", e)
            self.digitalizando = False
            try:
                self.logger.info("Intentando reinicializar la cámara...")
                self.camera.exit()
                time.sleep(0.2)
                self.camera.init()
                self.logger.info("Cámara reinicializada.")
                return 0
            except Exception as e:            
                self.logger.error("Error al reiniciar la cárama: %s", e)
                return 0
        except Exception as e:
            self.logger.error("Error en capture_frame: %s", e)
            self.digitalizando = False
            # Limpiar imagen verificada solo en caso de error
            if hasattr(self, '_imagen_actual_verificada'):
                self._imagen_actual_verificada = None
        finally:
            self.digitalizando = False

        return 0

    def buscar_imagen_en_camara(self, camera, nombre=None, raw=False, folder="/"):
        # Optimización: buscar primero en la última carpeta encontrada, luego en raíz
        extension = ".jpg"
        if raw:
            extension = ".cr3"
            
        def buscar_en_carpeta(carpeta_path):
            try:
                camera_list = camera.folder_list_files(carpeta_path)
                files_names = [camera_list.get_name(j) for j in range(camera_list.count())]
                image_files = [f for f in files_names if f.lower().endswith(extension)]
                
                if nombre:
                    for f in image_files:
                        if f.lower() == nombre.lower():
                            self.last_found_folder = carpeta_path  # Actualizar caché
                            return carpeta_path, f
                elif image_files:
                    self.last_found_folder = carpeta_path  # Actualizar caché
                    return carpeta_path, sorted(image_files)[-1]  # El más reciente
            except Exception:
                pass  # Ignorar errores en carpetas inaccesibles
            return None, None
        
        # 1. Buscar primero en la última carpeta donde se encontró algo
        if hasattr(self, 'last_found_folder') and self.last_found_folder != folder:
            result = buscar_en_carpeta(self.last_found_folder)
            if result[1]:
                return result
        
        # 2. Buscar en la carpeta raíz
        result = buscar_en_carpeta(folder)
        if result[1]:
            return result
            
        # 3. Si no se encuentra, buscar en subcarpetas
        try:
            folders = camera.folder_list_folders(folder)
            for i in range(folders.count()):
                subfolder = folders.get_name(i)
                full_subfolder = os.path.join(folder, subfolder)
                result = buscar_en_carpeta(full_subfolder)
                if result[1]:
                    return result
                    
                # Búsqueda recursiva solo si es necesario
                result = self.buscar_imagen_en_camara(camera, nombre, raw, full_subfolder)
                if result[1]:
                    return result
        except Exception:
            pass  # Ignorar errores de acceso a carpetas
            
        return None, None

    def alinear_perforacion(self, image_rgb):
        '''
        Detecta si la perforación está alineada.
        Si no lo está, llama a mover_x_px() hasta que la imagen lo esté.
        '''
        
        # Convertir a escala de grises y recortar zona
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)

        zona_1 = gray[self.zona_yi:self.zona_yf, self.zona_xi:self.zona_xf]        

        _, thresh = cv2.threshold(zona_1, self.umbral_grey, 255, cv2.THRESH_BINARY) # 252, 255
        cantidad_blanco = cv2.countNonZero(thresh)

        self.logger.info("Píxeles blancos detectados en zona: %s", cantidad_blanco)
        mover_mas = False
        if self.mostrar_debug:
            debug_img = image_rgb.copy()
            debug_img_bgr = cv2.cvtColor(debug_img, cv2.COLOR_RGB2BGR)

            if debug_img_bgr is not None and debug_img_bgr.size > 0:
                cv2.rectangle(debug_img_bgr, (self.zona_xi, self.zona_yi), (self.zona_xf, self.zona_yf), (255, 0, 0), 2) # azul
                cv2.putText(
                    debug_img_bgr,
                    f'px blancos z1: {cantidad_blanco}',
                    (30, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )
                cv2.imshow("debug_img_bgr", debug_img_bgr)
            else:
                self.logger.error("debug_img_bgr está vacío, no se puede mostrar.")

            if thresh is not None and thresh.size > 0:
                cv2.imshow("debug_zona_thresh.jpg", thresh)
            else:
                self.logger.error("thresh está vacío, no se puede mostrar.")

            key = 0
            while True:
                key = cv2.waitKey(0) & 0xFF
                if key == ord('e'):
                    # cv2.destroyAllWindows()
                    break
                elif key == ord('q'):
                    cv2.destroyAllWindows()
                    self.pausa()
                    break
                elif key == ord('r'):
                    self.mostrar_debug = False
                    cv2.destroyAllWindows()
                    break

        if cantidad_blanco > self.umbral_px_blancos:
            self.logger.info("Perforación alineada.")
            return True
        else:
            if mover_mas:
                self.mover_x_px(self.printer_pattern[self.count % len(self.printer_pattern)])
            else:
                self.mover_x_px()

        return False

    def popup_limpiar_impresora(self):
        '''Popup para pedir el número de contador'''
        Window.unbind(on_key_down=self.key_action)

        # Crear layout para popup
        cartel_limpiar = GridLayout(cols = 1, rows = 3)
        box = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        # Etiqueta para el mensaje
        cartel = Label(
            text=MENSAJE_LIMPIAR_IMPRESORA,
            valign='middle'
        )

        # Etiqueta para el mensaje de error
        self.error_label = Label(text='', color=(1, 0, 0, 1)) # Rojo para el mensaje de error

        #Botón para continuar
        boton_continuar = Button(text = "Reanudar")
        boton_cancelar = Button(text="Cancelar")

        cartel_limpiar.add_widget(cartel)
        
        # agregar en un contendor para los botones
        box.add_widget(boton_continuar)
        box.add_widget(boton_cancelar)
        cartel_limpiar.add_widget(box)

        self.popup_limpieza = Popup(
            title='Digitalización pausada',
            content=cartel_limpiar,
            size_hint=(None, None),
            size=(400, 200),
            auto_dismiss=False
        )

        self.popup_limpieza.open()

        # Vincular el botón "Continuar" a la función de asignación del número de rollo
        # pylint: disable=no-member
        boton_continuar.bind(on_press=lambda *args: self.reanudar_digitalizacion())
        boton_cancelar.bind(on_press=lambda *args: self.pausar())

    def reanudar_digitalizacion(self, *args):
        '''Reanuda la digitalización después de limpiar la impresora'''
        self.logger.warning("Reanudando digitalización después de limpieza de impresora")
        
        # CRÍTICO: Añadir flag para cancelar operaciones asíncronas pendientes
        self._digitalizacion_activa = True
        
        Window.bind(on_key_down=self.key_action)
        self.limpiar_impresora = False
        
        # Cerrar popup de manera segura
        try:
            if hasattr(self, 'popup_limpieza') and self.popup_limpieza:
                self.popup_limpieza.dismiss()
                # Dar tiempo para que el popup se cierre completamente
                time.sleep(0.2)
        except Exception as e:
            self.logger.error(f"Error cerrando popup de limpieza: {e}")
        
        # Pausar live view para reanudar digitalización
        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.update)
            self.timer = None
        
        # Limpiar cualquier scheduling pendiente
        try:
            Clock.unschedule(self.capture_frame_wrapper)
        except:
            pass
        
        # Ensure digitalizando flag is reset
        self.digitalizando = False
        self.pausar_digitalizacion = False
        
        # MEJORADO: Schedule con delay más largo y validación
        def iniciar_reanudacion(dt):
            if self.limpiar_impresora or self.pausar_digitalizacion:
                self.logger.warning("Reanudación cancelada - flags de pausa activos")
                return
            
            self.logger.info("Iniciando reanudación de digitalización...")
            Clock.schedule_once(self.capture_frame_wrapper, 0.1)
        
        Clock.schedule_once(iniciar_reanudacion, 0.5)
    
    @mainthread
    def _actualizar_contador_post_captura(self):
        """Actualizar el estado de la UI después de una captura exitosa"""
        self.estado_actual.text = f"Directorio: {self.directorio_app} \n Frame: {self.count}"

    def mover_x_px(self, x=1):
        ''' Función para ajustar la posición del film'''
        img = Imge.new("1",(35, x), 1)
        self.p.image(img)
        self.logger.info(f"Ajuste impresora: {x}")
        self.p._raw(b'\n')

    def retroceder_1_px(self):
        '''Función para retroceder la posición del film'''
        self.p._raw(b'\x1B\x4A\xFF')
        self.logger.info(f"Ajuste impresora: -1")
        self.p._raw(b'\n')

    def aplicar_cuadricula(self, image_array, color=(255, 0, 0), thickness=1):
        '''Dibuja dos líneas verticales: una a 400px desde la izquierda y otra desde la derecha'''
        result = image_array.copy()
        h, w, _ = result.shape

        # Línea a 150 px desde la izquierda
        cv2.line(
            result,
            (self.cuadricula_linea_x1, 0),
            (self.cuadricula_linea_x1, h),
            color,
            thickness
        )  # pylint: disable=E1101
        # Línea a 290 px desde la izquierda
        cv2.line(
            result,
            (self.cuadricula_linea_x2, 0),
            (self.cuadricula_linea_x2, h),
            color,
            thickness
        )  # pylint: disable=E1101
        # Línea a 810 px desde la izquierda
        cv2.line(
            result,
            (self.cuadricula_linea_x3, 0),
            (self.cuadricula_linea_x3, h),
            color,
            thickness
        )  # pylint: disable=E1101

        # Rectángulo de verificación de perforación
        cv2.rectangle(
            result,
            (self.cuadricula_x1, self.cuadricula_y1),
            (self.cuadricula_x2, self.cuadricula_y2),
            (0, 0, 255),
            2
        )

        return result

    def toggle_cuadricula(self):
        '''Mostrar cuadricula en preview'''
        self.mostrar_cuadricula = not self.mostrar_cuadricula
        # print(f"Cuadrícula {'activada' if self.mostrar_cuadricula else 'desactivada'}")

    def abrir_entangle(self, *args): # pylint: disable=W0613
        '''Abre Engangle, pausa la previsualización y la reactiva al cerrar'''
        # print("Abriendo Entangle...")

        # Detener la previsualización
        if hasattr(self, 'timer') and self.timer:
            Clock.unschedule(self.update)
            self.timer = None
            # print("Previsualización detenida")

        if hasattr(self, 'camera') and self.camera:
            try:
                self.camera.exit()
                # print("Cámara 2 cerrada")
            except Exception as e: # pylint: disable=W0718
                # print(f"Error al cerrar cámara 2: {e}")
                self.logger.error("Error al cerrar cámara 2: %s", e)

        def ejecutar_entangle():
            try:
                # Ejecutar Entangle
                proceso = subprocess.Popen(["entangle"])
                # print("Entangle ejecutándose...")
                proceso.wait() # Esperar a que el usuario cierre Entangle
                # print("Entangle cerrado")

                # Volver a ativar la previsualización desde el hilo principal
                Clock.schedule_once(lambda dt: self._reanudar_previsualizacion(), 0)

            except FileNotFoundError:
                Clock.schedule_once(lambda dt: self._show_error_popup(
                    "No se encontró el programa Entangle. Asegúrese de que esté instalado."
                ))
            except Exception as e: # pylint: disable=W0718
                Clock.schedule_once(lambda dt:
                    self._show_error_popup(f"Error al ejecutar Entangle:\n{e}")
                )

        # Ejecutar en un hilo para no bloquear la interfaz
        threading.Thread(target=ejecutar_entangle, daemon=True).start()

    def _reanudar_previsualizacion(self):
        # print("Reconectando cámaras...")
        self.logger.info("Reconectando cámaras...")

        try:
            self.asignar_camaras()
            # print("Cámaras asignadas correctamente")
            self.logger.info("Cámaras asignadas correctamente")

            self.timer = Clock.schedule_interval(self.update, 1.0 / 24.0)
            # print("Previsualización reactivada")
            self.logger.info("Previsualización reactivada")
            Clock.schedule_once(self._despues_de_esperar, TIEMPO_ESPERA)

        except Exception as e: # pylint: disable=W0718
            self._show_error_popup(f"Error al reconectar la(s) cámara(s):\n{e}")
    
    def _despues_de_esperar(self, dt): # pylint: disable=unused-argument
        # Código a ejecutar después de la espera de 2 segundos
        # print(f"Esperando {TIEMPO_ESPERA} segundos...")
        self.logger.info("Esperando %s segundos...", TIEMPO_ESPERA)
        # print(" para que la cámara termine la operación anterior...")
        self.logger.info(" para que la cámara termine la operación anterior...")
        self.loading_cursor(False)

    def _show_error_popup(self, mensaje="Ha ocurrido un error"):

        box = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Label para mostrar el mensaje
        label = Label(text=mensaje, font_size=16)
        box.add_widget(label)
        
        # Botón para cerrar el popup
        btn = Button(text='Cerrar', size_hint_y=None, height=40)
        box.add_widget(btn)

        error_popup = Popup(
            title='Error',
            content=box,
            size_hint=(None, None),
            size=(600, 250),
            auto_dismiss=False
        )
        btn.bind(on_release=error_popup.dismiss) # pylint: disable=E1101
        error_popup.open()

    
    def desmontar_camara_usb_por_serial(self, serial):
        '''
        Desmonta el dispositivo USB que corresponde al número de serie de la cámara.
        '''
        try:
            # Buscar todos los dispositivos montados
            for part in psutil.disk_partitions():
                # Obtener información udev para el dispositivo
                try:
                    udevadm_info = subprocess.check_output(['udevadm', 'info', '--query=all', '--name', part.device]).decode()
                    if f"ID_SERIAL_SHORT={serial}" in udevadm_info or f"ID_SERIAL={serial}" in udevadm_info:
                        # print(f"Desmontando cámara montada en: {part.mountpoint} ({part.device})")
                        subprocess.run(['udisksctl', 'unmount', '-b', part.device], check=True)
                        return
                except Exception as e:
                    continue
            # print("No se encontró dispositivo USB con ese serial montado.")
            self.logger.error("No se encontró dispositivo USB con ese serial montado.")
        except Exception as e:
            # print(f"Error buscando dispositivo USB por serial: {e}")
            self.logger.error("Error buscando dispositivo USB por serial: %s", e)

    def debug_camptura(self):
        self.mostrar_debug = False if self.mostrar_debug else True

    def crear_video():
        print('Crear video')
        #subprocess.check_call(['ffmpeg', '-r', '25',
        #                       '-i', template, '-c:v', 'h264', OUT_FILE])
        #for i in range(count):
        #   os.unlink(template % i)

    def main():
        ''' '''
        # kill_printer_processes()

        # digitalizar_16mm()
        # mover_x_px()

if __name__ == "__main__":
    CamApp().run()

