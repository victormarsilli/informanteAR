import feedparser
import requests
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from groq import Groq
import datetime
from supabase import create_client
from http.server import BaseHTTPRequestHandler
import os
import traceback

# Configuración de Informante AR
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)



def noticia_ya_existe(id_rss):
    # Buscamos en la nube de Supabase
    query = supabase.table("posts").select("id_noticia").eq("id_noticia", id_rss).execute()
    return len(query.data) > 0

def registrar_noticia(id_rss):
    # Guardamos el link para no repetirlo
    supabase.table("posts").insert({"id_noticia": id_rss}).execute()
    
# --- 1. CONFIGURACIÓN ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODELO = "llama-3.1-8b-instant"

# Datos Blogger
EMAIL_DESTINO_BLOGGER = os.environ.get("EMAIL_DESTINO_BLOGGER")
MI_GMAIL = os.environ.get("MI_GMAIL")
MI_GMAIL_APP_PASSWORD = os.environ.get("MI_GMAIL_APP_PASSWORD")
URL_BLOG = os.environ.get("URL_BLOG")

# Datos Facebook (IMPORTANTE: Usa el token de PÁGINA que sacamos)
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")

client = Groq(api_key=GROQ_API_KEY)

# --- 3. REDACCIÓN CON IA ---
def transformar_con_ia(titulo, resumen):
    try:
        if any(palabra in titulo.lower() for palabra in ["quiniela", "sorteo", "lotería"]):
            return None, None

        prompt = f"""
        Actúa como un experto en SEO y periodista digital. Reescribe esta noticia para el blog 'informARte' optimizando para motores de búsqueda.
        Título original: {titulo}
        Resumen: {resumen}
        
        REGLAS DE FORMATO Y SEO:
        1. Primera línea: Título atractivo, clickbait moderado y con palabras clave (texto plano, sin etiquetas).
        2. Estructura HTML: Usa <h2> para subtítulos (importante para SEO), <p> para párrafos, <ul>/<li> para listas.
        3. Intro SEO: El primer párrafo debe ser un resumen impactante (Lead) en <strong> que contenga las palabras clave principales.
        4. Legibilidad: Usa párrafos cortos y lenguaje natural, dale un estilo moderno.
        5. Localización: Si menciona Comodoro Rivadavia, Chubut o Argentina, resáltalo.
        6. evita poner tu pensamientos o razonamiento como por ejemplo titulo atractivo como texto
        """
        
        completion = client.chat.completions.create(
            model=MODELO,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        
        respuesta = completion.choices[0].message.content
        lineas = respuesta.split('\n')
        nuevo_titulo = lineas[0].replace('**', '').replace('Título:', '').strip()
        cuerpo = "\n".join(lineas[1:])
        return nuevo_titulo, cuerpo
    except: return None, None

# --- 4. PUBLICACIÓN EN BLOGGER ---
def publicar_en_blogger(titulo, contenido_html, imagen_url=None):
    msg = MIMEMultipart()
    msg['From'] = MI_GMAIL
    msg['To'] = EMAIL_DESTINO_BLOGGER
    msg['Subject'] = titulo
    
    # --- ESTILOS VISUALES (CSS INLINE) ---
    # Definimos estilos para que se vea profesional en cualquier dispositivo
    estilo_contenedor = "font-family: 'Georgia', 'Times New Roman', serif; font-size: 18px; line-height: 1.8; color: #2c3e50; max-width: 800px; margin: 0 auto;"
    estilo_h2 = "color: #d35400; font-family: 'Helvetica', 'Arial', sans-serif; font-weight: bold; margin-top: 30px; border-bottom: 2px solid #f39c12; padding-bottom: 5px;"
    estilo_img = "width: 100%; height: auto; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 20px;"
    estilo_footer = "background-color: #ecf0f1; padding: 20px; border-radius: 10px; margin-top: 40px; font-family: 'Arial', sans-serif; font-size: 15px; text-align: center; color: #7f8c8d;"

    # Inyectamos los estilos en las etiquetas que genera la IA
    contenido_estilizado = contenido_html.replace('<h2>', f'<h2 style="{estilo_h2}">')
    contenido_estilizado = contenido_estilizado.replace('<h3>', f'<h2 style="{estilo_h2}">') # Normalizamos a H2
    
    # Construimos el HTML final
    cuerpo_final = f'<div style="{estilo_contenedor}">'
    if imagen_url:
        # IMPORTANTE SEO: Agregamos el atributo 'alt' con el título para que Google entienda la imagen
        cuerpo_final += f'<img src="{imagen_url}" alt="{titulo}" style="{estilo_img}" />'
    
    cuerpo_final += f'<div>{contenido_estilizado}</div>'
    cuerpo_final += f'<div style="{estilo_footer}">📢 <strong>¡Gracias por leer!</strong><br>Si te sirvió esta información, compartila con tus amigos.<br><em>Seguinos en <a href="https://www.facebook.com/Informante.ar" style="color: #3b5998; text-decoration: none; font-weight: bold;">Facebook</a> y visitá nuestro <a href="{URL_BLOG}" style="color: #e67e22; text-decoration: none; font-weight: bold;">Blog</a> para más noticias de Comodoro y el país.</em></div>'
    cuerpo_final += '</div>'
    
    msg.attach(MIMEText(cuerpo_final, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587); server.starttls()
        server.login(MI_GMAIL, MI_GMAIL_APP_PASSWORD)
        server.sendmail(MI_GMAIL, EMAIL_DESTINO_BLOGGER, msg.as_string())
        server.quit()
        return True
    except: return False

def publicar_en_facebook(titulo, cuerpo_ia, imagen_url, hashtags=""):
    # Mejoramos el formato: convertimos etiquetas HTML útiles a texto antes de limpiar
    texto_formateado = cuerpo_ia.replace('<li>', '• ').replace('</li>', '\n')
    texto_formateado = texto_formateado.replace('<p>', '').replace('</p>', '\n')
    texto_formateado = texto_formateado.replace('<br>', '\n').replace('<br/>', '\n')
    
    # Limpiamos el resto de etiquetas HTML
    texto_limpio = re.sub('<[^<]+?>', '', texto_formateado)
    texto_fb = "\n\n".join([line.strip() for line in texto_limpio.splitlines() if line.strip()])
    
    # CTA (Llamada a la acción) más fuerte para generar CLICS (Dinero)
    mensaje_final = f"📌 {titulo}\n\n{texto_fb}\n\n👇 LEÉ LA NOTA COMPLETA ACÁ 👇\n{URL_BLOG}\n\n{hashtags}"
    
    # Lógica para imagen: Usamos /photos si hay imagen (se ve más grande y bonita), sino /feed
    if imagen_url:
        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
        payload = {
            'message': mensaje_final,
            'url': imagen_url,
            'access_token': FB_PAGE_TOKEN
        }
    else:
        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        payload = {
            'message': mensaje_final,
            'access_token': FB_PAGE_TOKEN
        }
    
    try:
        r = requests.post(url, data=payload)
        resultado = r.json()
        if r.status_code == 200:
            print("✅ ¡Publicado en Facebook con éxito!")
        else:
            # Si vuelve a fallar, el error nos dirá exactamente qué permiso falta
            error_info = resultado.get('error', {})
            print(f"⚠️ Detalle del error: {error_info.get('message', resultado) if isinstance(error_info, dict) else error_info}")
    except Exception as e:
        print(f"❌ Error conexión FB: {e}")

# --- FUNCION AUXILIAR: HASHTAGS ---
def obtener_hashtags(url_fuente):
    # Asigna hashtags según de dónde viene la noticia para ganar viralidad
    if "adnsur" in url_fuente or "elpatagonico" in url_fuente or "elcomodorense" in url_fuente:
        return "#Comodoro #Chubut #NoticiasLocales #Patagonia"
    elif "ole.com" in url_fuente or "tycsports" in url_fuente:
        return "#Deportes #FutbolArgentino #Argentina"
    elif "diarioshow" in url_fuente or "ciudad.com" in url_fuente or "pronto" in url_fuente:
        return "#Espectaculos #GranHermano #Farandula #Chimentos"
    elif "clarin" in url_fuente and "musica" in url_fuente:
        return "#Musica #Artistas #Show"
    elif "ambito" in url_fuente or "lanacion" in url_fuente:
        return "#Economia #Dolar #Finanzas"
    else:
        return "#Actualidad #Argentina #Noticias"

# --- 5. FUNCION CLIMA ---
def publicar_clima():
    hoy = datetime.date.today()
    id_clima = f"clima_{hoy}"
    
    # Verificar si ya publicamos el clima hoy para no repetir
    if noticia_ya_existe(id_clima):
        return

    print("🌤️ Obteniendo datos del clima para Comodoro...")
    try:
        # API Open-Meteo (Gratis) - Coordenadas de Comodoro Rivadavia
        url = "https://api.open-meteo.com/v1/forecast?latitude=-45.8641&longitude=-67.4966&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=1"
        r = requests.get(url)
        data = r.json()
        
        daily = data.get('daily', {})
        max_temp = daily['temperature_2m_max'][0]
        min_temp = daily['temperature_2m_min'][0]
        lluvia = daily['precipitation_probability_max'][0]
        
        titulo = f"🌦️ El Clima en Comodoro - {hoy.strftime('%d/%m/%Y')}"
        cuerpo = f"<p><strong>¡Buenos días Comodoro!</strong> Así estará el tiempo hoy:</p><ul><li><strong>Mínima:</strong> {min_temp}°C ❄️</li><li><strong>Máxima:</strong> {max_temp}°C ☀️</li><li><strong>Probabilidad de lluvia:</strong> {lluvia}% ☔</li></ul><p>¡Que tengas una excelente jornada!</p>"
        imagen_clima = "https://cdn-icons-png.flaticon.com/512/1163/1163661.png" # Icono genérico de clima
        hashtags_clima = "#Clima #ComodoroRivadavia #Tiempo #Pronostico"
        
        if publicar_en_blogger(titulo, cuerpo, imagen_clima):
            print("✅ Clima publicado en Blogger")
            publicar_en_facebook(titulo, cuerpo, imagen_clima, hashtags_clima)
            registrar_noticia(id_clima)
    except Exception as e:
        print(f"❌ Error obteniendo clima: {e}")

# --- 5. FUNCIÓN PRINCIPAL DEL BOT ---
def ejecutar_bot(url_rss):
    print(f"Analizando fuente: {url_rss}")
    try:
        feed = feedparser.parse(url_rss)
    except Exception as e:
        print(f"Error leyendo RSS: {e}")
        return

    # Procesamos las 2 primeras noticias para probar
    for entry in feed.entries[:2]:
        guid = entry.link
        
        # Verificar si ya existe en la base de datos
        if noticia_ya_existe(guid):
            continue
            
        print(f"Procesando: {entry.title}")
        
        # Intentar obtener imagen para Facebook
        imagen = ""
        if hasattr(entry, 'media_content') and entry.media_content:
            imagen = entry.media_content[0]['url']
        elif hasattr(entry, 'enclosures') and entry.enclosures:
            imagen = entry.enclosures[0]['href']
            
        # Generar contenido con IA
        nuevo_titulo, cuerpo = transformar_con_ia(entry.title, getattr(entry, 'summary', ''))
        
        # Obtener hashtags según la fuente
        tags = obtener_hashtags(url_rss)
        
        if nuevo_titulo and cuerpo:
            if publicar_en_blogger(nuevo_titulo, cuerpo, imagen):
                print("✅ Publicado en Blogger")
                publicar_en_facebook(nuevo_titulo, cuerpo, imagen, tags)
                registrar_noticia(guid)
                # time.sleep(5) # Pausa eliminada para evitar timeout en Vercel

# --- 6. EJECUCIÓN MULTI-FUENTE ---
def main_process():
    lista_fuentes = [
        # --- LOCALES (COMODORO / CHUBUT) ---
        "https://www.adnsur.com.ar/rss/feed.xml",
        "https://www.elpatagonico.com/rss/pages/chubut.xml",
        "https://elcomodorense.net/feed/",
        "https://radio3cadenapatagonia.com.ar/feed/",
        
        # --- FINANZAS ---
        "https://www.ambito.com/rss/pages/finanzas.xml",
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/?outputType=xml",
        
        # --- TECNOLOGÍA ---
        "https://www.clarin.com/rss/tecnologia/",
        "https://www.perfil.com/rss/tecnologia.xml",
        
        # --- SOCIEDAD (Tendencias y Viral) ---
        "https://www.infobae.com/feeds/rss/sociedad.xml",
        "https://tn.com.ar/rss/sociedad/",

        # --- ESPECTÁCULOS, CHIMENTOS Y GRAN HERMANO ---
        "https://www.diarioshow.com/rss/pages/espectaculos.xml", # Fuente principal de chimentos
        "https://www.ciudad.com.ar/rss", # Ciudad Magazine (Cubre mucho GH)
        "https://www.pronto.com.ar/rss/feed.xml", # Revista Pronto

        # --- MÚSICA ---
        "https://www.clarin.com/rss/espectaculos/musica/",
        
        # --- DEPORTES ---
        "https://www.ole.com.ar/rss/ultimas-noticias/", # Diario Olé
        "https://www.tycsports.com/rss"
    ]
    
    total_revisadas = 0
    print("--- Iniciando ciclo de noticias vIcmAr ---")
    
    # Publicar clima (se ejecuta una vez al día)
    publicar_clima()
    
    for url in lista_fuentes:
        ejecutar_bot(url)
        total_revisadas += 1
    
    print(f"\n✅ Ciclo completado. Se revisaron {total_revisadas} fuentes de noticias.")
    print(f"Hora de finalización: {time.ctime()}")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Evitar ejecución doble por favicon del navegador
        if self.path == '/favicon.ico':
            self.send_response(200)
            self.end_headers()
            return

        try:
            main_process()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write("Ejecucion completada con éxito".encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            error_msg = f"Error en la ejecución:\n{str(e)}\n\n{traceback.format_exc()}"
            self.wfile.write(error_msg.encode('utf-8'))