import math
from datetime import timedelta

import ephem


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
    passes = []

    # Set start time
    observer.date = ephem.date(tmin)

    # Load TLE
    try:
        sat_ephem = ephem.readtle(str(satellite.tle0), str(satellite.tle1), str(satellite.tle2))
    except (ValueError, AttributeError):
        return []

    # Loop over passes
    keep_digging = True
    while keep_digging:
        try:
            sat_ephem.compute(observer)
        except ValueError as error:
            if str(error).startswith("TLE elements are valid for a few weeks around their epoch"):
                # pylint: disable=protected-access
                age = observer.date.datetime() - sat_ephem._epoch.datetime()
                print(f"ERROR: TLE too old: {age}")
                print(satellite.tle0.strip())
                print(satellite.tle1.strip())
                print(satellite.tle2.strip())
            break
        try:
            # pylint: disable=invalid-name
            tr, azr, tt, altt, ts, azs = observer.next_pass(sat_ephem)
        except ValueError:
            break  # there will be sats in our list that fall below horizon, skip
        except TypeError:
            break  # if there happens to be a non-EarthSatellite object in the list
        except Exception:
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

        # show only if >= configured horizon and till tmax,
        # and not directly overhead (tr < ts see issue 199)

        if tr < ephem.date(tmax):
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
        else:
            keep_digging = False

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
