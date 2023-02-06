#!/usr/bin/env python3
import argparse
import logging
import sys

import auto_scheduler.settings as settings
from auto_scheduler.cache import CacheManager
from auto_scheduler.io import read_tles, read_transmitters
from auto_scheduler.satnogs_client import get_groundstation_info
from auto_scheduler.utils import satellites_from_transmitters


class Preference:
    """Preference class"""

    def __init__(self, search_term, success_rate, priority):
        """Initialize a preference"""
        self.search_term = search_term
        self.success_rate = success_rate / 100
        self.priority = priority

    def __repr__(self):
        return "%s %f %f" % (self.search_term, self.success_rate, self.priority)

    def is_candidate(self, sat):
        # check if sat's name or transmitter is in our list
        return bool((self.success_rate <= sat.success_rate)
                    and (self.search_term in sat.mode or self.search_term in sat.name))


def main(station_id, constrains_file, priorities_file):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    logging.info("Reading file with prefs")
    prefered_priorities = []
    with open(constrains_file, "r") as prio_file:
        for i in prio_file.readlines():
            # in case empty lines or comments
            if len(i) <= 1 or i[0] in ("#", "", " "):
                continue
            tmp = i.split(",")
            try:
                prf = Preference(tmp[0], float(tmp[1]), float(tmp[2]))
                prefered_priorities.append(prf)
            except Exception as err:
                logging.error(err)

    ground_station = get_groundstation_info(station_id, allow_testing=True)
    cache = CacheManager(station_id, ground_station['antenna'], settings.CACHE_DIR,
                         settings.CACHE_AGE, settings.MAX_NORAD_CAT_ID)
    logging.info(f'Last cache update: {cache.last_update()}')
    logging.info(f'Cache update needed: {cache.update_needed()}')
    cache.update()

    # Read tles
    tles = list(read_tles(cache.tles_file))

    # Read transmitters
    transmitters = read_transmitters(cache.transmitters_file)

    # Extract interesting satellites from receivable transmitters
    satellites = satellites_from_transmitters(transmitters, tles)

    # crosscheck the list of satellites and priorities
    sat_list = {}
    for sat in satellites:
        for prio in prefered_priorities:
            # if the sat is in the list and prio smaller that the new one
            if sat_list.get(sat.id) is not None:
                if sat_list[sat.id][1] < prio.priority:
                    if prio.is_candidate(sat):
                        sat_list[sat.id] = (sat.id, prio.priority, sat.transmitter)
            else:
                if prio.is_candidate(sat):
                    sat_list[sat.id] = (sat.id, prio.priority, sat.transmitter)

    # save the priorities in the file
    with open(priorities_file, "w") as out_file:
        for elem in sat_list.values():
            out_file.writelines("{} {} {}\n".format(elem[0], elem[1], elem[2]))

    logging.info(f'Done, output file written: {priorities_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Generate a priority list from a set of constraints given in a file.")
    parser.add_argument("-s", "--station", help="Ground station ID", type=int)
    parser.add_argument("CONSTRAINS_FILE", help="Input Priorities constrains file", type=str)
    parser.add_argument("PRIORITIES_FILE", help="Output Priorities file", type=str)
    args = parser.parse_args()

    # Check arguments
    if args.station is None:
        parser.print_help()
        sys.exit()

    main(args.station, args.CONSTRAINS_FILE, args.PRIORITIES_FILE)
