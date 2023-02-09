from datetime import datetime, timedelta

import pytest

from auto_scheduler.satnogs_client import get_active_transmitter_info, get_groundstation_info, \
    get_satellite_info, get_scheduled_passes_from_network, get_tles, get_transmitter_stats


def test_get_groundstation_info():
    """
    Test the get_groundstation_info method.

    Check that station information is returned for the requested station.

    Requires SatNOGS Network to be online.
    """
    ground_station_id = 2
    ground_station = get_groundstation_info(ground_station_id)

    assert isinstance(ground_station, dict)
    assert 'id' in ground_station
    assert ground_station['id'] == ground_station_id


def test_get_satellite_info():
    """
    Unit test for get_satellite_info
    """
    norad_cat_ids_alive, satellites_catalog = get_satellite_info()

    assert isinstance(norad_cat_ids_alive, list)
    assert isinstance(satellites_catalog, dict)
    assert norad_cat_ids_alive[0] in satellites_catalog
    assert 'norad_cat_id' in satellites_catalog[norad_cat_ids_alive[0]]


def test_get_active_transmitter_info():
    fmin, fmax = 430_000_000, 470_000_000
    transmitters = get_active_transmitter_info(fmin, fmax)
    assert isinstance(transmitters, list)
    assert isinstance(transmitters[0], dict)
    assert 'mode' in transmitters[0]
    assert 'norad_cat_id' in transmitters[0]
    assert 'uuid' in transmitters[0]


def test_get_tles():
    """
    Unit test for get_tles
    """
    tles = get_tles()
    assert isinstance(tles, list)


@pytest.mark.skip(reason="slow, approx. 4min; requires pagination through >50 pages")
def test_get_transmitter_stats():
    """
    Unit test for get_transmitter_stats
    """
    transmitters = get_transmitter_stats()
    assert isinstance(transmitters, list)


def test_get_scheduled_passes_from_network():
    """
    Unit test for get_scheduled_passes_from_network
    """
    # Input
    ground_station_id = 2
    tmin = datetime.fromisoformat('2023-02-09T19:42:47')
    tmax = datetime.fromisoformat('2023-02-09T20:12:47')

    # Output
    pass_result = {
        'altt': 14.0,
        'priority': 1,
        'satellite': {
            'id': 55123,
            'name': ''
        },
        'scheduled': True,
        'td': timedelta(seconds=380),
        'tr': datetime(2023, 2, 9, 19, 38, 56),
        'transmitter': {
            'mode': '',
            'uuid': 'eQnHaHRLfpdRtLHGSbrt75'
        },
        'ts': datetime(2023, 2, 9, 19, 45, 16)
    }

    scheduledpasses = get_scheduled_passes_from_network(ground_station_id, tmin, tmax)

    assert isinstance(scheduledpasses, list)
    assert len(scheduledpasses) == 1
    for key, expected_value in pass_result.items():
        assert scheduledpasses[0][key] == expected_value
