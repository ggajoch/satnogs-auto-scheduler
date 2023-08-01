import logging
import math
from datetime import timedelta

import ephem

logger = logging.getLogger(__name__)


def overlap(satpass, scheduledpasses, wait_time_seconds):
    """Check if this pass overlaps with already scheduled passes"""
    # pylint: disable=invalid-name

    # No overlap
    overlap_found = False

    # Add wait time
    tr = satpass['tr']
    ts = satpass['ts'] + timedelta(seconds=wait_time_seconds)

    # Loop over scheduled passes
    for scheduledpass in scheduledpasses:
        # Test pass falls within scheduled pass
        if tr >= scheduledpass['tr'] and ts < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap_found = True
        # Scheduled pass falls within test pass
        elif scheduledpass['tr'] >= tr and scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds) < ts:
            overlap_found = True
        # Pass start falls within pass
        elif scheduledpass['tr'] <= tr < scheduledpass['ts'] + timedelta(seconds=wait_time_seconds):
            overlap_found = True
        # Pass end falls within end
        elif scheduledpass['tr'] <= ts < scheduledpass['ts'] + timedelta(seconds=wait_time_seconds):
            overlap_found = True
        if overlap_found:
            break

    return overlap_found


def create_observer(lat, lon, alt, min_riseset=0.0):
    '''
    Create an observer instance.
    '''
    # pylint: disable=assigning-non-slot
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.elevation = alt
    observer.horizon = str(min_riseset)

    return observer


def find_passes(satellite, observer, tmin, tmax, minimum_altitude, min_pass_duration):
    """
    Find passes of one satellite over a specified ground station during the selected time period.

    # Arguments
    satellite (auto_scheduler.Satellite): The satellite
    observer (ephem.Observer): The observer
    tmin (datetime.datetime): Filter start datetime
    tmax (datetime.datetime): Filter end datetime
    minimum_altitude (float): Minimum culmination height in degrees above the horizon
    min_pass_duration (float): Minimum pass duration in minutes

    # Returns
    List of sallite passes
    """
    # pylint: disable=too-many-arguments,broad-exception-caught,too-many-locals
    passes = []

    # Set start time
    observer.date = ephem.date(tmin)

    # Load TLE
    try:
        sat_ephem = ephem.readtle(str(satellite.tle0), str(satellite.tle1), str(satellite.tle2))
    except (ValueError, AttributeError):
        return []

    # Loop over passes
    while True:
        try:
            sat_ephem.compute(observer)
        except ValueError as error:
            if str(error).startswith("TLE elements are valid for a few weeks around their epoch"):
                # pylint: disable=protected-access
                age = observer.date.datetime() - sat_ephem._epoch.datetime()
                print(f"WARNING: Skip satellite {satellite.id}, TLE too old "
                      f"for predictions: {age.days} days.")
            else:
                print(f"WARNING: Skip satellite {satellite.id} due to a propagation error.")
            break

        try:
            # pylint: disable=invalid-name
            tr, azr, tt, altt, ts, azs = observer.next_pass(sat_ephem)
        except ValueError:
            break  # there will be sats in our list that fall below horizon, skip
        except TypeError:
            break  # if there happens to be a non-EarthSatellite object in the list
        except Exception as error:
            print("WARNING: Unhandled exception. "
                  "Please report this error via the satnogs-auto-scheduer Issue Tracker.")
            print(error)
            break

        if tr is None:
            break

        # using the angles module convert the sexagesimal degree into
        # something more easily read by a human
        try:
            elevation = format(math.degrees(altt), '.0f')
            azimuth_r = format(math.degrees(azr), '.0f')
            azimuth_s = format(math.degrees(azs), '.0f')
        except TypeError:
            break

        pass_duration = ts.datetime() - tr.datetime()

        # Stop search, end of time range reached.
        if not tr < ephem.date(tmax):
            break

        # Store pass only if elevation is higher than configured horizon and satellite
        # not directly overhead at the moment (tr < ts), see issue
        # satnogs-network#199 and pyephem#105 for details.
        # https://gitlab.com/librespacefoundation/satnogs/satnogs-network/-/issues/199
        # https://github.com/brandon-rhodes/pyephem/issues/105
        if (float(elevation) >= minimum_altitude and tr < ts
                and pass_duration > timedelta(minutes=min_pass_duration)):

            # get pass information
            satpass = {
                'tr': tr.datetime(),  # Rise time
                'azr': azimuth_r,  # Rise Azimuth
                'tt': tt.datetime(),  # Max altitude time
                'altt': elevation,  # Max altitude
                'ts': ts.datetime(),  # Set time
                'td': pass_duration,  # Set duration
                'azs': azimuth_s,  # Set azimuth
                'transmitter': {
                    'uuid': satellite.transmitter,
                    'success_rate': satellite.success_rate,
                    'good_count': satellite.good_count,
                    'data_count': satellite.data_count,
                    'mode': satellite.mode,
                },
                'scheduled': False
            }
            passes.append(satpass)

        observer.date = ephem.Date(ts).datetime() + timedelta(minutes=1)

    return passes


