#!/usr/bin/env python
from __future__ import division
import json
import requests
import ephem
import math
import random
from datetime import datetime, timedelta
from satellite_tle import fetch_tles
import os
import glob
import lxml.html
import argparse
import logging
from utils import get_active_transmitter_info, \
                  get_transmitter_stats, \
                  DB_BASE_URL, \
                  NETWORK_BASE_URL


_LOG_LEVEL_STRINGS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

class twolineelement:
    """TLE class"""

    def __init__(self, tle0, tle1, tle2):
        """Define a TLE"""

        self.tle0 = tle0
        self.tle1 = tle1
        self.tle2 = tle2
        if tle0[:2] == "0 ":
            self.name = tle0[2:]
        else:
            self.name = tle0
            if tle1.split(" ")[1] == "":
                self.id = int(tle1.split(" ")[2][:4])
            else:
                self.id = int(tle1.split(" ")[1][:5])


class satellite:
    """Satellite class"""

    def __init__(self, tle, transmitter, success_rate, good_count, data_count):
        """Define a satellite"""

        self.tle0 = tle.tle0
        self.tle1 = tle.tle1
        self.tle2 = tle.tle2
        self.id = tle.id
        self.name = tle.name
        self.transmitter = transmitter
        self.success_rate = success_rate
        self.good_count = good_count
        self.data_count = data_count


