import json
import logging
import os
from datetime import datetime

from auto_scheduler import settings
from auto_scheduler.satnogs_client import get_active_transmitter_info, get_satellite_info, \
    get_tles, get_transmitter_stats


class CacheManager:
    """
    ## Notes

    norad_cat_ids_of_interest match the following conditions:
    - alive
    - receivable by the station
    - not a temporary norad id
    """
    # pylint: disable=too-many-instance-attributes
    transmitters_stats = None
    alive_norad_cat_ids = None
    norad_cat_ids_of_interest = None

    def __init__(self, ground_station_id, ground_station_antennas, cache_dir, cache_age,
                 max_norad_cat_id):
        # pylint: disable=too-many-arguments
        self.ground_station_id = ground_station_id
        self.ground_station_antennas = ground_station_antennas
        self.cache_dir = cache_dir
        self.cache_age = cache_age
        self.max_norad_cat_id = max_norad_cat_id

        self.transmitters_file = os.path.join(self.cache_dir,
                                              f"transmitters_{self.ground_station_id}.txt")
        self.tles_file = os.path.join(self.cache_dir, f"tles_{self.ground_station_id}.json")
        self.last_update_file = os.path.join(self.cache_dir, f"last_update_{ground_station_id}.txt")

        self.transmitters_stats_file = os.path.join(self.cache_dir, "transmitters_stats.json")
        self.satellites_file = os.path.join(self.cache_dir, "satellites.json")

        # Create cache
        if not os.path.isdir(self.cache_dir):
            os.mkdir(self.cache_dir)

    def last_update(self):
        try:
            with open(self.last_update_file, "r") as fp_last_update:
                line = fp_last_update.readline()
            return datetime.strptime(line.strip(), "%Y-%m-%dT%H:%M:%S")
        except IOError:
            return None

    def update_needed(self):
        tnow = datetime.now()

        # Get last update
        tlast = self.last_update()

        if tlast is None or (tnow - tlast).total_seconds() > self.cache_age * 3600:
            return True
        if not os.path.isfile(self.transmitters_file):
            return True
        if not os.path.isfile(self.tles_file):
            return True
        return False

    def update(self, force=False):
        if not force and not self.update_needed():
            # Cache is valid, skip the update
            return

        logging.info('Updating transmitters, transmitter statistics and TLEs')
        tnow = datetime.now()

        self.update_transmitters()
        self.update_tles(self.norad_cat_ids_of_interest)

        # Store current time
        with open(self.last_update_file, "w") as fp_last_update:
            fp_last_update.write(f'{tnow:%Y-%m-%dT%H:%M:%S}\n')

    def fetch_transmitters_stats(self):
        logging.info("Fetch transmitter statistics...")
        self.transmitters_stats = get_transmitter_stats()
        with open(self.transmitters_stats_file, "w") as fp_transmitters_stats:
            json.dump(self.transmitters_stats, fp_transmitters_stats, indent=2)
        logging.info("Transmitter statistics received.")

    def fetch_satellites(self):
        """
        Download the catalog of satellites from SatNOGS DB,
        extract which satellites are alive.
        """
        self.alive_norad_cat_ids, satellites_catalog = get_satellite_info()
        with open(self.satellites_file, "w") as fp_satellites:
            json.dump(satellites_catalog, fp_satellites, indent=2)

    def update_transmitters(self):
        # pylint: disable=consider-using-f-string
        self.fetch_satellites()
        self.fetch_transmitters_stats()

        # Get active transmitters in frequency range of each antenna
        transmitters = {}
        for antenna in self.ground_station_antennas:
            for transmitter in get_active_transmitter_info(antenna["frequency"],
                                                           antenna["frequency_max"]):
                transmitters[transmitter['uuid']] = transmitter

        # Extract NORAD IDs from transmitters
        self.norad_cat_ids_of_interest = sorted(
            set(transmitter["norad_cat_id"] for transmitter in transmitters.values()
                if transmitter["norad_cat_id"] < self.max_norad_cat_id
                and transmitter["norad_cat_id"] in self.alive_norad_cat_ids))

        # Store transmitters
        with open(self.transmitters_file, "w") as fp_transmitters:
            logging.info("Search for interesting transmitters.")
            for transmitter in self.transmitters_stats:
                uuid = transmitter["uuid"]
                # Skip absent transmitters
                if uuid not in transmitters:
                    continue
                # Skip dead satellites
                if transmitters[uuid]["norad_cat_id"] not in self.alive_norad_cat_ids:
                    continue

                fp_transmitters.write(
                    "%05d %s %d %d %d %s\n" %
                    (transmitters[uuid]["norad_cat_id"], uuid, transmitter["stats"]["success_rate"],
                     transmitter["stats"]["good_count"], transmitter["stats"]["total_count"],
                     transmitters[uuid]["mode"]))

            logging.info("Transmitter search finished.")

    def update_tles(self, norad_cat_ids):
        """
        Download TLEs from SatNOGS DB.
        Requires a SatNOGS DB API Token!

        Deprecation Notes:
        The previous method of using satellite_tle.fetch_tles was removed!

        Old description:
        This method collects data from various sources. This will take quite some time and
        a lot of seperate requests depending on the type and
        number of requested objects (slow, DEPRECATED)
        """
        if not settings.SATNOGS_DB_API_TOKEN:
            logging.error('The previous method of fetching TLEs from various sorces was removed. '
                          'Please configure SATNOGS_DB_API_TOKEN to enable the new method of '
                          'fetching TLEs from SatNOGS DB! ')

        # Method 1: Use authenticated SatNOGS DB access
        logging.info("Downloading TLEs from satnogs-db.")
        tle_data = get_tles()

        # Filter objects of interest only
        tles = list(filter(lambda entry: entry['norad_cat_id'] in norad_cat_ids, tle_data))

        with open(self.tles_file, "w") as fp_tles:
            json.dump(tles, fp_tles, indent=2)
