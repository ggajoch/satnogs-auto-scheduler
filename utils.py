import requests
import logging
import math
import random
from datetime import datetime, timedelta
import ephem
import lxml
import settings
from tqdm import tqdm


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


def get_active_transmitter_info(fmin, fmax):
    # Open session
    logging.info("Fetching transmitter information from DB.")
    r = requests.get('{}/api/transmitters'.format(settings.DB_BASE_URL))
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
    while True:
        if start:
            r = client.get('{}/api/observations/?ground_station={:d}'.format(
                           settings.NETWORK_BASE_URL,
                           ground_station))
            start = False
        else:
            nextpage = r.links.get("next")
            r = client.get(nextpage["url"])

        # r.json() is a list of dicts
        for o in r.json():
            satpass = {
                "id": o['norad_cat_id'],
                "tr": datetime.strptime(
                    o['start'].replace(
                        "Z",
                        ""),
                    "%Y-%m-%dT%H:%M:%S"),
                "ts": datetime.strptime(
                    o['end'].replace(
                        "Z",
                        ""),
                    "%Y-%m-%dT%H:%M:%S"),
                "scheduled": True,
                "altt": o['max_altitude'],
                "priority": 1,
                "uuid": o['transmitter'],
                "name": ''}

            if satpass['ts'] > tmin and satpass['tr'] < tmax:
                scheduledpasses.append(satpass)
        if satpass['ts'] < tmin:
            break

    logging.info("Scheduled passes for ground station %d retrieved!" % ground_station)
    return scheduledpasses


def overlap(satpass, scheduledpasses):
    # No overlap
    overlap = False
    # Loop over scheduled passes
    for scheduledpass in scheduledpasses:
        # Test pass falls within scheduled pass
        if satpass['tr'] >= scheduledpass['tr'] and satpass['ts'] < scheduledpass['ts']:
            overlap = True
        # Scheduled pass falls within test pass
        elif scheduledpass['tr'] >= satpass['tr'] and scheduledpass['ts'] < satpass['ts']:
            overlap = True
        # Pass start falls within pass
        elif satpass['tr'] >= scheduledpass['tr'] and satpass['tr'] < scheduledpass['ts']:
            overlap = True
        # Pass end falls within end
        elif satpass['ts'] >= scheduledpass['tr'] and satpass['ts'] < scheduledpass['ts']:
            overlap = True
        if overlap:
            break

    return overlap


def ordered_scheduler(passes, scheduledpasses):
    """Loop through a list of ordered passes and schedule each next one that fits"""
    # Loop over passes
    for satpass in passes:
        # Schedule if there is no overlap with already scheduled passes
        if not overlap(satpass, scheduledpasses):
            scheduledpasses.append(satpass)

    return scheduledpasses


def random_scheduler(passes, scheduledpasses):
    """Schedule passes based on random ordering"""
    # Shuffle passes
    random.shuffle(passes)

    return ordered_scheduler(passes, scheduledpasses)


def efficiency(passes):

    # Loop over passes
    start = False
    for satpass in passes:
        if not start:
            dt = satpass['ts'] - satpass['tr']
            tmin = satpass['tr']
            tmax = satpass['ts']
            start = True
        else:
            dt += satpass['ts'] - satpass['tr']
            if satpass['tr'] < tmin:
                tmin = satpass['tr']
            if satpass['ts'] > tmax:
                tmax = satpass['ts']
    # Total time covered
    dttot = tmax - tmin

    return dt.total_seconds(), dttot.total_seconds(
    ), dt.total_seconds() / dttot.total_seconds()


