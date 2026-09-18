# Instalador (print_scanner_app)

## Uso

Desde la raíz del repositorio:

```bash
python3 print_scanner_app/installer/install.py
```

Solo verificación, sin cambios (falla con código 2 si falta algo):

```bash
python3 print_scanner_app/installer/install.py --check
```

Si apt falla con «paquetes rotos», diagnosticar sin instalar:

```bash
python3 print_scanner_app/installer/install.py --diagnose
```

Incluir dependencias de desarrollo (pytest):

```bash
python3 print_scanner_app/installer/install.py --dev
```

## Qué hace

Durante la instalación, la terminal muestra cada paso (paquetes a instalar y la salida en vivo de `apt` y `pip`).

1. `apt update` (si no es dry-run).
2. Instala paquetes de sistema vía `apt` (requiere `sudo`): libgphoto2, SDL2/Kivy, `xclip`, `usbutils`, etc. `entangle` es opcional.
3. Instala dependencias Python desde `requirements-runtime.txt` con `pip install --user` y `--break-system-packages` cuando el sistema lo exige (Ubuntu 24.04+).
4. Comprueba que cada paquete se pueda importar tras la instalación.
5. Configura permisos de impresora térmica (`udev` + grupo `lp` para `/dev/usb/lp*`).
6. Si todo OK y no es dry-run, crea acceso directo en el escritorio (`~/Escritorio` o `~/Desktop`) y en el menú de aplicaciones (icono `Utils/Images/film_icon.png`).

Solo el acceso directo (dependencias ya instaladas):

```bash
python3 print_scanner_app/installer/install.py --desktop-only
```

La lista canónica de paquetes pip está en `requirements-runtime.txt` (no duplicada en el instalador).

## Tests (desarrollo)

```bash
python3 print_scanner_app/installer/install.py --dev
pytest print_scanner_app/tests/unit/installer/ -q
```

## Desinstalar dependencias

Desde la raíz del repositorio (como usuario normal, **sin** `sudo ./...`):

```bash
chmod +x eliminar_dependencias.sh
./eliminar_dependencias.sh
```

El script pide contraseña solo para `apt` y la regla udev. Usa `--break-system-packages` en pip (igual que el instalador en Ubuntu 24+).

Opciones: `--apt-only`, `--pip-only`, `--no-desktop`, `--purge-build` (incluye `python3-pip`).

Si `libgphoto2-dev` aparece como «no instalado», es porque nunca se instaló en esa máquina (instalador incompleto o solo runtime `gphoto2`). Si `gphoto2`/`xclip` no se quitan con apt, suele ser por dependencias de otros paquetes del sistema; ver mensajes al final del script.

## Cámara y locale (gphoto2)

El programa **adapta automáticamente** los textos de configuración de la cámara al idioma que libgphoto2 muestra en **esa PC** (`libgphoto2-l10n`). No hace falta unificar `LANG` ni `LC_ALL` entre estaciones ni editar `config.json` por idioma.

- Mismo `config.json` del repositorio en todas las PCs.
- Destino de capturas: clave `DIRECTORIO` (ruta absoluta). En la primera ejecución la app pide prefijo, serial de cámara, carpeta y código de sesión si faltan.
- Tras conectar la cámara, el sistema intenta dejar la captura en **tarjeta SD** (no RAM interna).
- Si algo falla, revisar `print_scanner_app/logs/app.log`: buscar  
  `Warning! No se pudo configurar la camara. Revisar configuración manualmente.`

Diagnóstico rápido en terminal:

```bash
gphoto2 --get-config capturetarget | grep -E 'Current|Choice'
```

**Entangle:** re-guardar `CONFIG_CAMARA` desde Entangle en otra PC puede dejar el JSON con textos distintos; el apply del programa los resuelve igual si la versión instalada incluye multi-locale.

Documentación de diseño: [`docs/CAMBIOS_MULTIIDIOMA.md`](../../docs/CAMBIOS_MULTIIDIOMA.md).

## Logs

`print_scanner_app/logs/install.log`

## Troubleshooting

- **«paquetes rotos» / `dpkg returned an error code (1)`**: el instalador intenta `dpkg --configure -a` y `apt --fix-broken install` al inicio. Si sigue fallando, ejecutar manualmente y repetir el instalador:
  ```bash
  sudo dpkg --configure -a
  sudo apt --fix-broken install -y
  sudo apt update
  python3 print_scanner_app/installer/install.py
  ```
- Si `apt` o `sudo` fallan, ejecutar los comandos indicados en consola manualmente.
- Si pip dice que terminó pero no importa (p. ej. `gphoto2`): casi siempre faltan paquetes **apt** previos (`libgphoto2-dev`, SDL2 para Kivy). El instalador ya no ejecuta pip si apt requerido falló.
- **`Permission denied: '/dev/usb/lp2'`** al mover film: el usuario debe estar en el grupo `lp` y tener la regla udev instalada. Ejecutar de nuevo el instalador o manualmente:
  ```bash
  sudo usermod -aG lp $USER
  newgrp lp    # o cerrar sesión y volver a entrar
  ```
  Desenchufar y enchufar la impresora USB. Comprobar: `ls -l /dev/usb/lp*`
- En Ubuntu 24.04+, si `pip` rechaza instalar: el instalador añade `--break-system-packages` automáticamente; también puede usarse un venv (`python3 -m venv .venv && source .venv/bin/activate`).
- Si Kivy falla al importar tras pip, revisar que estén los paquetes SDL2 de la lista apt del instalador.
