#!/usr/bin/env python3

import logging
from pathlib import Path
from tempfile import gettempdir

import pytest

from auto_scheduler.cache import CacheManager

CACHE_DIR = str(Path(gettempdir()))
CACHE_AGE = 24
MAX_NORAD_CAT_ID = 90000

GROUND_STATION_ID = 2
GROUND_STATION_ANTENNA = [{
    'frequency': 430000000,
    'frequency_max': 470000000,
    'band': 'UHF',
    'antenna_type': 'cross-yagi',
    'antenna_type_name': 'Cross Yagi'
}]


@pytest.mark.skip(reason="this test takes approx. 2 minutes")
def test_cachemanager_force_update():
    """
    Unit test for the CacheManager
    """
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    cache = CacheManager(GROUND_STATION_ID, GROUND_STATION_ANTENNA, CACHE_DIR, CACHE_AGE,
                         MAX_NORAD_CAT_ID)
    print(cache.last_update())
    print(cache.update_needed())

    cache.update(force=True)

    print(cache.last_update())
