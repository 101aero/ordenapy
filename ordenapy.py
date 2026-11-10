
"""
ORDENAPY v1.0 - InformatOLI

Paso 2: Analisis, vista previa y organizacion.

- Detecta Descargas en Windows 11 y Ubuntu.
- Permite introducir otra carpeta.
- Clasifica sin modificar inicialmente.
- Muestra una vista previa de los movimientos.
- Organiza solamente tras confirmacion.
- Evita sobrescribir archivos existentes.
- Ignora temporales, ocultos y subcarpetas.
- Guarda un registro JSONL de movimientos.
"""

import json
import os
import shutil

from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4


# ============================================
# CONFIGURACION
# ============================================

CATEGORIAS = {
    "Documentos": {
        ".pdf", ".doc", ".docx", ".txt",
        ".xls", ".xlsx", ".ppt", ".pptx"
    },
    "Imagenes": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp"
    },
    "Videos": {
        ".mp4", ".avi", ".mkv", ".mov"
    },
    "Musica": {
        ".mp3", ".wav", ".flac", ".ogg"
    },
    "Comprimidos": {
        ".zip", ".rar", ".7z", ".tar", ".gz"
    },
    "Instaladores": {
        ".exe", ".msi", ".deb", ".rpm"
    },
    "Codigo": {
        ".py", ".pas", ".java", ".js",
        ".html", ".css", ".json"
    },
    "Otros": set()
}

TEMPORALES = {
    ".tmp", ".temp", ".part", ".partial",
    ".crdownload", ".download", ".swp",
    ".aria2", ".filepart"
}


# ============================================
# DETECTAR DESCARGAS
# ============================================

def detectar_descargas():

    inicio = Path.home()
    candidatas = []

    if os.name == "nt":

        try:
            import winreg

            clave_registro = (
                r"Software\Microsoft\Windows\CurrentVersion"
                r"\Explorer\User Shell Folders"
            )

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                clave_registro
            ) as clave:

                ruta, _ = winreg.QueryValueEx(
                    clave,
                    "{374DE290-123F-4565-9164-39C4925E467B}"
                )

                candidatas.append(
                    Path(os.path.expandvars(ruta))
                )

        except OSError:
            pass

    else:

        archivo_xdg = inicio / ".config" / "user-dirs.dirs"

        try:
            lineas = archivo_xdg.read_text(
                encoding="utf-8"
            ).splitlines()

            for linea in lineas:

                linea = linea.strip()

                if linea.startswith("XDG_DOWNLOAD_DIR="):

                    ruta = linea.split("=", 1)[1]
                    ruta = ruta.strip().strip('"')
                    ruta = ruta.replace("$HOME", str(inicio))

                    candidatas.append(Path(ruta))

        except OSError:
            pass

    candidatas.extend([
        inicio / "Downloads",
        inicio / "Descargas"
    ])

    for carpeta in candidatas:

        if carpeta != inicio and carpeta.is_dir():
            return carpeta

    return None


# ============================================
# SELECCIONAR CARPETA
# ============================================

def seleccionar_carpeta():

    descargas = detectar_descargas()

    print("\nSELECCION DE CARPETA")
    print("-" * 45)

    if descargas:

        print(f"\nDescargas detectada: {descargas}")

        print("\n1. Usar Descargas")
        print("2. Introducir otra carpeta")
        print("0. Salir")

        opcion = input("\nOpcion [1]: ").strip()

        if opcion in ("", "1"):
            return descargas

        if opcion == "0":
            return None

        if opcion != "2":
            print("Opcion no valida.")
            return None

    else:
        print("\nNo se detecta Descargas.")
        print("Introduce otra ruta.")

    ruta = input("\nRuta de la carpeta: ").strip()
    ruta = ruta.strip('"').strip("'")

    return Path(ruta).expanduser() if ruta else None


# ============================================
# IDENTIFICAR TEMPORALES
# ============================================

def es_temporal(archivo):

    nombre = archivo.name.lower()

    return (
        archivo.suffix.lower() in TEMPORALES
        or nombre.startswith(("~$", ".~lock", "."))
        or nombre in {"thumbs.db", "desktop.ini"}
    )


# ============================================
# CLASIFICAR ARCHIVO
# ============================================

