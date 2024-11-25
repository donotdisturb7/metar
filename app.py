from flask import Flask, render_template, request, send_file
import avwx
from avwx.exceptions import BadStation, SourceError, InvalidRequest
from datetime import datetime
import pytz
import logging
import io

app = Flask(__name__)

# Configuration des logs
logging.basicConfig(level=logging.INFO)

AIRPORTS = {
    "LFPG": "Aéroport Charles de Gaulle",
    "LFPB": "Aéroport de Paris-Le Bourget",
    "LFPO": "Aéroport de Paris-Orly",
    "LFRN": "Aéroport de Rennes",
    "LFBD": "Aéroport de Bordeaux-Mérignac",
    "EGLL": "Londres-Heathrow (Royaume-Uni)",
    "EHAM": "Amsterdam-Schiphol (Pays-Bas)",
    "EDDF": "Francfort (Allemagne)",
    "LEMD": "Madrid-Barajas (Espagne)",
    "LIRF": "Rome Fiumicino (Italie)",
    "KATL": "Hartsfield-Jackson, Atlanta (États-Unis)",
    "KLAX": "Los Angeles (États-Unis)",
    "KJFK": "John F. Kennedy, New York (États-Unis)",
    "CYYZ": "Toronto Pearson (Canada)",
    "CYVR": "Vancouver (Canada)",
    "RJTT": "Tokyo Haneda (Japon)",
    "ZBAA": "Pékin Capitale (Chine)",
    "OMDB": "Dubaï (Émirats arabes unis)",
    "VIDP": "Delhi Indira Gandhi (Inde)",
    "WSSS": "Singapour Changi (Singapour)",
    "FAOR": "Johannesburg OR Tambo (Afrique du Sud)",
    "DNMM": "Lagos Murtala Muhammed (Nigeria)",
    "HAAB": "Addis-Abeba Bole (Éthiopie)",
    "YSSY": "Sydney-Kingsford Smith (Australie)",
    "NZAA": "Auckland (Nouvelle-Zélande)"
}

ERROR_MESSAGES = {
    "invalid_code": "Le code de la station doit contenir 4 caractères (code ICAO).",
    "bad_station": "Le code {station_code} est invalide ou non reconnu.",
    "fetch_error": "Erreur lors de la récupération du METAR : {error}"
}

def format_temperature(temp):
    """
    Convertit une température METAR (ex : M01) en un format lisible avec le signe négatif (ex : -1).
    """
    if temp.startswith('M'):
        return f"-{temp[1:]}"  # Remplace 'M' par '-' et garde les chiffres
    return temp  # Retourne tel quel si pas de 'M'


