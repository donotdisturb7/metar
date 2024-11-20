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

def decode_metar(metar_data, station_code):
    """Décode le rapport METAR en informations compréhensibles"""
    vent_info = f"Vent venant du {metar_data.wind_direction.repr}° à {metar_data.wind_speed.repr} nœuds."
    temperature_info = f"Température : {metar_data.temperature.repr}°C, Point de rosée : {metar_data.dewpoint.repr}°C."

    visibility = metar_data.visibility.repr
    if visibility == "CAVOK":
        visibility_info = "Visibilité : CAVOK (pas de phénomènes significatifs, visibilité supérieure à 10 km)."
    else:
        try:
            visibility_value = float(visibility.replace('SM', '').strip()) if 'SM' in visibility else int(visibility)
            if 'SM' in visibility or station_code.startswith('K'):
                visibility_info = f"Visibilité : {visibility_value:.2f} miles." if 'SM' in visibility else f"Visibilité : {visibility_value / 1609.34:.2f} miles."
            else:
                visibility_info = f"Visibilité : {visibility_value} mètres."
        except ValueError:
            visibility_info = f"Visibilité : {visibility} (unité non spécifiée)."

    pression_info = f"Pression atmosphérique : {metar_data.altimeter.repr[1:]} {'hPa' if metar_data.altimeter.repr.startswith('Q') else 'inHg'}."

    time_repr = metar_data.time.repr
    day, hour, minute = int(time_repr[:2]), int(time_repr[2:4]), int(time_repr[4:6])
    now = datetime.utcnow()
    observation_time_utc = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
    local_tz = pytz.timezone('America/Martinique')
    observation_time_local = observation_time_utc.replace(tzinfo=pytz.utc).astimezone(local_tz)

    heure_info = (
        f"Heure d'observation UTC : {observation_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC<br>"
        f"Heure locale (Martinique) : {observation_time_local.strftime('%Y-%m-%d %H:%M:%S')} (heure locale)"
    )

    return f"{vent_info}<br>{temperature_info}<br>{visibility_info}<br>{pression_info}<br>{heure_info}<br>"

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
        report_content = f"Rapport METAR pour {airport_name} ({station_code}):\n\n{metar_info.replace('<br>', '\n')}"
        
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
