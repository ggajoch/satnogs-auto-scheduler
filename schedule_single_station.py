#!/usr/bin/env python
from __future__ import division
import requests
import ephem
from datetime import datetime, timedelta
import os
import lxml.html
import argparse
import logging
from utils import read_priorities_transmitters, \
                  get_priority_passes
from auto_scheduler import Twolineelement, Satellite
from auto_scheduler.pass_predictor import find_passes
from auto_scheduler.schedulers import ordered_scheduler, \
                                      report_efficiency
from cache import CacheManager
from satnogs_client import get_active_transmitter_info, \
                           get_groundstation_info, \
                           get_satellite_info, \
                           get_scheduled_passes_from_network, \
                           get_transmitter_stats, \
                           schedule_observation
import settings
from tqdm import tqdm
import sys

_LOG_LEVEL_STRINGS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']


def _log_level_string_to_int(log_level_string):
    if log_level_string not in _LOG_LEVEL_STRINGS:
        message = 'invalid choice: {0} (choose from {1})'.format(log_level_string,
                                                                 _LOG_LEVEL_STRINGS)
        raise argparse.ArgumentTypeError(message)

    log_level_int = getattr(logging, log_level_string, logging.INFO)
    # check the logging log_level_choices have not changed from our expected values
    assert isinstance(log_level_int, int)

    return log_level_int