def decode_metar(metar_data, station_code):
    """Décode le rapport METAR en informations compréhensibles avec gestion des exceptions"""
    # METAR brut
    try:
        metar_brut = metar_data.raw  # Récupère le METAR brut
        metar_brut_info = f"METAR brut : {metar_brut}"
    except Exception as e:
        metar_brut_info = f"Impossible de récupérer le METAR brut : {e}"

    # Décodage du vent
    try:
        vent_direction = metar_data.wind_direction.repr
        vent_vitesse = metar_data.wind_speed.repr
        vent_info = f"Vent venant du {vent_direction}° à {vent_vitesse} nœuds."
    except AttributeError:
        vent_info = "Données sur le vent indisponibles."

    # Températures
    try:
        temperature = format_temperature(metar_data.temperature.repr)  # Utilise la fonction de formatage
        dew_point = format_temperature(metar_data.dewpoint.repr)  # Idem pour le point de rosée
        temperature_info = f"Température : {temperature}°C, Point de rosée : {dew_point}°C."
    except Exception as e:
        temperature_info = f"Données sur la température indisponibles : {e}"

   # Visibilité
    try:
        visibility = metar_data.visibility.repr  # Récupère la visibilité en tant que chaîne
        visibility_float = float(visibility) if visibility.isdigit() else None  # Convertir en float si possible
        
        if visibility == "CAVOK":
            visibility_info = "Visibilité : CAVOK (pas de phénomènes significatifs, visibilité supérieure à 10 km)."
        elif visibility_float is not None:
            # Détecter si l'on est en miles (pour les États-Unis et le Canada)
            if station_code.startswith(("K", "C")):  # États-Unis ('K') et Canada ('C')
                visibility_miles = visibility_float  # La visibilité est directement en miles
                visibility_info = f"Visibilité : {visibility_miles:.2f} miles."
            else:
                visibility_km = visibility_float / 1000  # Convertir en kilomètres pour les autres
                visibility_info = f"Visibilité : {visibility_km:.2f} km."
        else:
            visibility_info = f"Visibilité : {visibility} (format inconnu)."
    except Exception as e:
        visibility_info = f"Données sur la visibilité indisponibles : {e}"



    # Décodage de la pression atmosphérique
    try:
        pression = metar_data.altimeter.repr
        if pression.startswith('Q'):
            pression_info = f"Pression atmosphérique : {pression[1:]} hPa (hectopascals, système international)."
        elif pression.startswith('A'):
            pression_info = f"Pression atmosphérique : {pression[1:]} inHg (pouces de mercure, utilisé principalement aux USA)."
        else:
            pression_info = f"Pression atmosphérique : {pression} (unité non spécifiée)."
    except AttributeError:
        pression_info = "Données sur la pression atmosphérique indisponibles."

    # Décodage de l'heure d'observation
    try:
        time_repr = metar_data.time.repr
        day = int(time_repr[:2])  # Jour du mois
        hour = int(time_repr[2:4])  # Heure (UTC)
        minute = int(time_repr[4:6])

        now = datetime.utcnow()  # Date actuelle en UTC
        observation_time_utc = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)

        local_tz = pytz.timezone('America/Martinique')
        observation_time_local = observation_time_utc.replace(tzinfo=pytz.utc).astimezone(local_tz)

        heure_info = (
            f"Heure d'observation UTC : {observation_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC<br>"
            f"Heure locale (Martinique) : {observation_time_local.strftime('%Y-%m-%d %H:%M:%S')} (heure locale)"
        )
    except (AttributeError, ValueError):
        heure_info = "Données sur l'heure d'observation indisponibles."

    # Décodage de la couverture nuageuse avec interprétation
    try:
        clouds = metar_data.clouds  # Liste des couches nuageuses
        if not clouds:  # Si la liste est vide ou None
            clouds_info = "Couverture nuageuse : Ciel clair."
        else:
            cloud_layers = []
            coverage_map = {
                "FEW": "Quelques nuages (1-2/8 du ciel couvert)",
                "SCT": "Nuages épars (3-4/8 du ciel couvert)",
                "BKN": "Nuages fragmentés (5-7/8 du ciel couvert)",
                "OVC": "Ciel couvert (8/8 du ciel couvert)",
            }
            for layer in clouds:
                try:
                    # Récupérer les données pour chaque couche
                    coverage_code = getattr(layer, 'type', None)  # Type de nuages (FEW, SCT, etc.)
                    base = getattr(layer, 'base', None)  # Altitude en centaines de pieds
                    if coverage_code in coverage_map:
                        description = coverage_map[coverage_code]
                        if base is not None:
                            cloud_layers.append(f"{description}, à une altitude de {base * 100} pieds")
                        else:
                            cloud_layers.append(description)
                    elif coverage_code:  # Code inconnu mais présent
                        cloud_layers.append(f"Couverture non spécifiée ({coverage_code})")
                except Exception as e:
                    print(f"Erreur lors du traitement d'une couche nuageuse : {e}", file=sys.stderr)
            # Construire la description finale
            if cloud_layers:
                clouds_info = "Couverture nuageuse : " + ", ".join(cloud_layers) + "."
            else:
                clouds_info = "Données sur la couverture nuageuse indisponibles."
    except Exception as e:
        clouds_info = f"Données sur la couverture nuageuse indisponibles : {e}"



    # Construction finale des informations décodées
    metar_decoded = (
        f"{metar_brut_info}<br>"
        f"{vent_info}<br>"
        f"{temperature_info}<br>"
        f"{visibility_info}<br>"
        f"{pression_info}<br>"
        f"{clouds_info}<br>"
        f"{heure_info}<br>"
    )


    return metar_decoded


@app.route('/', methods=['GET', 'POST'])
def home():
    logging.info("Accès à la route /")
    metar_info = ""
    airport_name = ""
    station_code = ""
    if request.method == 'POST':
        station_code = request.form.get('station_code') or request.form.get('icao_list')
        logging.info(f"Formulaire soumis avec le code station : {station_code}")
        if len(station_code) != 4:
            metar_info = ERROR_MESSAGES["invalid_code"]
        else:
            try:
                metar = avwx.Metar(station_code)
                metar.update()
                metar_info = decode_metar(metar.data, station_code)
                airport_name = AIRPORTS.get(station_code, "Aéroport inconnu")
            except BadStation:
                metar_info = ERROR_MESSAGES["bad_station"].format(station_code=station_code)
            except (SourceError, InvalidRequest) as e:
                logging.error(f"Erreur lors de la récupération du METAR : {e}")
                metar_info = ERROR_MESSAGES["fetch_error"].format(error=e)

    return render_template('index.html', metar_info=metar_info, airport_name=airport_name, station_code=station_code)

@app.route('/download', methods=['POST'])
def download():
    logging.info("Accès à la route /download")
    station_code = request.form.get('station_code') or request.form.get('icao_list')
    if len(station_code) != 4:
        return "Le code de la station doit contenir 4 caractères (code ICAO).", 400

    try:
        metar = avwx.Metar(station_code)
        metar.update()
        metar_info = decode_metar(metar.data, station_code)
        airport_name = AIRPORTS.get(station_code, "Aéroport inconnu")
        report_content = "Rapport METAR pour " + airport_name + " (" + station_code + "):\n\n" + metar_info.replace('<br>', '\n')
        
        # Créer un fichier en mémoire
        buffer = io.BytesIO()
        buffer.write(report_content.encode('utf-8'))
        buffer.seek(0)
        
        return send_file(buffer, as_attachment=True, download_name=f"METAR_{station_code}.txt", mimetype='text/plain')
    except BadStation:
        return f"Le code {station_code} est invalide ou non reconnu.", 400
    except (SourceError, InvalidRequest) as e:
        logging.error(f"Erreur lors de la récupération du METAR : {e}")
        return f"Erreur lors de la récupération du METAR : {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