def constrain_pass_to_az_window(satellite, observer, satpass, start_azimuth, stop_azimuth,
                                min_pass_duration):
    """
    Modifies the observation start/stop time to satisfy azimuth viewing window constraints.
    For example, if there is an obstruction covering the start of the pass then the pass start time
    will be adjusted to begin only when the satellite has cleared the obstruction. This can result
    in shorter observations and more time-efficient scheduling.
    :param satellite: Satellite object the satpass is for
    :param observer: Observer
    :param satpass: Satpass to be adjusted to fit within the viewing window. Modified in-place.
    :param start_azimuth: Start of the viewing window. Viewing window is the area covered by a
    clockwise sweep from the start angle to the end angle.
    :param stop_azimuth: End of the viewing window.
    :param min_pass_duration: Minimum pass duration in minutes. Passes shorter than this are
    discarded.
    :return: The modified satpass object that satisfies the viewing window constraint, or None if
    it is impossible to satisfy the viewing window and minimum pass duration constraints
    """
    # pylint: disable=too-many-arguments

    # How much the start/stop time should be incremented by each step while finding the
    # parameters for the constrained pass. Larger values will solve quicker but will result in a
    # worse solution.
    sweep_step_size = timedelta(seconds=1)

    # Load TLE
    try:
        sat_ephem = ephem.readtle(str(satellite.tle0), str(satellite.tle1), str(satellite.tle2))
    except (ValueError, AttributeError):
        return None

    # Sweep the start of pass time forwards until the azimuth constraint is met, or another
    # constraint fails
    azr_within_window = False
    while not azr_within_window:
        # Set pass start time
        observer.date = ephem.date(satpass['tr'])
        sat_ephem.compute(observer)

        # Convert to degrees
        satpass['azr'] = format(math.degrees(sat_ephem.az), '.0f')
        pass_duration = satpass['ts'] - satpass['tr']

        azr_within_window = check_az_in_window(float(satpass['azr']), start_azimuth, stop_azimuth)

        if not azr_within_window:
            # Change the pass start time for the next iteration
            satpass['tr'] += sweep_step_size

        if pass_duration < timedelta(minutes=min_pass_duration):
            return None

    # Sweep the end of pass time backwards until the azimuth constraint is met, or another
    # constraint fails
    azs_within_window = False
    while not azs_within_window:
        # Set pass stop time
        observer.date = ephem.date(satpass['ts'])
        sat_ephem.compute(observer)

        # Convert to degrees
        satpass['azs'] = format(math.degrees(sat_ephem.az), '.0f')

        azs_within_window = check_az_in_window(float(satpass['azs']), start_azimuth, stop_azimuth)
        pass_duration = satpass['ts'] - satpass['tr']

        if not azs_within_window:
            # Change the pass stop time for the next iteration
            satpass['ts'] -= sweep_step_size

        if pass_duration < timedelta(minutes=min_pass_duration):
            return None

        satpass['td'] = pass_duration

    return satpass


def check_az_in_window(azimuth, start_azimuth, stop_azimuth):
    """
    Determines whether a given azimuth angle is between two specified start/stop azimuth angles.
    In effect, checks that an azimuth is within an acceptable viewing window.
    :param azimuth: Azimuth to be tested
    :param start_azimuth: Start of the viewing window. Viewing window is the area covered by a
    clockwise sweep from the start angle to the end angle.
    :param stop_azimuth: End of the viewing window.
    :return: True if the specified azimuth is contained inside the viewing window.
    """

    # Determine if the specified viewing window crosses zero degrees
    # If so, we perform the window check with a complementary window and invert the result
    if start_azimuth > stop_azimuth:
        complementary_window = True

        # Swap start and stop which inverts the window and avoids the zero crossing
        start_azimuth, stop_azimuth = stop_azimuth, start_azimuth
    else:
        complementary_window = False

    # Check if the specified azimuth is inside the window
    if start_azimuth <= azimuth <= stop_azimuth:
        # Azimuth is within the window (normal or complementary)
        return not complementary_window

    # Azimuth is outside the window (normal or complementary)
    return complementary_window


def constrain_pass_to_max_observation_duration(satpass, max_pass_duration, tmin, tmax):
    """
    Determines wheather a given observation duration time exceeds the time to record an
    observation. In case the calculated recording time is longer then the max_pass_duration
    the start and end values are shortened to have the optimal recording time above the horizon
    for the given satellite.
    :param satpass: Satpass to be adjusted to fit within the recording duration. Modified
    in-place.
    :param max_pass_duration: Maximum pass duration in minutes. Passes longer than this are
    shortned.
    :param tmin: Earliest time for a schedule
    :param tmax: Latest time for a schedule
    :return: The modified satpass object that satisfies the record duration constraint.
    """

    max_duration = timedelta(minutes=max_pass_duration)

    if satpass['td'] > max_duration:
        half = (satpass['td'] - max_duration) / 2

        # Max elevation fits within time frame
        if satpass['tr'] + half >= tmin and satpass['ts'] - half <= tmax:
            satpass['tr'] += half
            satpass['ts'] -= half
        else:
            satpass['ts'] = min(satpass['ts'], tmax)
            satpass['tr'] = satpass['ts'] - max_duration

        satpass['td'] = satpass['ts'] - satpass['tr']

    return satpass


