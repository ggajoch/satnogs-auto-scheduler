#!/usr/bin/env python
from __future__ import division
import requests
import ephem
from datetime import datetime, timedelta
from satellite_tle import fetch_tles
import os
import lxml.html
import argparse
import logging
from utils import get_active_transmitter_info, get_transmitter_stats, \
    get_groundstation_info, get_last_update, get_scheduled_passes_from_network, ordered_scheduler, \
    efficiency, find_passes, schedule_observation
import settings
from tqdm import tqdm
import sys

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
        self.name = tle.name.strip()
        self.transmitter = transmitter
        self.success_rate = success_rate
        self.good_count = good_count
        self.data_count = data_count

    def __repr__(self):
        return "%s %s %d %d %d %s" % (self.id, self.transmitter, self.success_rate,
                                      self.good_count, self.data_count, self.name)


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
    parser.add_argument("-t", "--starttime", help="Start time (YYYY-MM-DD HH:MM:SS) [default: now]",
        default=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    parser.add_argument("-d", "--duration", help="Duration to schedule [hours; default 1.0]", type=float, default=1)
    parser.add_argument("-w", "--wait",
                        help="Wait time between consecutive observations (for setup and slewing) [seconds; default: 0.0]",
                        type=float, default=0)
    parser.add_argument("-u", "--username", help="old SatNOGS Network username (NOT the new Auth0 username)")
    parser.add_argument("-p", "--password", help="old SatNOGS Network password")
    parser.add_argument("-n", "--dryrun",  help="Dry run (do not schedule passes)", action="store_true")
    parser.add_argument("-l", "--log-level", default="INFO", dest="log_level",
                        type=_log_level_string_to_int, nargs="?",
                        help="Set the logging output level. {0}".format(_LOG_LEVEL_STRINGS))
    args = parser.parse_args()

    # Check arguments
    if args.station == None:
        parser.print_help()
        sys.exit()
    
    # Setting logging level
    numeric_level = args.log_level
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level")
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Settings
    ground_station_id = args.station
    length_hours = args.duration
    wait_time_seconds = args.wait
    if wait_time_seconds < 0:
        wait_time_seconds = 0.0
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

    # Exit if ground station is empty
    if not ground_station:
        sys.exit()

    # Create cache
    if not os.path.isdir(cache_dir):
        os.mkdir(cache_dir)

    # Get last update
    tlast = get_last_update(os.path.join(cache_dir, "last_update_%d.txt" % ground_station_id))

    # Update logic
    update = False
    if tlast is None or (tnow - tlast).total_seconds() > settings.CACHE_AGE * 3600:
        update = True
    if not os.path.isfile(os.path.join(cache_dir, "transmitters_%d.txt" % ground_station_id)):
        update = True
    if not os.path.isfile(os.path.join(cache_dir, "tles_%d.txt" % ground_station_id)):
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
            set([transmitter["norad_cat_id"] for transmitter in transmitters.values()
                 if transmitter["norad_cat_id"] < settings.MAX_NORAD_CAT_ID]))

        # Store transmitters
        fp = open(os.path.join(cache_dir, "transmitters_%d.txt" % ground_station_id), "w")
        logging.info("Requesting transmitter success rates.")
        transmitters_stats = get_transmitter_stats()
        for transmitter in transmitters_stats:
            if not transmitter['uuid'] in transmitters.keys():
                continue

            fp.write("%05d %s %d %d %d\n" %
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
        fp = open(os.path.join(cache_dir, "tles_%d.txt" % ground_station_id), "w")
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
                    satellites.append(satellite(
                        tle,
                        uuid,
                        success_rate,
                        good_count,
                        data_count))

    # Find passes
    passes = find_passes(satellites, observer, tmin, tmax, minimum_altitude)

    # Priorities
    priorities = {}

    # List of scheduled passes
    scheduledpasses = get_scheduled_passes_from_network(ground_station_id, tmin, tmax)
    logging.info("Found %d scheduled passes between %s and %s on ground station %d" %
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
            # Find satellite transmitter with highest number of good observations
            max_good_count = max([s['good_count'] for s in passes if s["id"] == satpass["id"]])
            if max_good_count > 0:
                satpass['priority'] = \
                    (float(satpass['altt']) / 90.0) \
                    * satpass['success_rate'] \
                    * float(satpass['good_count']) / max_good_count
            else:
                satpass['priority'] = (
                    float(satpass['altt']) / 90.0) * satpass['success_rate']
            normalpasses.append(satpass)

    # Priority scheduler
    prioritypasses = sorted(prioritypasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(prioritypasses, scheduledpasses, wait_time_seconds)
    for satpass in passes:
        logging.debug(satpass)

    # Normal scheduler
    normalpasses = sorted(normalpasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(normalpasses, scheduledpasses, wait_time_seconds)

    # Compute scheduling efficiency
    dt, dttot, eff = efficiency(scheduledpasses)
    logging.info("%d passes scheduled out of %d, %.0f s out of %.0f s at %.3f%% efficiency" %
                 (len(scheduledpasses), len(passes), dt, dttot, 100 * eff))

    # Find unique objects
    satids = sorted(set([satpass['id'] for satpass in passes]))

    schedule_needed = False

    logging.info("GS  | Sch | NORAD | Start time          | End time            |  El | " +
                 "Priority | Transmitter UUID       | Satellite name ")
    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        logging.info(
            "%3d | %3.d | %05d | %s | %s | %3.0f | %4.6f | %s | %s" %
            (ground_station_id,
             satpass['scheduled'],
             int(satpass['id']),
             satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
             satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"),
             float(satpass['altt']) if satpass['altt'] else 0.,
             satpass['priority'],
             satpass['uuid'],
             satpass['name'].rstrip()))
        if not satpass['scheduled']:
            schedule_needed = True
            
    # Login and schedule passes
    if schedule and schedule_needed:
        loginUrl = '{}/accounts/login/'.format(settings.NETWORK_BASE_URL)  # login URL
        session = requests.session()
        login = session.get(loginUrl)  # Get login page for CSFR token
        login_html = lxml.html.fromstring(login.text)
        login_hidden_inputs = login_html.xpath(
            r'//form//input[@type="hidden"]')  # Get CSFR token
        form = {x.attrib["name"]: x.attrib["value"] for x in login_hidden_inputs}
        form["login"] = username
        form["password"] = password
        session.post(loginUrl, data=form, headers={'referer': loginUrl})  # Login

        scheduledpasses_sorted = sorted(scheduledpasses, key=lambda satpass: satpass['tr'])

        logging.info('Checking and scheduling passes as needed.')
        for satpass in tqdm(scheduledpasses_sorted):
            if not satpass['scheduled']:
                logging.debug(
                    "Scheduling %05d %s %s %3.0f %4.3f %s %s" %
                    (int(satpass['id']),
                     satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
                     satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"),
                     float(satpass['altt']),
                     satpass['priority'],
                     satpass['uuid'],
                     satpass['name'].rstrip()))
                schedule_observation(session,
                                     int(satpass['id']),
                                     satpass['uuid'],
                                     ground_station_id,
                                     satpass['tr'].strftime("%Y-%m-%d %H:%M:%S") + ".000",
                                     satpass['ts'].strftime("%Y-%m-%d %H:%M:%S") + ".000")

        logging.info("All passes are scheduled. Exiting!")
