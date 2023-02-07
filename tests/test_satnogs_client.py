from auto_scheduler.satnogs_client import get_groundstation_info

GROUND_STATION_ID = 2


def test_get_groundstation_info():
    """
    Test the get_groundstation_info method.

    Check that station information is returned for the requested station.

    Requires SatNOGS Network to be online.
    """
    ground_station = get_groundstation_info(GROUND_STATION_ID)

    assert isinstance(ground_station, dict)
    assert 'id' in ground_station
    assert ground_station['id'] == GROUND_STATION_ID
