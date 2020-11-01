#!/usr/bin/env python3
from __future__ import division

import argparse
import logging
import sys
from datetime import datetime, timedelta

import settings
from auto_scheduler import __version__ as auto_scheduler_version
from auto_scheduler.io import read_priorities_transmitters, read_tles, \
    read_transmitters
from auto_scheduler.pass_predictor import constrain_pass_to_az_window, \
    create_observer, find_passes
from auto_scheduler.satnogs_client import get_groundstation_info, \
    get_scheduled_passes_from_network, schedule_observations_batch
from auto_scheduler.schedulers import ordered_scheduler, report_efficiency
from auto_scheduler.utils import get_priority_passes, \
    print_scheduledpass_summary, satellites_from_transmitters
from cache import CacheManager
from tqdm import tqdm

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
    cache = CacheManager(ground_station_id, ground_station['antenna'], settings.CACHE_DIR,
                         settings.CACHE_AGE, settings.MAX_NORAD_CAT_ID)
    cache.update()

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

    # Set observer
    observer = create_observer(ground_station['lat'],
                               ground_station['lng'],
                               ground_station['altitude'],
                               min_riseset=min_riseset)

    # Minimum duration of a pass
    min_pass_duration = settings.MIN_PASS_DURATION

    # Read tles
    tles = list(read_tles(cache.tles_file))

    # Read transmitters
    transmitters = read_transmitters(cache.transmitters_file)

    # Extract interesting satellites from receivable transmitters
    satellites = satellites_from_transmitters(transmitters, tles)

    # Find passes
    passes = []
    logging.info('Finding all passes for %s satellites:' % len(satellites))

    # Loop over satellites
    for satellite in tqdm(satellites):
        satellite_passes = find_passes(satellite, observer, tmin, tmax, min_culmination,
                                       min_pass_duration)
        for p in satellite_passes:
            # Constrain the passes to be within the allowable viewing window
            logging.debug("Original pass is azr %f and azs %f", float(p['azr']), float(p['azs']))
            p = constrain_pass_to_az_window(satellite, observer, p, start_azimuth, stop_azimuth,
                                            min_pass_duration)

            if not p:
                logging.debug("Pass did not meet azimuth window requirements. Removed.")
                continue
            logging.debug("Adjusted pass inside azimuth window is azr %f and azs %f",
                          float(p['azr']), float(p['azs']))

            p.update({
                'satellite': {
                    'name': str(satellite.name),
                    'id': str(satellite.id),
                    'tle1': str(satellite.tle1),
                    'tle2': str(satellite.tle2)
                },
                'transmitter': {
                    'uuid': satellite.transmitter,
                    'success_rate': satellite.success_rate,
                    'good_count': satellite.good_count,
                    'data_count': satellite.data_count,
                    'mode': satellite.mode
                },
                'scheduled': False
            })
            passes.append(p)

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

    print_scheduledpass_summary(scheduledpasses, ground_station_id, printer=logging.info)

    # Login and schedule passes
    passes_schedule = sorted((satpass for satpass in scheduledpasses if not satpass['scheduled']),
                             key=lambda satpass: satpass['tr'])
    if schedule and passes_schedule:
        logging.info('Scheduling all unscheduled passes listed above.')
        observations = ({
            'ground_station_id': ground_station_id,
            'transmitter_uuid': satpass['transmitter']['uuid'],
            'start': satpass['tr'],
            'end': satpass['ts']
        } for satpass in passes_schedule)
        schedule_observations_batch(observations)

    logging.info("Done.")


if __name__ == '__main__':
    main()
