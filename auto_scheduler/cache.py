import json
import logging
import os
import sys
from datetime import datetime

from auto_scheduler import settings
from auto_scheduler.satnogs_client import APIRequestError, get_active_transmitter_info, \
    get_satellite_info, get_tles, get_transmitter_stats

logger = logging.getLogger(__name__)


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
    transmitters_receivable = None
    norad_cat_ids_alive = None
    norad_cat_ids_of_interest = None
    satellites_by_norad_id = None
    tles_all = None

    def __init__(self, ground_station_id, ground_station_antennas, cache_dir, cache_age):
        # pylint: disable=too-many-arguments
        self.ground_station_id = ground_station_id
        self.ground_station_antennas = ground_station_antennas
        self.cache_dir = cache_dir
        self.cache_age = cache_age

        self.transmitters_file = os.path.join(self.cache_dir,
                                              f"transmitters_{self.ground_station_id}.txt")
        self.transmitters2_file = os.path.join(self.cache_dir,
                                               f"transmitters_{self.ground_station_id}.json")
        self.last_update_file = os.path.join(self.cache_dir, f"last_update_{ground_station_id}.txt")

        self.tles_file = os.path.join(self.cache_dir, "tles.json")
        self.transmitters_stats_file = os.path.join(self.cache_dir, "transmitters_stats.json")
        self.satellites_file = os.path.join(self.cache_dir, "satellites.json")
        self.satellites2_file = os.path.join(self.cache_dir, "satellites2.json")

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

        required_files = [
            self.transmitters_file, self.tles_file, self.transmitters_stats_file,
            self.satellites_file
        ]
        for filename in required_files:
            if not os.path.isfile(filename):
                return True
        return False

    def update(self, force=False):
        """
        Update the Cache if necessary (or forced) and provide the downloaded or already cached
        data via instance attributes.

        Once this method was called, the following instance attributes are available:
        - satellites_by_norad_id (dict(int -> dict))
        - norad_cat_ids_alive (list(str))
        - transmitters_stats (dict(str->dict))
        - transmitters_receivable (dict(str->dict))
        - tles_all (list(dict))
        """
        logging.info('Update satellites, transmitters, transmitter statistics and TLEs:')
        tnow = datetime.now()

        if force or self.update_needed():
            self.fetch_satellites()
            self.fetch_transmitters_stats()
            self.fetch_transmitters_receivable()
            self.fetch_tles()

            # Store current time
            with open(self.last_update_file, "w") as fp_last_update:
                fp_last_update.write(f'{tnow:%Y-%m-%dT%H:%M:%S}\n')
        else:

            def key2int(dict_object):
                """
                Convert all keys to integer
                """
                return {int(key): value for key, value in dict_object.items()}

            with open(self.satellites_file) as fp_satellites:
                satellites_by_norad_id_str = json.load(fp_satellites)

            self.satellites_by_norad_id = key2int(satellites_by_norad_id_str)

            self.norad_cat_ids_alive = self.satellites_by_norad_id.keys()

            with open(self.transmitters_stats_file) as fp_transmitters_stats:
                self.transmitters_stats = json.load(fp_transmitters_stats)

            with open(self.transmitters2_file) as fp_transmitters2:
                self.transmitters_receivable = json.load(fp_transmitters2)

            # Read tles
            with open(self.tles_file) as fp_tles:
                self.tles_all = json.load(fp_tles)

    def fetch_transmitters_stats(self):
        logging.info(
            "Download transmitter statistics from SatNOGS Network (this may take some minutes)...")
        try:
            transmitters_stats_list = get_transmitter_stats()
        except APIRequestError:
            logging.error('Download from SatNOGS Network failed.')
            sys.exit(1)

        self.transmitters_stats = {}
        for transmitter in transmitters_stats_list:
            self.transmitters_stats[transmitter['uuid']] = transmitter['stats']

        with open(self.transmitters_stats_file, "w") as fp_transmitters_stats:
            json.dump(self.transmitters_stats, fp_transmitters_stats, indent=2)

    def fetch_satellites(self):
        """
        Download the catalog of satellites from SatNOGS DB.

        Store the data in two formats:
        - Filtered by satellites which have a norad id and are alive,
          indexed by norad id (DEPRECATED)
        - All satellites, indexed by sat id (SatNOGS Satellite ID) plus
          the mapping between norad id and sat id
        """
        try:
            logger.info('Download satellite information from SatNOGS DB...')
            satellites_list = get_satellite_info()
        except APIRequestError:
            logger.error('Download from SatNOGS DB failed.')
            sys.exit(1)

        satellites_by_sat_id = {}
        satellites_by_norad_id = {}
        norad_to_sat_id = {}
        norad_cat_ids_alive = []

        for satellite in satellites_list:
            if satellite['norad_cat_id'] in norad_to_sat_id:
                print('WARNING: Duplicated NORAD ID found! '
                      f'{satellite["sat_id"]}  vs '
                      f'{satellites_by_sat_id[norad_to_sat_id[satellite["norad_cat_id"]]]}')
                continue

            if satellite['norad_cat_id'] is None:
                print(f'INFO: Skip Satellite {satellite["sat_id"]} with missing NORAD ID '
                      'since having an assigned or temporary NORAD ID is required for scheduling.')
                print(satellite)
                continue

            satellites_by_sat_id[satellite['sat_id']] = satellite
            norad_to_sat_id[satellite['norad_cat_id']] = satellite['sat_id']

            # DEPRECATED:
            # Search satellites which have a norad_cat_id and are alive, indexed by norad id
            if satellite['norad_cat_id'] is None:
                continue
            if not satellite["status"] == "alive":
                continue

            norad_cat_ids_alive.append(satellite["norad_cat_id"])
            satellites_by_norad_id[satellite["norad_cat_id"]] = satellite

        data = {'satellites': satellites_by_sat_id, 'norad_to_sat_id': norad_to_sat_id}
        with open(self.satellites2_file, "w") as fp_satellites:
            json.dump(data, fp_satellites, indent=2)

        with open(self.satellites_file, "w") as fp_satellites:
            json.dump(satellites_by_norad_id, fp_satellites, indent=2)

        self.norad_cat_ids_alive = norad_cat_ids_alive
        self.satellites_by_norad_id = satellites_by_norad_id

    def fetch_transmitters_receivable(self):
        """
        Get active transmitters in frequency range of each antenna
        """
        self.transmitters_receivable = {}

        for antenna in self.ground_station_antennas:
            logging.info('Download list of active transmitters between '
                         f'{antenna["frequency"] * 1e-6:.0f} and '
                         f'{antenna["frequency_max"] * 1e-6:.0f} MHz from SatNOGS DB...')

            try:
                transmitters = get_active_transmitter_info(antenna["frequency"],
                                                           antenna["frequency_max"])
            except APIRequestError:
                logging.error("Download from SatNOGS DB failed.")
                sys.exit(1)

            for transmitter in transmitters:
                self.transmitters_receivable[transmitter['uuid']] = transmitter

        with open(self.transmitters2_file, "w") as fp_transmitters2:
            json.dump(self.transmitters_receivable, fp_transmitters2, indent=2)

    def update_transmitters(self):
        # Extract NORAD IDs from transmitters
        self.norad_cat_ids_of_interest = sorted(
            set(transmitter["norad_cat_id"]
                for transmitter in self.transmitters_receivable.values()
                if transmitter["norad_cat_id"] in self.norad_cat_ids_alive))

        # Store transmitters
        with open(self.transmitters_file, "w") as fp_transmitters:
            logging.info("Filter transmitters based on ground station capability.")
            for uuid, stats in self.transmitters_stats.items():
                # Skip transmitters which do not have statistics in SatNOGS Network (yet)
                if uuid not in self.transmitters_receivable:
                    continue

                # Skip dead satellites
                if self.transmitters_receivable[uuid][
                        "norad_cat_id"] not in self.norad_cat_ids_alive:
                    continue

                # pylint: disable=consider-using-f-string
                fp_transmitters.write(
                    "%05d %s %d %d %d %s\n" %
                    (self.transmitters_receivable[uuid]["norad_cat_id"], uuid,
                     stats["success_rate"], stats["good_count"], stats["total_count"],
                     self.transmitters_receivable[uuid]["mode"]))

    def fetch_tles(self):
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
        logging.info('Download TLEs from SatNOGS DB...')
        try:
            self.tles_all = get_tles()
        except APIRequestError:
            logging.error('Download from SatNOGS DB failed.')
            sys.exit(1)

        with open(self.tles_file, "w") as fp_tles:
            json.dump(self.tles_all, fp_tles, indent=2)

    def flush_cache(self):
        """
        Flush the cache so a current set of transmitters, satellites and TLE can be downloaded.
        """
        logging.info('Flushing cache.')
        cache = [
            self.transmitters_file,
            self.transmitters2_file,
            self.last_update_file,
            self.tles_file,
            self.transmitters_stats_file,
            self.satellites_file,
            self.satellites2_file,
        ]
        for cachefile in cache:
            if os.path.exists(cachefile):
                os.remove(cachefile)
