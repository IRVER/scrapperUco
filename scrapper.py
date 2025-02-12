import requests
from bs4 import BeautifulSoup
import json
import os
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
import time
import subprocess

BASE_URL = "https://sede.uco.es/bouco/"
RESULTS_DIR = "results"
PROCESSED_IDS_FILE = os.path.join(RESULTS_DIR, "processed_ids.json")

# Configuración del bot de Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Toma el token desde la variable de entorno
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")  # Toma el canal desde la variable de entorno
GH_PAT = os.getenv("GH_PAT")

if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise ValueError("Faltan las variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHANNEL_ID")

os.makedirs(RESULTS_DIR, exist_ok=True)

# Cargar publicaciones ya enviadas
def cargar_ids_procesados():
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

# Guardar publicaciones ya enviadas
def guardar_ids_procesados(ids_procesados):
    with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids_procesados), f, indent=4, ensure_ascii=False)

async def send_to_telegram(bot, publicacion):
    """Envía un mensaje al canal de Telegram con los detalles del anuncio."""
    message = f" *Publicación: {publicacion['id']}*\n\n"
    message += f"*Titulo*: {publicacion['titulo']}\n\n"
    message += f"*Descripción*: {publicacion['descripcion']}\n"
    print(message)
    await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo="https://sede.uco.es/layout/logo-uco.png", caption=message,parse_mode=ParseMode.MARKDOWN)

def parse_uco_boletin(html_file):
    soup = BeautifulSoup(html_file, 'html.parser')
    publicaciones = []
    
    for row in soup.select("table.rich-table tbody tr.rich-table-row"):
        try:
            id_publicacion = row.select_one("td a.accesoTitulo").text.strip()
            titulo = row.select_one("td b a").text.strip()
            
            descripcion = None
            for td in row.select("td.width15"):
                if td.find("img", class_="rich-spacer"):
                    descripcion_td = td.find_next_sibling("td", class_="width80")
                    if descripcion_td:
                        label = descripcion_td.find("label")
                        if label:
                            descripcion = label.text.strip()
                            break
            
            enlace_descarga = row.select_one("td a[title='Descargar Documentos Publicados']")
            enlace_descarga = enlace_descarga["onclick"] if enlace_descarga else None

            publicaciones.append({
                "id": id_publicacion,
                "titulo": titulo,
                "descripcion": descripcion,
                "enlace_descarga": enlace_descarga
            })
        except AttributeError:
            continue  
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_file = os.path.join(RESULTS_DIR, "publicaciones.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(publicaciones, f, indent=4, ensure_ascii=False)
    
    print(f"Archivo guardado en: {output_file}")
    return publicaciones

async def scrape():
    """Realiza todo el flujo de extracción de datos."""
    print("Obteniendo la página principal...")
    response = requests.get(BASE_URL)

    if response.status_code != 200:
        print("Error al acceder a la página principal")
        return

    publicaciones = parse_uco_boletin(response.text)

    # Inicializar bot de Telegram
    bot = Bot(token=TELEGRAM_TOKEN)

    ids_procesados = cargar_ids_procesados()
    nuevos_ids = set()
    
    for publicacion in publicaciones:
        if publicacion['id'] not in ids_procesados:
            print("Enviando", publicacion['id'])
            await send_to_telegram(bot, publicacion)
            nuevos_ids.add(publicacion['id'])
    
    # Guardar los nuevos IDs procesados
    ids_procesados.update(nuevos_ids)
    guardar_ids_procesados(ids_procesados)

def guardar_cambios_git():
    """Guarda processed_ids.json en el repositorio con un commit automático usando GH_PAT."""
    try:
        # Configurar usuario para commits
        subprocess.run(["git", "config", "--global", "user.email", "github-actions@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Actions"], check=True)

        # Configurar la URL remota con el token GH_PAT
        repo_url = f"https://x-access-token:{GH_PAT}@github.com/IRVER/scrapperUco.git"
        subprocess.run(["git", "remote", "set-url", "origin", repo_url], check=True)

        # Añadir y hacer commit de los archivos modificados
        subprocess.run(["git", "add", PROCESSED_IDS_FILE, "results/publicaciones.json"], check=True)
        subprocess.run(["git", "commit", "-m", "Actualizar processed_ids.json con nuevas publicaciones"], check=True)

        # Hacer push al repositorio
        subprocess.run(["git", "push", "origin", "main"], check=True)

        print("Archivo processed_ids.json actualizado y subido al repositorio.")

    except subprocess.CalledProcessError:
        print("No hay cambios nuevos en processed_ids.json. No se hizo commit.")


if __name__ == "__main__":
    asyncio.run(scrape()) 
    guardar_cambios_git()
