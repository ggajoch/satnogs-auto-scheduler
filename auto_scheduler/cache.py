import logging
import os
from datetime import datetime

from satellite_tle import fetch_tles

from auto_scheduler.satnogs_client import get_active_transmitter_info, \
    get_satellite_info, get_transmitter_stats


class CacheManager:
    def __init__(self, ground_station_id, ground_station_antennas, cache_dir, cache_age,
                 max_norad_cat_id):
        self.ground_station_id = ground_station_id
        self.ground_station_antennas = ground_station_antennas
        self.cache_dir = cache_dir
        self.cache_age = cache_age
        self.max_norad_cat_id = max_norad_cat_id

        self.transmitters_file = os.path.join(self.cache_dir,
                                              "transmitters_%d.txt" % self.ground_station_id)
        self.tles_file = os.path.join(self.cache_dir, "tles_%d.txt" % self.ground_station_id)
        self.last_update_file = os.path.join(self.cache_dir,
                                             "last_update_%d.txt" % ground_station_id)

        # Create cache
        if not os.path.isdir(self.cache_dir):
            os.mkdir(self.cache_dir)

    def last_update(self):
        try:
            with open(self.last_update_file, "r") as f:
                line = f.readline()
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

        logging.info('Updating transmitters and TLEs for station')
        tnow = datetime.now()

        # Store current time
        with open(self.last_update_file, "w") as fp:
            fp.write(tnow.strftime("%Y-%m-%dT%H:%M:%S") + "\n")

        # Get active transmitters in frequency range of each antenna
        transmitters = {}
        for antenna in self.ground_station_antennas:
            for transmitter in get_active_transmitter_info(antenna["frequency"],
                                                           antenna["frequency_max"]):
                transmitters[transmitter['uuid']] = transmitter

        # Get satellites which are alive
        alive_norad_cat_ids = get_satellite_info()

        # Extract NORAD IDs from transmitters
        norad_cat_ids = sorted(
            set(transmitter["norad_cat_id"] for transmitter in transmitters.values()
                if transmitter["norad_cat_id"] < self.max_norad_cat_id
                and transmitter["norad_cat_id"] in alive_norad_cat_ids))

        # Store transmitters
        fp = open(self.transmitters_file, "w")
        logging.info("Requesting transmitter success rates.")
        transmitters_stats = get_transmitter_stats()
        for transmitter in transmitters_stats:
            uuid = transmitter["uuid"]
            # Skip absent transmitters
            if uuid not in transmitters.keys():
                continue
            # Skip dead satellites
            if transmitters[uuid]["norad_cat_id"] not in alive_norad_cat_ids:
                continue

            fp.write("%05d %s %d %d %d %s\n" %
                     (transmitters[uuid]["norad_cat_id"], uuid,
                      transmitter["stats"]["success_rate"], transmitter["stats"]["good_count"],
                      transmitter["stats"]["total_count"], transmitters[uuid]["mode"]))

        logging.info("Transmitter success rates received!")
        fp.close()

        # Get TLEs
        tles = fetch_tles(norad_cat_ids)

        # Store TLEs
        with open(self.tles_file, "w") as f:
            for norad_cat_id, (source, tle) in tles.items():
                f.write("%s\n%s\n%s\n" % (tle[0], tle[1], tle[2]))