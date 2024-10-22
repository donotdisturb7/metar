from flask import Flask, render_template, request, redirect, url_for
import avwx # Bibliothèque pour traiter les données METAR
from datetime import datetime
import pytz # Pour la gestion des fuseaux horaires
import sys





app = Flask(__name__) # Crée l'instance de l'application Flask


def decode_metar(metar_data):
    vent_direction = metar_data.wind_direction.repr
    vent_vitesse = metar_data.wind_speed.repr
    vent_info = f"Vent venant du {vent_direction}° à {vent_vitesse} nœuds."

    temperature = metar_data.temperature.repr
    dew_point = metar_data.dewpoint.repr
    temperature_info = f"Température : {temperature}°C, Point de rosée : {dew_point}°C."

    visibility = metar_data.visibility.repr
    if visibility == "CAVOK":
        visibility_info = "Visibilité : CAVOK (pas de phénomènes significatifs, visibilité supérieure à 10 km)."
    else:
        visibility_info = f"Visibilité : {visibility} mètres."

    pression = metar_data.altimeter.repr
    pression_info = f"Pression atmosphérique : {pression} hPa."

    time_repr = metar_data.time.repr
    day = int(time_repr[:2])
    hour = int(time_repr[2:4])
    minute = int(time_repr[4:6])

    now = datetime.utcnow()
    observation_time_utc = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)

    local_tz = pytz.timezone('America/Martinique')
    observation_time_local = observation_time_utc.replace(tzinfo=pytz.utc).astimezone(local_tz)

    heure_info = (
        f"Heure d'observation UTC : {observation_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC<br>"
        f"Heure locale (Martinique) : {observation_time_local.strftime('%Y-%m-%d %H:%M:%S')} (heure locale)"
    )

    metar_decoded = (
        f"{vent_info}<br>"
        f"{temperature_info}<br>"
        f"{visibility_info}<br>"
        f"{pression_info}<br>"
        f"{heure_info}<br>"
    )

    return metar_decoded

@app.route('/', methods=['GET', 'POST'])
def home():
    metar_info = ""
    if request.method == 'POST':
        station_code = request.form['station_code']
        if len(station_code) != 4:
            metar_info = "Le code de la station doit contenir 4 caractères (code ICAO)."
        else:
            try:
                metar = avwx.Metar(station_code)
                metar.update()
                metar_info = decode_metar(metar.data)
            except avwx.exceptions.BadStation:
                metar_info = f"Le code {station_code} est invalide ou non reconnu."
            except Exception as e:
                metar_info = f"Erreur lors de la récupération du METAR : {e}"

    return render_template('index.html', metar_info=metar_info)

if __name__ == '__main__':
    app.run(debug=True)
