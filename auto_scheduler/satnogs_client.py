# pylint: disable=missing-timeout

import logging
import sys
from datetime import datetime

import requests

from auto_scheduler import settings

logger = logging.getLogger(__name__)


def get_paginated_endpoint(url, max_entries=None, authenticated=False):
    if authenticated:
        response = requests.get(url=url,
                                headers={'Authorization': f'Token {settings.SATNOGS_DB_API_TOKEN}'})
    else:
        response = requests.get(url=url)
    response.raise_for_status()

    data = response.json()

    while 'next' in response.links and (not max_entries or len(data) < max_entries):
        next_page_url = response.links['next']['url']

        response = requests.get(url=next_page_url)
        response.raise_for_status()

        data.extend(response.json())

    return data


def get_satellite_info():
    # Open session
    logger.info("Fetching satellite information from DB.")
    response = requests.get(f'{settings.DB_BASE_URL}/api/satellites')
    logger.info("Satellites received!")

    # Select alive satellites
    norad_cat_ids = []
    for obs in response.json():
        if obs["status"] == "alive":
            norad_cat_ids.append(obs["norad_cat_id"])

    return norad_cat_ids


def get_active_transmitter_info(fmin, fmax):
    # Open session
    logger.info("Fetching transmitter information from DB.")
    response = requests.get(f'{settings.DB_BASE_URL}/api/transmitters')
    logger.info("Transmitters received!")

    # Loop
    transmitters = []
    for obs in response.json():
        if obs["downlink_low"]:
            if obs["status"] == "active" and obs["downlink_low"] > fmin and obs[
                    "downlink_low"] <= fmax and obs["norad_cat_id"] is not None:
                transmitter = {
                    "norad_cat_id": obs["norad_cat_id"],
                    "uuid": obs["uuid"],
                    "mode": obs["mode"]
                }
                transmitters.append(transmitter)
    logger.info("Transmitters filtered based on ground station capability.")
    return transmitters


def get_tles():
    tle_data = get_paginated_endpoint(f'{settings.DB_BASE_URL}/api/tle/', authenticated=True)
    return tle_data


def get_transmitter_stats():
    logger.debug("Requesting transmitter success rates for all satellite")
    transmitters = get_paginated_endpoint(f'{settings.NETWORK_BASE_URL}/api/transmitters/')
    return transmitters


def get_scheduled_passes_from_network(ground_station, tmin, tmax):
    # Get first page
    client = requests.session()

    # Loop
    next_url = f'{settings.NETWORK_BASE_URL}/api/observations/?ground_station={ground_station}'
    scheduledpasses = []

    logger.info(f"Requesting scheduled passes for ground station {ground_station}")
    # Fetch observations until the time of the end of the last fetched observation happends to be
    # before the start time of the selected timerange for scheduling
    # NOTE: This algorithm is based on the order in which the API returns the observations, i.e.
    # most recent observations are returned at first!
    while next_url:
        response = client.get(next_url)

        if 'next' in response.links:
            next_url = response.links['next']['url']
        else:
            logger.debug("No further pages with observations")
            next_url = None

        if not response.json():
            logger.info("Ground station has no observations yet")
            break

        # response.json() is a list of dicts/observations
        for obs in response.json():
            start = datetime.strptime(obs['start'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            end = datetime.strptime(obs['end'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            satpass = {
                "tr": start,
                "ts": end,
                "td": end - start,
                "scheduled": True,
                "altt": obs['max_altitude'],
                "priority": 1,
                "transmitter": {
                    "uuid": obs['transmitter'],
                    "mode": ''
                },
                "satellite": {
                    "name": '',
                    "id": obs['norad_cat_id']
                }
            }

            if satpass['ts'] > tmin and satpass['tr'] < tmax:
                # Only store observations which are during the ROI for scheduling
                scheduledpasses.append(satpass)

        if satpass['ts'] < tmin:
            # Last fetched observation is older than the ROI for scheduling, end loop.
            break

    logger.info(f"Scheduled passes for ground station {ground_station} retrieved!")
    return scheduledpasses


def get_groundstation_info(ground_station_id, allow_testing):

    logger.info(f"Requesting information for ground station {ground_station_id}")

    # Loop
    response = requests.get(f"{settings.NETWORK_BASE_URL}/api/stations/?id={ground_station_id}")

    selected_stations = list(filter(lambda s: s['id'] == ground_station_id, response.json()))

    if not selected_stations:
        logger.info('No ground station information found!')
        # Exit if no ground station found
        sys.exit()

    logger.info('Ground station information retrieved!')
    station = selected_stations[0]
    logger.debug(station)

    if station['status'] == 'Online' or (station['status'] == 'Testing' and allow_testing):
        return station

    if station['status'] == 'Testing' and not allow_testing:
        logger.info(
            f"Ground station {ground_station_id} is in testing mode but auto-scheduling is not "
            "allowed. Use -T command line argument to enable scheduling.")
    else:
        logger.info(
            f"Ground station {ground_station_id} neither in 'online' nor in 'testing' mode, "
            "can't schedule!")
    return {}


def schedule_observations_batch(observations):
    """
    Schedule observations on satnogs-network.

    observations: list of dicts, keys:
      - ground_station_id: ground station id - int
      - transmitter_uuid: transmitter uuid - str
      - start: observation start - datetime
      - end: observation end - datetime
    """
    observations_serialized = list({
        'ground_station': satpass['ground_station_id'],
        'transmitter_uuid': satpass['transmitter_uuid'],
        'start': satpass['start'].strftime("%Y-%m-%d %H:%M:%S"),
        'end': satpass['end'].strftime("%Y-%m-%d %H:%M:%S")
    } for satpass in observations)

    try:
        response = requests.post(f'{settings.NETWORK_BASE_URL}/api/observations/',
                                 json=observations_serialized,
                                 headers={'Authorization': f'Token {settings.SATNOGS_API_TOKEN}'})
        response.raise_for_status()
        logger.debug("Scheduled {len(observations_serialized)} passes!")
    except requests.HTTPError:
        err = response.json()
        logger.error(f"Failed to batch-schedule the passes. Reason: {err}")
        logger.error("Fall-back to single-pass scheduling.")
        schedule_observations(observations_serialized)


def schedule_observations(observations_serialized):
    """
    Schedule observations on satnogs-network.

    observations: list of dicts, keys:
      - ground_station: ground station id - int
      - transmitter_uuid: transmitter uuid - str
      - start: observation start - str, "%Y-%m-%d %H:%M:%S"
      - end: observation end - str, "%Y-%m-%d %H:%M:%S"
    """
    for observation in observations_serialized:
        try:
            response = requests.post(
                f'{settings.NETWORK_BASE_URL}/api/observations/',
                json=[observation],
                headers={'Authorization': f'Token {settings.SATNOGS_API_TOKEN}'})
            response.raise_for_status()
            logger.debug("Scheduled pass!")
        except requests.HTTPError:
            err = response.json()
            logger.error(f"Failed to schedule the pass at {observation['end']}. Reason: {err}")
