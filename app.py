from flask import Flask, render_template, request, redirect, url_for
import avwx # Bibliothèque pour traiter les données METAR
from datetime import datetime
import pytz # Pour la gestion des fuseaux horaires

app = Flask(__name__) # Crée l'instance de l'application Flask


def decode_metar(metar_data, station_code):
    """Décode le rapport METAR en informations compréhensibles"""
    # Décodage du vent
    vent_direction = metar_data.wind_direction.repr
    vent_vitesse = metar_data.wind_speed.repr
    vent_info = f"Vent venant du {vent_direction}° à {vent_vitesse} nœuds."

    # Température et point de rosée
    temperature = metar_data.temperature.repr
    dew_point = metar_data.dewpoint.repr
    temperature_info = f"Température : {temperature}°C, Point de rosée : {dew_point}°C."

    # Visibilité
    visibility = metar_data.visibility.repr
    try:
        if visibility == "CAVOK":
            visibility_info = "Visibilité : CAVOK (pas de phénomènes significatifs, visibilité supérieure à 10 km)."
        else:
            # Vérification si la visibilité contient "SM", ce qui signifie qu'elle est en miles
            if 'SM' in visibility:
                visibility_value = float(visibility.replace('SM', '').strip())
                visibility_info = f"Visibilité : {visibility_value} miles."
            else:
                visibility_value = int(visibility)

                # Si le code ICAO commence par "K" (aéroports aux États-Unis), on convertit en miles
                if station_code.startswith('K'):
                    visibility_in_miles = visibility_value / 1609.34  # Conversion mètres -> miles
                    visibility_info = f"Visibilité : {visibility_in_miles:.2f} miles."
                else:
                    visibility_info = f"Visibilité : {visibility_value} mètres."
    except Exception as e:
        visibility_info = f"Visibilité : {visibility} (unité non spécifiée)."

    # Pression barométrique
    pression = metar_data.altimeter.repr
    if pression.startswith('Q'):
        pression_info = f"Pression atmosphérique : {pression[1:]} hPa (hectopascals, système international)."
    elif pression.startswith('A'):
        pression_info = f"Pression atmosphérique : {pression[1:]} inHg (pouces de mercure, utilisé principalement aux USA)."
    else:
        pression_info = f"Pression atmosphérique : {pression} (unité non spécifiée)."

    # Heure d'observation (décodage de l'heure UTC en format conventionnel)
    time_repr = metar_data.time.repr  # Format JJHHMMZ
    day = int(time_repr[:2])  # Jour du mois
    hour = int(time_repr[2:4])  # Heure (UTC)
    minute = int(time_repr[4:6])

    # Obtenir la date et heure complètes (utiliser aujourd'hui comme base)
    now = datetime.utcnow()  # Date actuelle en UTC
    # Ajuster pour que le jour vienne du METAR
    observation_time_utc = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)

    # Convertir en heure locale pour la Martinique
    local_tz = pytz.timezone('America/Martinique')  # Fuseau horaire de la Martinique
    observation_time_local = observation_time_utc.replace(tzinfo=pytz.utc).astimezone(local_tz)

    # Format conventionnel de l'heure UTC et heure locale
    heure_info = (
        f"Heure d'observation UTC : {observation_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC<br>"
        f"Heure locale (Martinique) : {observation_time_local.strftime('%Y-%m-%d %H:%M:%S')} (heure locale)"
    )

    # Décodage final
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
                metar_info = decode_metar(metar.data, station_code)
            except avwx.exceptions.BadStation:
                metar_info = f"Le code {station_code} est invalide ou non reconnu."
            except Exception as e:
                metar_info = f"Erreur lors de la récupération du METAR : {e}"

    return render_template('index.html', metar_info=metar_info)

if __name__ == '__main__':
    app.run(debug=True)