def get_scheduled_passes_from_network(ground_station, tmin, tmax):
    # Get first page
    client = requests.session()

    # Loop
    start = True
    scheduledpasses = []

    logging.info("Requesting scheduled passes for ground station %d" % ground_station)
    while True:
        if start:
            r = client.get('{}/observations/?ground_station={:d}'.format(
                           NETWORK_BASE_URL,
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
                "scheduled": True}

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
    for satellite in satellites:
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
    r = client.get("{}/stations/?id={:d}".format(
                   NETWORK_BASE_URL,
                   ground_station_id))
    for o in r.json():
        if o['id'] == ground_station_id:
            found = True
            break
    if found:
        logging.info('Ground station infromation retrieved!')
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

    obsURL = "https://network.satnogs.org/observations/new/"  # Observation URL
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


def _log_level_string_to_int(log_level_string):
    if log_level_string not in _LOG_LEVEL_STRINGS:
        message = 'invalid choice: {0} (choose from {1})'.format(log_level_string,
                                                                 _LOG_LEVEL_STRINGS)
        raise argparse.ArgumentTypeError(message)

    log_level_int = getattr(logging, log_level_string, logging.INFO)
    # check the logging log_level_choices have not changed from our expected values
    assert isinstance(log_level_int, int)

    return log_level_int


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Automatically schedule observations on a SatNOGS station.")
    parser.add_argument("-s", "--station", help="Ground station ID", type=int)
    parser.add_argument(
        "-t",
        "--starttime",
        help="Start time (YYYY-MM-DD HH:MM:SS) [default: now]",
        default=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    parser.add_argument(
        "-d",
        "--duration",
        help="Duration to schedule [hours]",
        type=int,
        default=1)
    parser.add_argument("-u", "--username", help="SatNOGS username")
    parser.add_argument("-p", "--password", help="SatNOGS password")
    parser.add_argument(
        "-n",
        "--dryrun",
        help="Dry run (do not schedule passes)",
        action="store_true")
    parser.add_argument("-l", "--log-level",
                        default="INFO",
                        dest="log_level",
                        type=_log_level_string_to_int,
                        nargs="?",
                        help="Set the logging output level. {0}".format(_LOG_LEVEL_STRINGS))
    args = parser.parse_args()

    # Setting logging level
    numeric_level = args.log_level
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(level=numeric_level,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Settings
    ground_station_id = args.station
    length_hours = args.duration
    data_age_hours = 24
    cache_dir = "/tmp/cache"
    username = args.username
    password = args.password
    schedule = not args.dryrun

    # Set time range
    tnow = datetime.strptime(args.starttime, "%Y-%m-%dT%H:%M:%S")
    tmin = tnow
    tmax = tnow + timedelta(hours=length_hours)

    # Get ground station information
    ground_station = get_groundstation_info(ground_station_id)

    # Create cache
    if not os.path.isdir(cache_dir):
        os.mkdir(cache_dir)

    # Get last update
    tlast = get_last_update(
        os.path.join(
            cache_dir,
            "last_update_%d.txt" %
            ground_station_id))

    # Update logic
    update = False
    if tlast is None or (tnow - tlast).total_seconds() > data_age_hours * 3600:
        update = True
    if not os.path.isfile(
        os.path.join(
            cache_dir,
            "transmitters_%d.txt" %
            ground_station_id)):
        update = True
    if not os.path.isfile(
        os.path.join(
            cache_dir,
            "tles_%d.txt" %
            ground_station_id)):
        update = True

    # Update
    if update:
        logging.info('Updating transmitters and TLEs for station')
        # Store current time
        with open(os.path.join(cache_dir, "last_update_%d.txt" % ground_station_id), "w") as fp:
            fp.write(tnow.strftime("%Y-%m-%dT%H:%M:%S") + "\n")

        # Get active transmitters in frequency range of each antenna
        transmitters = {}
        for antenna in ground_station['antenna']:
            for transmitter in get_active_transmitter_info(antenna["frequency"],
                                                           antenna["frequency_max"]):
                transmitters[transmitter['uuid']] = transmitter

        # Get NORAD IDs
        norad_cat_ids = sorted(
            set([transmitter["norad_cat_id"] for transmitter in transmitters.values()]))

        # Store transmitters
        fp = open(
            os.path.join(
                cache_dir,
                "transmitters_%d.txt" %
                ground_station_id),
            "w")
        logging.info("Requesting transmitter success rates.")
        transmitters_stats = get_transmitter_stats()
        for transmitter in transmitters_stats:
            if not transmitter['uuid'] in transmitters.keys():
                pass

            fp.write(
                "%05d %s %d %d %d\n" %
                (transmitter["norad_cat_id"],
                 transmitter["uuid"],
                 transmitter["success_rate"],
                 transmitter["good_count"],
                 transmitter["data_count"]))

        logging.info("Transmitter success rates received!")
        fp.close()

        # Get TLEs
        tles = fetch_tles(norad_cat_ids)

        # Store TLEs
        fp = open(
            os.path.join(
                cache_dir,
                "tles_%d.txt" %
                ground_station_id),
            "w")
        for norad_cat_id, (source, tle) in tles.items():
            fp.write("%s\n%s\n%s\n" % (tle[0], tle[1], tle[2]))
        fp.close()

    # Set observer
    observer = ephem.Observer()
    observer.lon = str(ground_station['lng'])
    observer.lat = str(ground_station['lat'])
    observer.elevation = ground_station['altitude']
    minimum_altitude = ground_station['min_horizon']

    # Read tles
    with open(os.path.join(cache_dir, "tles_%d.txt" % ground_station_id), "r") as f:
        lines = f.readlines()
        tles = [twolineelement(lines[i], lines[i + 1], lines[i + 2])
                for i in range(0, len(lines), 3)]

        # Read transmitters
    satellites = []
    with open(os.path.join(cache_dir, "transmitters_%d.txt" % ground_station_id), "r") as f:
        lines = f.readlines()
        for line in lines:
            item = line.split()
            norad_cat_id, uuid, success_rate, good_count, data_count = int(
                item[0]), item[1], float(item[2]) / 100.0, int(item[3]), int(item[4])
            for tle in tles:
                if tle.id == norad_cat_id:
                    satellites.append(
                        satellite(
                            tle,
                            uuid,
                            success_rate,
                            good_count,
                            data_count))

    # Find passes
    passes = find_passes(satellites, observer, tmin, tmax, minimum_altitude)

    # Priorities
#    priorities = {"40069": 1.000, "25338": 0.990, "28654": 0.990, "33591": 0.990}
    priorities = {}

    # List of scheduled passes
    scheduledpasses = get_scheduled_passes_from_network(
        ground_station_id, tmin, tmax)
    logging.info(
        "Found %d scheduled passes between %s and %s on ground station %d\n" %
        (len(scheduledpasses), tmin, tmax, ground_station_id))

    # Get passes of priority objects
    prioritypasses = []
    normalpasses = []
    for satpass in passes:
        # Get user defined priorities
        if satpass['id'] in priorities:
            satpass['priority'] = priorities[satpass['id']]
            prioritypasses.append(satpass)
        else:
            satpass['priority'] = (
                float(satpass['altt']) / 90.0) * satpass['success_rate']
            normalpasses.append(satpass)

    # Priority scheduler
    prioritypasses = sorted(
        prioritypasses,
        key=lambda satpass: -
        satpass['priority'])
    scheduledpasses = ordered_scheduler(prioritypasses, scheduledpasses)

    # Random scheduler
    normalpasses = sorted(
        normalpasses,
        key=lambda satpass: -
        satpass['priority'])
    scheduledpasses = ordered_scheduler(normalpasses, scheduledpasses)

    dt, dttot, eff = efficiency(scheduledpasses)
    logging.info(
        "%d passes scheduled out of %d, %.0f s out of %.0f s at %.3f%% efficiency" %
        (len(scheduledpasses), len(passes), dt, dttot, 100 * eff))

    # Find unique objects
    satids = sorted(set([satpass['id'] for satpass in passes]))

    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        if not satpass['scheduled']:
            logging.info(
                "%05d %s %s %3.0f %4.3f %s %s" %
                (int(
                    satpass['id']),
                    satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
                    satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"),
                    float(
                    satpass['altt']),
                    satpass['priority'],
                    satpass['uuid'],
                    satpass['name'].rstrip()))

    # Login
    loginUrl = "https://network.satnogs.org/accounts/login/"  # login URL
    session = requests.session()
    login = session.get(loginUrl)  # Get login page for CSFR token
    login_html = lxml.html.fromstring(login.text)
    login_hidden_inputs = login_html.xpath(
        r'//form//input[@type="hidden"]')  # Get CSFR token
    form = {x.attrib["name"]: x.attrib["value"] for x in login_hidden_inputs}
    form["login"] = username
    form["password"] = password
    session.post(loginUrl, data=form, headers={'referer': loginUrl})  # Login

    # Schedule passes
    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        if not satpass['scheduled']:
            if schedule:
                schedule_observation(session,
                                     int(satpass['id']),
                                     satpass['uuid'],
                                     ground_station_id,
                                     satpass['tr'].strftime("%Y-%m-%d %H:%M:%S") + ".000",
                                     satpass['ts'].strftime("%Y-%m-%d %H:%M:%S") + ".000")
