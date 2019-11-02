import ephem
import math

from datetime import datetime, timedelta


def overlap(satpass, scheduledpasses, wait_time_seconds):
    """Check if this pass overlaps with already scheduled passes"""
    # No overlap
    overlap = False

    # Add wait time
    tr = satpass['tr']
    ts = satpass['ts'] + timedelta(seconds=wait_time_seconds)

    # Loop over scheduled passes
    for scheduledpass in scheduledpasses:
        # Test pass falls within scheduled pass
        if tr >= scheduledpass['tr'] and ts < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        # Scheduled pass falls within test pass
        elif scheduledpass['tr'] >= tr and scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds) < ts:
            overlap = True
        # Pass start falls within pass
        elif tr >= scheduledpass['tr'] and tr < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        # Pass end falls within end
        elif ts >= scheduledpass['tr'] and ts < scheduledpass['ts'] + timedelta(
                seconds=wait_time_seconds):
            overlap = True
        if overlap:
            break

    return overlap


def find_passes(satellite,
                observer,
                tmin,
                tmax,
                minimum_altitude,
                min_pass_duration):
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
        sat_ephem.compute(observer)
        try:
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
            if (float(elevation) >= minimum_altitude and tr < ts and
                    pass_duration > timedelta(minutes=min_pass_duration)):
                valid = True

                # invalidate passes that start too soon
                if tr < ephem.Date(datetime.now() + timedelta(minutes=5)):
                    valid = False

                # get pass information
                satpass = {
                    'mytime': str(observer.date),
                    'name': str(satellite.name),
                    'id': str(satellite.id),
                    'tle1': str(satellite.tle1),
                    'tle2': str(satellite.tle2),
                    'tr': tr.datetime(),  # Rise time
                    'azr': azimuth_r,  # Rise Azimuth
                    'tt': tt.datetime(),  # Max altitude time
                    'altt': elevation,  # Max altitude
                    'ts': ts.datetime(),  # Set time
                    'azs': azimuth_s,  # Set azimuth
                    'valid': valid,
                    'uuid': satellite.transmitter,
                    'success_rate': satellite.success_rate,
                    'good_count': satellite.good_count,
                    'data_count': satellite.data_count,
                    'mode': satellite.mode,
                    'scheduled': False
                }
                passes.append(satpass)
            observer.date = ephem.Date(ts).datetime() + timedelta(minutes=1)
        else:
            keep_digging = False
            
    return passes
