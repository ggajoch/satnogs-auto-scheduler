#!/usr/bin/env python3

import logging
from pathlib import Path
from tempfile import gettempdir

import pytest

from auto_scheduler.cache import CacheManager

CACHE_DIR = str(Path(gettempdir()))
CACHE_AGE = 24
MAX_NORAD_CAT_ID = 90000

ground_station_id = 2
ground_station_antenna = [{
    'frequency': 430000000,
    'frequency_max': 470000000,
    'band': 'UHF',
    'antenna_type': 'cross-yagi',
    'antenna_type_name': 'Cross Yagi'
}]


@pytest.mark.skip(reason="this test takes approx. 2 minutes")
def testCacheManager_force_update():
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    cache = CacheManager(ground_station_id, ground_station_antenna, CACHE_DIR, CACHE_AGE,
                         MAX_NORAD_CAT_ID)
    print(cache.last_update())
    print(cache.update_needed())

    cache.update(force=True)

    print(cache.last_update())
