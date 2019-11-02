import requests
import logging
from datetime import datetime
import lxml
import settings
import sys


def get_paginated_endpoint(url, max_entries=None):
    r = requests.get(url=url)
    r.raise_for_status()

    data = r.json()

    while 'next' in r.links and (not max_entries or len(data) < max_entries):
        next_page_url = r.links['next']['url']

        r = requests.get(url=next_page_url)
        r.raise_for_status()

        data.extend(r.json())

    return data


def get_satellite_info():
    # Open session
    logging.info("Fetching satellite information from DB.")
    r = requests.get('{}/api/satellites'.format(settings.DB_BASE_URL))
    logging.info("Satellites received!")

    # Select alive satellites
    norad_cat_ids = []
    for o in r.json():
        if o["status"] == "alive":
            norad_cat_ids.append(o["norad_cat_id"])

    return norad_cat_ids


def get_active_transmitter_info(fmin, fmax):
    # Open session
    logging.info("Fetching transmitter information from DB.")
    r = requests.get('{}/api/transmitters'.format(settings.DB_BASE_URL))
    logging.info("Transmitters received!")

    # Loop
    transmitters = []
    for o in r.json():
        if o["downlink_low"]:
            if o["status"] == "active" and o["downlink_low"] > fmin and o["downlink_low"] <= fmax:
                transmitter = {"norad_cat_id": o["norad_cat_id"], "uuid": o["uuid"], "mode": o["mode"]}
                transmitters.append(transmitter)
    logging.info("Transmitters filtered based on ground station capability.")
    return transmitters


def get_transmitter_stats():
    logging.debug("Requesting transmitter success rates for all satellite")
    transmitters = get_paginated_endpoint('{}/api/transmitters/'.format(settings.NETWORK_BASE_URL))
    return transmitters


def get_scheduled_passes_from_network(ground_station, tmin, tmax):
    # Get first page
    client = requests.session()

    # Loop
    start = True
    scheduledpasses = []

    logging.info("Requesting scheduled passes for ground station %d" % ground_station)
    # Fetch observations until the time of the end of the last fetched observation happends to be
    # before the start time of the selected timerange for scheduling
    # NOTE: This algorithm is based on the order in which the API returns the observations, i.e.
    # most recent observations are returned at first!
    while True:
        if start:
            r = client.get('{}/api/observations/?ground_station={:d}'.format(
                settings.NETWORK_BASE_URL, ground_station))
            start = False
        else:
            nextpage = r.links.get("next")
            r = client.get(nextpage["url"])

        if not r.json():
            # Ground station has no observations yet
            break

        # r.json() is a list of dicts/observations
        for o in r.json():
            satpass = {
                "id": o['norad_cat_id'],
                "tr": datetime.strptime(o['start'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S"),
                "ts": datetime.strptime(o['end'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S"),
                "scheduled": True,
                "altt": o['max_altitude'],
                "priority": 1,
                "uuid": o['transmitter'],
                "name": '',
                "mode": ''
            }

            if satpass['ts'] > tmin and satpass['tr'] < tmax:
                # Only store observations which are during the ROI for scheduling
                scheduledpasses.append(satpass)

        if satpass['ts'] < tmin:
            # Last fetched observation is older than the ROI for scheduling, end loop.
            break

    logging.info("Scheduled passes for ground station %d retrieved!" % ground_station)
    return scheduledpasses


def get_groundstation_info(ground_station_id, allow_testing):

    logging.info("Requesting information for ground station %d" % ground_station_id)

    # Loop
    r = requests.get("{}/api/stations/?id={:d}".format(settings.NETWORK_BASE_URL,
                                                       ground_station_id))

    selected_stations = list(filter(lambda s: s['id'] == ground_station_id, r.json()))

    if not selected_stations:
        logging.info('No ground station information found!')
        # Exit if no ground station found
        sys.exit()

    logging.info('Ground station information retrieved!')
    station = selected_stations[0]

    if station['status'] == 'Online' or (station['status'] == 'Testing' and allow_testing):
        return station
    else:
        if station['status'] == 'Testing' and not allow_testing:
            logging.info("Ground station {} is in testing mode but auto-scheduling is not "
                         "allowed. Use -T command line argument to enable scheduling.".format(ground_station_id))
        else:
            logging.info("Ground station {} neither in 'online' nor in 'testing' mode, "
                         "can't schedule!".format(ground_station_id))
        return {}


def schedule_observation(session, norad_cat_id, uuid, ground_station_id, starttime, endtime):

    obsURL = '{}/observations/new/'.format(settings.NETWORK_BASE_URL)  # Observation URL
    # Get the observation/new/ page to get the CSFR token
    obs = session.get(obsURL)
    obs_html = lxml.html.fromstring(obs.text)
    hidden_inputs = obs_html.xpath(r'//form//input[@type="hidden"]')
    form = {x.attrib["name"]: x.attrib["value"] for x in hidden_inputs}
    form["obs-0-transmitter_uuid"] = uuid
    form["obs-0-start"] = starttime
    form["obs-0-end"] = endtime
    form["obs-0-ground_station"] = ground_station_id
    form["obs-TOTAL_FORMS"] = str(1)
    form["obs-INITIAL_FORMS"] = str(0)
    session.post(obsURL, data=form, headers={'referer': obsURL})
    logging.debug("Scheduled!")
