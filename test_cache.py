#!/usr/bin/env python3

from datetime import datetime
import logging
import settings

from cache import CacheManager
from utils import get_groundstation_info


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    ground_station_id = 2
    ground_station = get_groundstation_info(ground_station_id, allow_testing=True)
    print(ground_station)

    cache = CacheManager(ground_station_id,
                         ground_station['antenna'],
                         settings.CACHE_DIR,
                         settings.CACHE_AGE,
                         settings.MAX_NORAD_CAT_ID)
    print(cache.last_update())
    print(cache.update_needed())

    cache.update(force=True)

    print(cache.last_update())
