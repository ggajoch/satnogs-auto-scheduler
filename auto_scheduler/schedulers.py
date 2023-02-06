import logging
import random

from .pass_predictor import overlap


def ordered_scheduler(passes, scheduledpasses, wait_time_seconds):
    """Loop through a list of ordered passes and schedule each next one that fits"""
    # Loop over passes
    for satpass in passes:
        # Schedule if there is no overlap with already scheduled passes
        if not overlap(satpass, scheduledpasses, wait_time_seconds):
            scheduledpasses.append(satpass)

    return scheduledpasses


def random_scheduler(passes, scheduledpasses, wait_time_seconds):
    """Schedule passes based on random ordering"""
    # Shuffle passes
    random.shuffle(passes)

    return ordered_scheduler(passes, scheduledpasses, wait_time_seconds)


def report_efficiency(scheduledpasses, passes):
    # pylint: disable=consider-using-f-string

    if scheduledpasses:
        # Loop over passes
        start = False
        for satpass in scheduledpasses:
            if not start:
                dt = satpass['ts'] - satpass['tr']
                tmin = satpass['tr']
                tmax = satpass['ts']
                start = True
            else:
                dt += satpass['ts'] - satpass['tr']
                if satpass['tr'] < tmin:
                    tmin = satpass['tr']
                if satpass['ts'] > tmax:
                    tmax = satpass['ts']
        # Total time covered
        dttot = tmax - tmin

        logging.info("%d passes selected out of %d, %.0f s out of %.0f s at %.3f%% efficiency" %
                     (len(scheduledpasses), len(passes), dt.total_seconds(), dttot.total_seconds(),
                      100 * dt.total_seconds() / dttot.total_seconds()))

    else:
        logging.info("No appropriate passes found for scheduling.")