def constrain_pass_to_angular_separation(satellite, observer, satpass, angular_separation):
    """
    Determines whether a given observation passes within max-separation of the antenna direction.
    :param satellite: Satellite object the satpass is for.
    :param satpass: Satpass to be adjusted to fit within the recording duration.
    :param observer: Observer.
    :param angular_separation: list of max_separation, pointing_az, pointing_el
    :return: The satpass object that satisfies the pointing constraint, or None.
    """
    # Un-pack arguments
    max_separation, pointing_az, pointing_el = angular_separation

    # Load TLE
    try:
        sat_ephem = ephem.readtle(str(satellite.tle0), str(satellite.tle1), str(satellite.tle2))
    except (ValueError, AttributeError):
        return None

    num_steps = 127
    min_separation = 10  # >2*pi, cover entire sky
    if max_separation:
        for time_step in [
                satpass['tr'] + x * (satpass['ts'] - satpass['tr']) / (num_steps - 1)
                for x in range(num_steps)
        ]:
            observer.date = ephem.date(time_step)
            sat_ephem.compute(observer)
            separation = ephem.separation((math.radians(pointing_az), math.radians(pointing_el)),
                                          (sat_ephem.az, sat_ephem.alt))
            if separation < min_separation:
                min_separation = separation
        logging.debug(
            f"Angular separation for {sat_ephem.name} is {math.degrees(min_separation):.1f}")
        if min_separation > math.radians(max_separation):
            return None
    return satpass


def find_constrained_passes(satellite, observer, constraints):
    """
    Find passes of one satellite over a specified ground station while
    taking multiple constraints into account.

    # Supported constraints
    - time range (tmin (datetime), tmax (datetime))
    - pass duration (min (float), max (float)): Pass duration in minutes
    - azimuth window (start (float), stop (float)): azimuth in degrees; Use (0.0, 360.0) to disable
    - min_culmination (float): Minimum culmination elevation in degrees; Use 0.0 to disable
    - angular_separation (max_separation (float), pointing_az (float), pointing_el (float)):
      Maximum angular separation; use max_separation as None to disable

    # Arguments
    satellite (auto_scheduler.Satellite): The satellite
    observer (ephem.Observer): The observer
    constaints (dict): The constraints
    """
    # Un-pack arguments
    tmin, tmax = constraints['time']
    min_pass_duration, max_pass_duration = constraints['pass_duration']
    start_azimuth, stop_azimuth = constraints['azimuth']
    min_culmination = constraints['min_culmination']
    angular_separation = constraints['angular_separation']

    selected_passes = []
    satellite_passes = find_passes(satellite, observer, tmin, tmax, min_culmination,
                                   min_pass_duration)
    for satpass in satellite_passes:
        # Constrain the passes to be within the allowable viewing window
        logging.debug("Original pass is azr %f and azs %f", float(satpass['azr']),
                      float(satpass['azs']))
        satpass = constrain_pass_to_az_window(satellite, observer, satpass, start_azimuth,
                                              stop_azimuth, min_pass_duration)

        if not satpass:
            logging.debug("Pass did not meet azimuth window requirements. Removed.")
            continue

        satpass = constrain_pass_to_angular_separation(satellite, observer, satpass,
                                                       angular_separation)

        if not satpass:
            logging.debug("Pass did not meet max angular separation requirements. Removed.")
            continue

        logging.debug("Adjusted pass inside azimuth window is azr %f and azs %f",
                      float(satpass['azr']), float(satpass['azs']))

        logging.debug(f"Original pass for {str(satellite.id)}"
                      f"is start {satpass['tr']} and end {satpass['ts']}")
        satpass = constrain_pass_to_max_observation_duration(satpass, max_pass_duration, tmin, tmax)
        logging.debug(f"Adjusted max observation duration for {satellite.name} "
                      f"to start {satpass['tr']} and end {satpass['ts']}")

        # pylint: disable=duplicate-code
        # NOTE: The transmitter was already added by find_passes initially.
        #       Why do we set it here again?
        # Additionally, setting the satellite in find_passes directly would be cleaner.
        satpass.update({
            'satellite': {
                'name': str(satellite.name),
                'id': str(satellite.id),
                'tle1': str(satellite.tle1),
                'tle2': str(satellite.tle2)
            },
            'transmitter': {
                'uuid': satellite.transmitter,
                'success_rate': satellite.success_rate,
                'good_count': satellite.good_count,
                'data_count': satellite.data_count,
                'mode': satellite.mode
            },
            'scheduled': False
        })
        selected_passes.append(satpass)
    return selected_passes