def obtener_categoria(archivo):

    extension = archivo.suffix.lower()

    for categoria, extensiones in CATEGORIAS.items():

        if extension in extensiones:
            return categoria

    return "Otros"


# ============================================
# EVITAR NOMBRES DUPLICADOS
# ============================================

def ocupado(ruta, reservados):

    return (
        ruta.exists()
        or ruta.is_symlink()
        or str(ruta).casefold() in reservados
    )


def elegir_destino(carpeta_destino, nombre, reservados):

    original = Path(nombre)
    candidato = carpeta_destino / nombre

    numero = 1

    while ocupado(candidato, reservados):

        nuevo_nombre = (
            f"{original.stem} ({numero})"
            f"{original.suffix}"
        )

        candidato = carpeta_destino / nuevo_nombre

        numero += 1

    reservados.add(str(candidato).casefold())

    return candidato


# ============================================
# ANALIZAR SIN MODIFICAR
# ============================================

def analizar(carpeta):

    plan = []
    errores = []
    ignorados = 0
    reservados = set()

    script_actual = Path(__file__).resolve()

    archivos = sorted(
        carpeta.iterdir(),
        key=lambda ruta: ruta.name.casefold()
    )

    for archivo in archivos:

        try:

            # No entrar en subcarpetas ni enlaces
            if archivo.is_symlink() or not archivo.is_file():
                continue

            # No organizar el propio script ni temporales
            if (
                archivo.resolve() == script_actual
                or es_temporal(archivo)
            ):
                ignorados += 1
                continue

            categoria = obtener_categoria(archivo)
            carpeta_destino = carpeta / categoria

            # No utilizar destinos que sean enlaces
            # ni archivos en lugar de carpetas
            if (
                carpeta_destino.is_symlink()
                or (
                    carpeta_destino.exists()
                    and not carpeta_destino.is_dir()
                )
            ):

                errores.append(
                    f"{archivo.name}: destino no seguro"
                )
                continue

            destino = elegir_destino(
                carpeta_destino,
                archivo.name,
                reservados
            )

            datos = archivo.stat()

            plan.append((
                archivo,
                destino,
                categoria,
                datos.st_size,
                datos.st_mtime_ns
            ))

        except OSError as error:

            errores.append(
                f"{archivo.name}: {error}"
            )

    return plan, ignorados, errores


# ============================================
# MOSTRAR VISTA PREVIA
# ============================================

def mostrar_prevision(carpeta, plan, ignorados, errores):

    print("\n" + "=" * 45)
    print("           RESULTADO DEL ANALISIS")
    print("=" * 45)

    print(f"\nCarpeta: {carpeta}\n")

    conteo = Counter(
        elemento[2] for elemento in plan
    )

    for categoria in CATEGORIAS:

        print(
            f"{categoria:<20} {conteo[categoria]:>5}"
        )

    print("-" * 45)

    print(f"{'TOTAL':<20} {len(plan):>5}")

    print(f"\nIgnorados: {ignorados}")
    print(f"Errores: {len(errores)}")

    for error in errores:
        print(f"AVISO: {error}")

    print("\nVISTA PREVIA DE MOVIMIENTOS")
    print("-" * 45)

    for origen, destino, _, _, _ in plan:

        print(
            f"{origen.name} -> "
            f"{destino.parent.name}/{destino.name}"
        )

    print("\nTodavia NO se ha modificado nada.")


# ============================================
# REGISTRAR OPERACION
# ============================================

def registrar(registro, evento, origen, destino):

    entrada = {
        "evento": evento,
        "fecha": datetime.now().isoformat(
            timespec="seconds"
        ),
        "origen": str(origen),
        "destino": str(destino)
    }

    registro.write(
        json.dumps(
            entrada,
            ensure_ascii=False
        ) + "\n"
    )

    registro.flush()
    os.fsync(registro.fileno())


# ============================================
# MOVER SIN SOBRESCRIBIR
# ============================================

