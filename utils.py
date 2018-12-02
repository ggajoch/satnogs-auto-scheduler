import requests
import logging

DB_BASE_URL = 'https://db.satnogs.org/api'


def get_active_transmitter_info(fmin, fmax):
    # Open session
    logging.info("Fetching transmitter information from DB.")
    r = requests.get('{}/transmitters'.format(DB_BASE_URL))
    logging.info("Transmitters received!")

    # Loop
    transmitters = []
    for o in r.json():
        if o["downlink_low"]:
            if o["alive"] and o["downlink_low"] > fmin and o["downlink_low"] <= fmax:
                transmitter = {"norad_cat_id": o["norad_cat_id"],
                               "uuid": o["uuid"]}
                transmitters.append(transmitter)
    logging.info("Transmitters filtered based on ground station capability.")
    return transmitters
