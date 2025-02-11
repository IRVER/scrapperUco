import requests
from bs4 import BeautifulSoup
import json
import os
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
import time
from flask import Flask
from threading import Thread

BASE_URL = "https://sede.uco.es/bouco/"
RESULTS_DIR = "results"
PROCESSED_IDS_FILE = os.path.join(RESULTS_DIR, "processed_ids.json")

# Configuración del bot de Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Toma el token desde la variable de entorno
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")  # Toma el canal desde la variable de entorno

if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise ValueError("Faltan las variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHANNEL_ID")


os.makedirs(RESULTS_DIR, exist_ok=True)


async def send_to_telegram(bot, publicacion):
    """Envía un mensaje al canal de Telegram con los detalles del anime."""
    message = f" *Publicación: {publicacion['id']}*\n\n"
    message += f"*Titulo*: {publicacion['titulo']}\n\n"
    message += f"*Descripción*: {publicacion['descripcion']}\n"
    print(message)
    await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo="https://sede.uco.es/layout/logo-uco.png", caption=message,parse_mode=ParseMode.MARKDOWN)


def descargar_documento(enlace_descarga, id_publicacion, output_dir="results"):
    """
    Descarga el documento usando el enlace extraído.
    """
    
    if not enlace_descarga:
        print(f"No se encontró enlace de descarga para {id_publicacion}")
        return None
    
    doc_id = enlace_descarga.split("'")[1] if "'" in enlace_descarga else None
    if not doc_id:
        print(f"No se pudo extraer el ID del documento para {id_publicacion}")
        return None
    
    response = requests.post(BASE_URL, data={"idBandejaAnuncios:j_idcl": doc_id})
    
    if response.status_code == 200:
        file_path = os.path.join(output_dir, f"{id_publicacion}.pdf")
        with open(file_path, "wb") as file:
            file.write(response.content)
        print(f"Documento descargado: {file_path}")
        return file_path
    else:
        print(f"Error al descargar {id_publicacion}")
        return None


def parse_uco_boletin(html_file):
    
    soup = BeautifulSoup(html_file, 'html.parser')
    
    publicaciones = []
    
    # Encontrar todas las publicaciones en la tabla de anuncios
    for row in soup.select("table.rich-table tbody tr.rich-table-row"):
        try:
            id_publicacion = row.select_one("td a.accesoTitulo").text.strip()
            titulo = row.select_one("td b a").text.strip()
            # Buscar la descripción correcta
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
            continue  # Si falta algún dato, se salta la publicación
    
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
    
    for publicacion in publicaciones:
        print("enviando", publicacion['id'])
        await send_to_telegram(bot, publicacion)
    


app = Flask(__name__)


@app.route("/")
def home():
    return "Bot activo"


async def main():
    while True:
        await scrape()
        print("Esperando 8 horas para la próxima ejecución...")
        await asyncio.sleep(8 * 60 * 60)  # Espera asíncrona

if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=8080)

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    asyncio.run(main())  # Corrección aquí
