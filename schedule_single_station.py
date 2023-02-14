#!/usr/bin/env python3

# pylint: disable=consider-using-f-string

from __future__ import division

import argparse
import logging
import sys
from datetime import datetime, timedelta

from tqdm import tqdm

from auto_scheduler import __version__ as auto_scheduler_version
from auto_scheduler import settings
from auto_scheduler.cache import CacheManager
from auto_scheduler.io import read_priorities_transmitters, read_transmitters_of_interest
from auto_scheduler.pass_predictor import create_observer, find_constrained_passes
from auto_scheduler.satnogs_client import APIRequestError, check_station_availability, \
    get_groundstation_info, get_scheduled_passes_from_network, schedule_observations_batch
from auto_scheduler.schedulers import ordered_scheduler, report_efficiency
from auto_scheduler.utils import get_priority_passes, print_scheduledpass_summary, \
    satellites_from_transmitters

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
    # pylint: disable=too-many-branches,too-many-statements,too-many-locals

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
    parser.add_argument("-o",
                        "--max-observation-duration",
                        help="Max time for a single observation [minutes; default: 30]",
                        type=float,
                        default=30.0)
    parser.add_argument("-m",
                        "--min-culmination",
                        help="Minimum culmination elevation [degrees; " +
                        "ground station default, minimum: 0, maximum: 90]",
                        type=float,
                        default=None)
    parser.add_argument("-r",
                        "--min-riseset",
                        help="Minimum rise/set elevation [degrees; " +
                        "ground station default, minimum: 0, maximum: 90]",
                        type=float,
                        default=None)
    parser.add_argument("-z",
                        "--horizon",
                        help="Force rise/set elevation to 0 degrees (overrided -r).",
                        action="store_true")
    parser.add_argument("-b",
                        "--start-azimuth",
                        help="Start of the azimuth window to observe within. Window goes from start"
                        "to stop azimuth in a clockwise direction. [degrees; default: 0, "
                        "maximum: 360]",
                        type=float,
                        default=0.0)
    parser.add_argument("-e",
                        "--stop-azimuth",
                        help="End of the azimuth window to observe within. Window goes from start "
                        "to stop azimuth in a clockwise direction. [degrees; default: 360, "
                        "maximum: 360]",
                        type=float,
                        default=360.0)
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
                        metavar="PRIORITIES_FILE",
                        help="File with transmitter priorities. Should have " +
                        "columns of the form |NORAD priority UUID| like |43017 0.9" +
                        " KgazZMKEa74VnquqXLwAvD|. Priority is fractional, one transmitter " +
                        "per line, 1.0 gets maximum priority.",
                        default=None)
    parser.add_argument("-M",
                        "--min-priority",
                        help="Minimum priority. Only schedule passes with a priority higher" +
                        "than this limit [default: 0.0, maximum: 1.0]",
                        type=float,
                        default=0.)
    parser.add_argument(
        "-T",
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
    parser.add_argument("--version",
                        action="version",
                        version="satnogs-auto-scheduler {}".format(auto_scheduler_version))
    args = parser.parse_args()

    # Check arguments
    if args.station is None:
        parser.print_help()
        sys.exit()

    # Setting logging level
    numeric_level = args.log_level
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level")
    logging.basicConfig(level=numeric_level, format="%(message)s")

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

    # Set time range
    tnow = datetime.strptime(args.starttime, "%Y-%m-%dT%H:%M:%S")
    tmin = tnow
    tmax = tnow + timedelta(hours=length_hours)

    # Get ground station information
    try:
        ground_station = get_groundstation_info(ground_station_id)
    except APIRequestError:
        sys.exit(1)

    if not args.dryrun and not check_station_availability(ground_station, args.allow_testing):
        sys.exit(1)

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
    if not args.horizon:
        # Use minimum altitude for computing rise and set times (horizon to horizon otherwise)
        if args.min_riseset is None:
            min_riseset = ground_station['min_horizon']
        else:
            if args.min_riseset < 0.0:
                min_riseset = 0.0
            elif args.min_riseset > 90.0:
                min_riseset = 90.0
            else:
                min_riseset = args.min_riseset
    else:
        min_riseset = 0.0

    # Set start azimuth viewing window
    if args.start_azimuth < 0.0:
        logging.warning("Azimuth window not in range [0, 360] degrees. Setting to 0 degrees.")
        start_azimuth = 0.0
    elif args.start_azimuth > 360.0:
        logging.warning("Azimuth window not in range [0, 360] degrees. Setting to 360 degrees.")
        start_azimuth = 360.0
    else:
        start_azimuth = args.start_azimuth

    # Set stop azimuth viewing window
    if args.stop_azimuth < 0.0:
        logging.warning("Azimuth window not in the range [0, 360] degrees. Setting to 0 degrees.")
        stop_azimuth = 0.0
    elif args.stop_azimuth > 360.0:
        logging.warning("Azimuth window not in the range [0, 360] degrees. Setting to 360 degrees.")
        stop_azimuth = 360.0
    else:
        stop_azimuth = args.stop_azimuth

    max_pass_duration = args.max_observation_duration
    priorities_filename = args.priorities
    only_priority = args.only_priority
    dryrun = args.dryrun

    schedule_single_station(ground_station_id, wait_time_seconds, min_priority, tmax, tmin,
                            ground_station, min_culmination, min_riseset, start_azimuth,
                            stop_azimuth, max_pass_duration, priorities_filename, only_priority,
                            dryrun)


def schedule_single_station(ground_station_id,
                            wait_time_seconds,
                            min_priority,
                            tmax,
                            tmin,
                            ground_station,
                            min_culmination,
                            min_riseset,
                            start_azimuth,
                            stop_azimuth,
                            max_pass_duration,
                            priorities_filename,
                            only_priority,
                            dryrun,
                            skip_frequency_violators=True):
    # pylint: disable=too-many-arguments,too-many-locals

    # Create or update the transmitter & TLE cache
    cache = CacheManager(ground_station_id, ground_station['antenna'], settings.CACHE_DIR,
                         settings.CACHE_AGE, settings.MAX_NORAD_CAT_ID)
    cache.update()

    cache.update_transmitters()
    # Filter TLEs for objects of interest only
    tles = list(
        filter(lambda entry: entry['norad_cat_id'] in cache.norad_cat_ids_of_interest,
               cache.tles_all))

    # Read transmitters
    transmitters_of_interest = read_transmitters_of_interest(cache.transmitters_file)

    # Extract interesting satellites from receivable transmitters
    satellites = satellites_from_transmitters(transmitters_of_interest, tles)

    # Skip satellites with frequency misuse (avoids scheduling permission errors)
    if skip_frequency_violators:
        satellites = list(
            filter(
                lambda sat: not cache.satellites_by_norad_id[str(sat.id)]['is_frequency_violator'],
                satellites))

    # Find passes
    constraints = {
        'time': (tmin, tmax),
        'pass_duration': (settings.MIN_PASS_DURATION, max_pass_duration),
        'azimuth': (start_azimuth, stop_azimuth),
        'min_culmination': min_culmination,
    }
    logging.info(f'Search passes for {len(satellites)} satellites:')

    # Set observer
    observer = create_observer(ground_station['lat'],
                               ground_station['lng'],
                               ground_station['altitude'],
                               min_riseset=min_riseset)
    passes = []
    for satellite in tqdm(satellites, disable=None):
        passes.extend(find_constrained_passes(satellite, observer, constraints))

    priorities, favorite_transmitters = read_priorities_transmitters(priorities_filename)

    # List of scheduled passes
    try:
        logging.info('Download list of scheduled passes from SatNOGS Network...')
        scheduledpasses = get_scheduled_passes_from_network(ground_station_id, tmin, tmax)
    except APIRequestError:
        logging.error('Download from SatNOGS Network failed.')
        sys.exit(1)

    logging.info(f"Found {len(scheduledpasses)} scheduled passes "
                 f"between {tmin} and {tmax} on ground station {ground_station_id}.")

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

    print_scheduledpass_summary(scheduledpasses,
                                ground_station_id,
                                cache.satellites_by_norad_id,
                                printer=logging.info)

    # Login and schedule passes
    passes_schedule = sorted((satpass for satpass in scheduledpasses if not satpass['scheduled']),
                             key=lambda satpass: satpass['tr'])
    if (not dryrun) and passes_schedule:
        logging.info('Scheduling all unscheduled passes listed above.')
        observations = list({
            'ground_station_id': ground_station_id,
            'transmitter_uuid': satpass['transmitter']['uuid'],
            'start': satpass['tr'],
            'end': satpass['ts']
        } for satpass in passes_schedule)
        schedule_observations_batch(observations)

    logging.info("Done.")


if __name__ == '__main__':
    main()
