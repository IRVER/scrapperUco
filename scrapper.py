import requests
from bs4 import BeautifulSoup
import json
import os
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
import time
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

BASE_URL = "https://sede.uco.es/bouco/"
RESULTS_DIR = "results"
PROCESSED_IDS_FILE = os.path.join(RESULTS_DIR, "processed_ids.json")
GOOGLE_DRIVE_FILE_ID = "1FxVf_5IOpL8fB0BAsQdLHp6w7iK35iFE"

# Configuración del bot de Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise ValueError("Faltan las variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHANNEL_ID")

os.makedirs(RESULTS_DIR, exist_ok=True)

# 🔹 Autenticación con Google Drive
def autenticar_google_drive():
    """Autenticación automática con cuenta de servicio."""
    scope = ["https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    gauth = GoogleAuth()
    gauth.credentials = creds
    return GoogleDrive(gauth)

# 🔹 Descargar `processed_ids.json` desde Google Drive
def descargar_json_drive():
    """Descarga el archivo JSON desde Google Drive."""
    drive = autenticar_google_drive()
    file = drive.CreateFile({'id': GOOGLE_DRIVE_FILE_ID})
    file.GetContentFile(PROCESSED_IDS_FILE)
    print(f"📥 Archivo descargado: {PROCESSED_IDS_FILE}")

# 🔹 Subir `processed_ids.json` actualizado a Google Drive
def subir_json_drive():
    """Sube el archivo JSON actualizado a Google Drive."""
    drive = autenticar_google_drive()
    file = drive.CreateFile({'id': GOOGLE_DRIVE_FILE_ID})
    file.SetContentFile(PROCESSED_IDS_FILE)
    file.Upload()
    print(f"📤 Archivo actualizado en Google Drive: {PROCESSED_IDS_FILE}")

# 🔹 Cargar IDs procesados
def cargar_ids_procesados():
    """Carga los IDs procesados desde Google Drive."""
    try:
        descargar_json_drive()  # Descargar antes de leer
        with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        print("⚠️ No se encontró processed_ids.json, creando uno nuevo.")
        return set()

# 🔹 Guardar nuevos IDs en Google Drive
def guardar_ids_procesados(ids_procesados):
    """Guarda los nuevos IDs y los sube a Google Drive."""
    with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids_procesados), f, indent=4, ensure_ascii=False)
    subir_json_drive()  # Subir después de escribir

# 🔹 Enviar publicaciones a Telegram
async def send_to_telegram(bot, publicacion):
    """Envía un mensaje al canal de Telegram con los detalles del anuncio."""
    message = f"📢 *{publicacion['id']}*\n\n"
    message += f"📌 *Título*: {publicacion['titulo']}\n\n"
    message += f"📝 *Descripción*: {publicacion['descripcion']}\n"

    await bot.send_photo(
        chat_id=TELEGRAM_CHANNEL_ID, 
        photo="https://sede.uco.es/layout/logo-uco.png", 
        caption=message,
        parse_mode=ParseMode.MARKDOWN
    )
    print(f"📤 Enviado a Telegram: {publicacion['id']}")

# 🔹 Scraper de UCO
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

    with open(os.path.join(RESULTS_DIR, "publicaciones.json"), "w", encoding="utf-8") as f:
        json.dump(publicaciones, f, indent=4, ensure_ascii=False)

    return publicaciones

# 🔹 Flujo principal del scraper
async def scrape():
    print("📡 Obteniendo la página principal...")
    response = requests.get(BASE_URL)

    if response.status_code != 200:
        print("❌ Error al acceder a la página principal")
        return

    publicaciones = parse_uco_boletin(response.text)

    bot = Bot(token=TELEGRAM_TOKEN)
    ids_procesados = cargar_ids_procesados()
    nuevos_ids = set()
    
    for publicacion in publicaciones:
        if publicacion['id'] not in ids_procesados:
            await send_to_telegram(bot, publicacion)
            nuevos_ids.add(publicacion['id'])
    
    ids_procesados.update(nuevos_ids)
    guardar_ids_procesados(ids_procesados)

if __name__ == "__main__":
    asyncio.run(scrape()) 
