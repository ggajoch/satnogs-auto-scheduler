import json
import tempfile

import pytest

from auto_scheduler.cache import CacheManager
from auto_scheduler.utils import search_satellites


def key2int(dict_object):
    """
    Convert all keys to integer
    """
    return {int(key): value for key, value in dict_object.items()}


def test_search_satellites():
    """
    Unit test for search_satellites using data for a typical UHF station.
    """
    # Load input data
    with open('./tests/fixtures/transmitters_receivable.json') as fp_transmitters2:
        transmitters_receivable = json.load(fp_transmitters2)

    with open('./tests/fixtures/transmitters_stats.json') as fp_transmitters_stats:
        transmitters_stats = json.load(fp_transmitters_stats)

    with open('./tests/fixtures/tles.json') as fp_tles:
        tles_all = json.load(fp_tles)

    with open('./tests/fixtures/satellites.json') as fp_satellites:
        satellites_by_norad_id_str = json.load(fp_satellites)
    satellites_by_norad_id = key2int(satellites_by_norad_id_str)

    max_norad_cat_id = 90000
    skip_frequency_violators = True

    # Load output data
    with open('./tests/fixtures/search_satellites_output.json') as fp_output:
        norad_cat_ids_fixture = set(json.load(fp_output))

    satellites = search_satellites(transmitters_receivable, transmitters_stats, tles_all,
                                   satellites_by_norad_id, max_norad_cat_id,
                                   skip_frequency_violators)
    norad_cat_ids = set(sat.id for sat in satellites)

    assert norad_cat_ids == norad_cat_ids_fixture


@pytest.mark.skip(reason="takes approx. 4 minutes due to the transmitter statistics download")
def test_search_satellites_online():
    """
    Check that search_satellites does not return satellites with temporary norad id (>90000):
    """
    ground_station_id = 1888
    ground_station_antenna = [{
        'antenna_type': 'yagi',
        'antenna_type_name': 'Yagi',
        'band': 'UHF',
        'frequency': 430000000,
        'frequency_max': 446000000
    }]
    cache_age = 24  # hours
    max_norad_cat_id = 90000
    skip_frequency_violators = True

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = CacheManager(ground_station_id, ground_station_antenna, cache_dir, cache_age,
                             max_norad_cat_id)
        cache.update()

    satellites = search_satellites(cache.transmitters_receivable, cache.transmitters_stats,
                                   cache.tles_all, cache.satellites_by_norad_id, max_norad_cat_id,
                                   skip_frequency_violators)

    for satellite in satellites:
        assert satellite.id < 90000
