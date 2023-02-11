"""
Unit tests for the pass predictor
"""
import tomli

from auto_scheduler.io import read_tles, read_transmitters_of_interest
from auto_scheduler.pass_predictor import create_observer, find_passes
from auto_scheduler.utils import satellites_from_transmitters

TIMEDELTA_RESOLUTION = 1  # seconds


def assert_pass(pass0, pass1):
    """
    Check that both provided passes are equal in rise & set times and locations.

    Quirk: ephem returns azr, altt and azs as type str.
    This method transparently convert those to float.
    """
    for key in ['tr', 'tt', 'ts']:
        assert (pass0[key] - pass1[key]).total_seconds() < TIMEDELTA_RESOLUTION

    for key in ['azr', 'altt', 'azs']:
        if isinstance(pass0[key], str):
            value0 = float(pass0[key])
        else:
            value0 = pass0[key]

        if isinstance(pass1[key], str):
            value1 = float(pass1[key])
        else:
            value1 = pass1[key]

        assert value0 == value1


def test_find_passes():
    """
    Test the find_passes method with a number of satellites
    """

    with open('tests/fixtures/pass_prediction1.toml', 'rb') as test_case_file:
        test_case = tomli.load(test_case_file)

    tles = list(read_tles(test_case['files']['tles_filename']))
    transmitters = list(read_transmitters_of_interest(test_case['files']['transmitters_filename']))

    # Extract interesting satellites from receivable transmitters
    satellites = satellites_from_transmitters(transmitters, tles)

    # Find all passes for station 2, given the transmitters and tles
    observer = create_observer(test_case['ground_station']['lat'],
                               test_case['ground_station']['lng'],
                               test_case['ground_station']['altitude'],
                               min_riseset=test_case['ground_station']['min_horizon'])

    # Loop over satellites
    passes = []
    for satellite in satellites:
        passes.extend(
            find_passes(satellite, observer, test_case['tmin'], test_case['tmax'],
                        test_case['min_culmination'], test_case['min_pass_duration']))

    # Check that the expected number of passes was found
    assert len(passes) == test_case['passes']['count']

    # Make sure the rise/transit/set time is within the expected range for the first pass
    # Make sure the rise/transit/set azimuth is equal to the expected value
    assert_pass(passes[0], test_case['passes']['first_pass'])