def main():
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Automatically schedule observations on a SatNOGS station.")
    parser.add_argument("-s", "--station", help="Ground station ID", type=int)
    parser.add_argument("-t",
                        "--starttime",
                        help="Start time (YYYY-MM-DDTHH:MM:SS) [default: now + 10 minutes]",
                        default=(datetime.utcnow() +
                                 timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"))
    parser.add_argument("-d",
                        "--duration",
                        help="Duration to schedule [hours; default: 1.0]",
                        type=float,
                        default=1.0)
    parser.add_argument("-m",
                        "--min-culmination",
                        help="Minimum culmination elevation [degrees; ground station default, minimum: 0, maximum: 90]",
                        type=float,
                        default=None)
    parser.add_argument("-r",
                        "--min-riseset",
                        help="Minimum rise/set elevation [degrees; ground station default, minimum: 0, maximum: 90]",
                        type=float,
                        default=None)
    parser.add_argument("-z",
                        "--horizon",
                        help="Force rise/set elevation to 0 degrees (overrided -r).",
                        action="store_true")
    parser.add_argument("-f",
                        "--only-priority",
                        help="Schedule only priority satellites (from -P file)",
                        dest='only_priority',
                        action='store_false')
    parser.set_defaults(only_priority=True)
    parser.add_argument("-w",
                        "--wait",
                        help="Wait time between consecutive observations (for setup and slewing)" +
                        " [seconds; default: 0, maximum: 3600]",
                        type=int,
                        default=0)
    parser.add_argument("-n",
                        "--dryrun",
                        help="Dry run (do not schedule passes)",
                        action="store_true")
    parser.add_argument("-P",
                        "--priorities",
                        help="File with transmitter priorities. Should have " +
                        "columns of the form |NORAD priority UUID| like |43017 0.9" +
                        " KgazZMKEa74VnquqXLwAvD|. Priority is fractional, one transmitter " +
                        "per line.",
                        default=None)
    parser.add_argument("-M",
                        "--min-priority",
                        help="Minimum priority. Only schedule passes with a priority higher" +
                        "than this limit [default: 0.0, maximum: 1.0]",
                        type=float,
                        default=0.)
    parser.add_argument("-T",
                        "--allow-testing",
                        help="Allow scheduling on stations which are in testing mode [default: False]",
                        action="store_true")
    parser.set_defaults(allow_testing=False)    
    parser.add_argument("-l",
                        "--log-level",
                        default="INFO",
                        dest="log_level",
                        type=_log_level_string_to_int,
                        nargs="?",
                        help="Set the logging output level. {0}".format(_LOG_LEVEL_STRINGS))
    args = parser.parse_args()

    # Check arguments
    if args.station is None:
        parser.print_help()
        sys.exit()

    # Setting logging level
    numeric_level = args.log_level
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level")
    logging.basicConfig(level=numeric_level,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Settings
    ground_station_id = args.station
    if args.duration > 0.0:
        length_hours = args.duration
    else:
        length_hours = 1.0
    if args.wait <= 0:
        wait_time_seconds = 0
    elif args.wait <= 3600:
        wait_time_seconds = args.wait
    else:
        wait_time_seconds = 3600
    if args.min_priority < 0.0:
        min_priority = 0.0
    elif args.min_priority > 1.0:
        min_priority = 1.0
    else:
        min_priority = args.min_priority
    schedule = not args.dryrun
    only_priority = args.only_priority
    priority_filename = args.priorities

    # Set time range
    tnow = datetime.strptime(args.starttime, "%Y-%m-%dT%H:%M:%S")
    tmin = tnow
    tmax = tnow + timedelta(hours=length_hours)

    # Get ground station information
    ground_station = get_groundstation_info(ground_station_id, args.allow_testing)
    if not ground_station:
        sys.exit()

    # Create or update the transmitter & TLE cache
    cache = CacheManager(ground_station_id,
                         ground_station['antenna'],
                         settings.CACHE_DIR,
                         settings.CACHE_AGE,
                         settings.MAX_NORAD_CAT_ID)
    cache.update()

    # Set observer
    observer = ephem.Observer()
    observer.lon = str(ground_station['lng'])
    observer.lat = str(ground_station['lat'])
    observer.elevation = ground_station['altitude']

    # Set minimum culmination elevation
    if args.min_culmination is None:
        min_culmination = ground_station['min_horizon']
    else:
        if args.min_culmination < 0.0:
            min_culmination = 0.0
        elif args.min_culmination > 90.0:
            min_culmination = 90.0
        else:
            min_culmination = args.min_culmination

    # Set minimum rise/set elevation
    if args.min_riseset is None:
        min_riseset = ground_station['min_horizon']
    else:
        if args.min_riseset < 0.0:
            min_riseset = 0.0
        elif args.min_riseset > 90.0:
            min_riseset = 90.0
        else:
            min_riseset = args.min_riseset
            
    # Use minimum altitude for computing rise and set times (horizon to horizon otherwise)
    if not args.horizon:
        observer.horizon = str(min_riseset)

    # Minimum duration of a pass
    min_pass_duration = settings.MIN_PASS_DURATION

    # Read tles
    tles = list(cache.read_tles())

    # Read transmitters
    transmitters = cache.read_transmitters()

    # Extract satellites from receivable transmitters
    satellites = []
    for transmitter in transmitters:
        for tle in tles:
            if tle['norad_cat_id'] == transmitter['norad_cat_id']:
                satellites.append(Satellite(Twolineelement(*tle['lines']),
                                            transmitter['uuid'],
                                            transmitter['success_rate'],
                                            transmitter['good_count'],
                                            transmitter['data_count'],
                                            transmitter['mode']))

    # Find passes
    passes = []
    logging.info('Finding all passes for %s satellites:' % len(satellites))
    # Loop over satellites
    for satellite in tqdm(satellites):
        passes.extend(find_passes(satellite,
                                  observer,
                                  tmin,
                                  tmax,
                                  min_culmination,
                                  min_pass_duration))

    priorities, favorite_transmitters = read_priorities_transmitters(priority_filename)
    
    # List of scheduled passes
    scheduledpasses = get_scheduled_passes_from_network(ground_station_id, tmin, tmax)
    logging.info("Found %d scheduled passes between %s and %s on ground station %d" %
                 (len(scheduledpasses), tmin, tmax, ground_station_id))

    # Get passes of priority objects
    prioritypasses, normalpasses = get_priority_passes(passes, priorities, favorite_transmitters,
                                                       only_priority, min_priority)

    # Priority scheduler
    prioritypasses = sorted(prioritypasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(prioritypasses, scheduledpasses, wait_time_seconds)
    for satpass in passes:
        logging.debug(satpass)

    # Normal scheduler
    normalpasses = sorted(normalpasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(normalpasses, scheduledpasses, wait_time_seconds)

    # Report scheduling efficiency
    report_efficiency(scheduledpasses, passes)

    # Find unique objects
    satids = sorted(set([satpass['id'] for satpass in passes]))

    schedule_needed = False

    logging.info("GS  | Sch | NORAD | Start time          | End time            |  El | " +
                 "Priority | Transmitter UUID       | Mode       | Satellite name ")
    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        logging.info(
            "%3d | %3.d | %05d | %s | %s | %3.0f | %4.6f | %s | %-10s | %s" %
            (ground_station_id, satpass['scheduled'], int(
                satpass['id']), satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
             satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"), float(satpass['altt']) if satpass['altt']
             else 0., satpass['priority'], satpass['uuid'], satpass['mode'], satpass['name'].rstrip()))
        if not satpass['scheduled']:
            schedule_needed = True

    # Login and schedule passes
    if schedule and schedule_needed:
        loginUrl = '{}/accounts/login/'.format(settings.NETWORK_BASE_URL)  # login URL
        session = requests.session()
        login = session.get(loginUrl)  # Get login page for CSFR token
        login_html = lxml.html.fromstring(login.text)
        login_hidden_inputs = login_html.xpath(r'//form//input[@type="hidden"]')  # Get CSFR token
        form = {x.attrib["name"]: x.attrib["value"] for x in login_hidden_inputs}
        form["login"] = settings.NETWORK_USERNAME
        form["password"] = settings.NETWORK_PASSWORD

        # Login
        result = session.post(loginUrl,
                              data=form,
                              headers={
                                  'referer': loginUrl,
                                  'user-agent': 'satnogs-auto-scheduler/0.0.1'
                              })
        if result.url.endswith("/accounts/login/"):
            logging.info("Authentication failed")
            sys.exit(-1)
        else:
            logging.info("Authentication successful")

        # Sort passes
        scheduledpasses_sorted = sorted(scheduledpasses, key=lambda satpass: satpass['tr'])

        logging.info('Checking and scheduling passes as needed.')
        for satpass in tqdm(scheduledpasses_sorted):
            if not satpass['scheduled']:
                logging.debug("Scheduling %05d %s %s %3.0f %4.3f %s %s" %
                              (int(satpass['id']), satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
                               satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"), float(satpass['altt']),
                               satpass['priority'], satpass['uuid'], satpass['name'].rstrip()))
                schedule_observation(session, int(satpass['id']), satpass['uuid'],
                                     ground_station_id,
                                     satpass['tr'].strftime("%Y-%m-%d %H:%M:%S") + ".000",
                                     satpass['ts'].strftime("%Y-%m-%d %H:%M:%S") + ".000")

        logging.info("All passes are scheduled. Exiting!")


if __name__ == '__main__':
    main()