def find_passes(satellites, observer, tmin, tmax, minimum_altitude):
    # Loop over satellites
    passes = []
    passid = 0
    logging.info('Finding all passes for %s satellites:' % len(satellites))
    for satellite in tqdm(satellites):
        # Set start time
        observer.date = ephem.date(tmin)

        # Load TLE
        try:
            sat_ephem = ephem.readtle(str(satellite.tle0),
                                      str(satellite.tle1),
                                      str(satellite.tle2))
        except (ValueError, AttributeError):
            continue

        # Loop over passes
        keep_digging = True
        while keep_digging:
            try:
                tr, azr, tt, altt, ts, azs = observer.next_pass(sat_ephem)
            except ValueError:
                break  # there will be sats in our list that fall below horizon, skip
            except TypeError:
                break  # if there happens to be a non-EarthSatellite object in the list
            except Exception:
                break

            if tr is None:
                break

            # using the angles module convert the sexagesimal degree into
            # something more easily read by a human
            try:
                elevation = format(math.degrees(altt), '.0f')
                azimuth_r = format(math.degrees(azr), '.0f')
                azimuth_s = format(math.degrees(azs), '.0f')
            except TypeError:
                break
            passid += 1

            # show only if >= configured horizon and in next 6 hours,
            # and not directly overhead (tr < ts see issue 199)
            if tr < ephem.date(tmax):
                if (float(elevation) >= minimum_altitude and tr < ts):
                    valid = True
                    if tr < ephem.Date(datetime.now() +
                                       timedelta(minutes=5)):
                        valid = False
                    satpass = {'passid': passid,
                               'mytime': str(observer.date),
                               'name': str(satellite.name),
                               'id': str(satellite.id),
                               'tle1': str(satellite.tle1),
                               'tle2': str(satellite.tle2),
                               'tr': tr.datetime(),  # Rise time
                               'azr': azimuth_r,     # Rise Azimuth
                               'tt': tt.datetime(),  # Max altitude time
                               'altt': elevation,    # Max altitude
                               'ts': ts.datetime(),  # Set time
                               'azs': azimuth_s,     # Set azimuth
                               'valid': valid,
                               'uuid': satellite.transmitter,
                               'success_rate': satellite.success_rate,
                               'good_count': satellite.good_count,
                               'data_count': satellite.data_count,
                               'scheduled': False}
                    passes.append(satpass)
                observer.date = ephem.Date(
                    ts).datetime() + timedelta(minutes=1)
            else:
                keep_digging = False

    return passes


def get_groundstation_info(ground_station_id):

    logging.info("Requesting information for ground station %d" % ground_station_id)
    client = requests.session()

    # Loop
    found = False
    r = client.get("{}/api/stations/?id={:d}".format(
                   settings.NETWORK_BASE_URL,
                   ground_station_id))
    for o in r.json():
        if o['id'] == ground_station_id:
            found = True
            break
    if found:
        logging.info('Ground station information retrieved!')
        return o
    else:
        logging.info('No ground station information found!')
        return {}


def get_last_update(fname):
    try:
        fp = open(fname, "r")
        line = fp.readline()
        fp.close()
        return datetime.strptime(line.strip(), "%Y-%m-%dT%H:%M:%S")
    except IOError:
        return None


def schedule_observation(
        session,
        norad_cat_id,
        uuid,
        ground_station_id,
        starttime,
        endtime):

    obsURL = '{}/observations/new/'.format(settings.NETWORK_BASE_URL)  # Observation URL
    # Get the observation/new/ page to get the CSFR token
    obs = session.get(obsURL)
    obs_html = lxml.html.fromstring(obs.text)
    hidden_inputs = obs_html.xpath(r'//form//input[@type="hidden"]')
    form = {x.attrib["name"]: x.attrib["value"] for x in hidden_inputs}
    form["satellite"] = norad_cat_id
    form["transmitter"] = uuid
    form["start-time"] = starttime
    form["end-time"] = endtime
    form["0-starting_time"] = starttime
    form["0-ending_time"] = endtime
    form["0-station"] = ground_station_id
    form["total"] = str(1)
    session.post(obsURL, data=form, headers={'referer': obsURL})
    logging.debug("Scheduled!")