def mover_exclusivo(origen, destino):

    """
    Crea el destino de forma exclusiva.

    Si la copia falla, intenta eliminar
    el destino parcial y conserva el origen.
    """

    creado = False

    try:

        # xb impide sobrescribir un archivo existente
        with destino.open("xb") as salida:

            creado = True

            with origen.open("rb") as entrada:

                shutil.copyfileobj(
                    entrada,
                    salida,
                    1024 * 1024
                )

            salida.flush()
            os.fsync(salida.fileno())

        # Conservar metadatos del archivo
        shutil.copystat(origen, destino)

        # Eliminar origen solo tras copiar correctamente
        origen.unlink()

    except OSError:

        if creado and origen.exists():

            try:
                destino.unlink()
            except OSError:
                pass

        raise


# ============================================
# ORGANIZAR ARCHIVOS
# ============================================

def organizar(carpeta, plan):

    historial = carpeta / ".ordenapy"

    if (
        historial.is_symlink()
        or (
            historial.exists()
            and not historial.is_dir()
        )
    ):

        print("\nERROR: directorio de registro no seguro.")
        return

    try:

        historial.mkdir(exist_ok=True)

        nombre_registro = (
            f"registro_{datetime.now():%Y%m%d_%H%M%S}_"
            f"{uuid4().hex[:8]}.jsonl"
        )

        ruta_registro = historial / nombre_registro

        movidos = 0
        fallidos = 0

        with ruta_registro.open(
            "x",
            encoding="utf-8"
        ) as registro:

            for origen, destino, _, tamano, fecha_ns in plan:

                try:

                    if (
                        origen.is_symlink()
                        or not origen.is_file()
                    ):
                        raise OSError(
                            "Archivo desaparecido o no valido"
                        )

                    # Comprobar si cambia tras el analisis
                    estado = origen.stat()

                    if (
                        estado.st_size != tamano
                        or estado.st_mtime_ns != fecha_ns
                    ):
                        raise OSError(
                            "El archivo cambia desde el analisis"
                        )

                    if destino.parent.is_symlink():
                        raise OSError(
                            "Destino es un enlace simbolico"
                        )

                    destino.parent.mkdir(exist_ok=True)

                    if (
                        destino.exists()
                        or destino.is_symlink()
                    ):
                        raise FileExistsError(
                            "El destino ya esta ocupado"
                        )

                    # Registrar intencion antes del movimiento
                    registrar(
                        registro,
                        "preparado",
                        origen,
                        destino
                    )

                    mover_exclusivo(origen, destino)

                    # Registrar movimiento completado
                    registrar(
                        registro,
                        "movido",
                        origen,
                        destino
                    )

                    movidos += 1

                    print(
                        f"OK: {origen.name} -> "
                        f"{destino.parent.name}/{destino.name}"
                    )

                except OSError as error:

                    fallidos += 1

                    print(
                        f"ERROR: {origen.name}: {error}"
                    )

        print("\n" + "=" * 45)
        print("         ORGANIZACION FINALIZADA")
        print("=" * 45)

        print(f"Archivos movidos: {movidos}")
        print(f"Errores: {fallidos}")

        print(f"\nRegistro: {ruta_registro}")

    except OSError as error:

        print(
            f"\nERROR al crear o escribir registro: {error}"
        )


# ============================================
# PROGRAMA PRINCIPAL
# ============================================

def main():

    print("=" * 45)
    print("             ORDENAPY v1.0")
    print("         Organizador de archivos")
    print("              InformatOLI")
    print("=" * 45)

    carpeta = seleccionar_carpeta()

    if carpeta is None:
        print("\nOperacion cancelada.")
        return

    if not carpeta.is_dir():
        print("\nERROR: carpeta no valida.")
        return

    try:

        plan, ignorados, errores = analizar(carpeta)

    except OSError as error:

        print(f"\nERROR al analizar: {error}")
        return

    mostrar_prevision(
        carpeta,
        plan,
        ignorados,
        errores
    )

    if not plan:
        print("\nNo hay archivos para organizar.")
        return

    print("\nATENCION:")
    print("La siguiente accion mueve los archivos.")
    print("Las subcarpetas existentes no se recorren.")

    confirmacion = input(
        "\nEscribe ORGANIZAR para continuar: "
    ).strip()

    if confirmacion != "ORGANIZAR":

        print("\nOperacion cancelada.")
        print("No se ha movido ningun archivo.")
        return

    organizar(carpeta, plan)


# ============================================
# INICIO
# ============================================

if __name__ == "__main__":
    main()
