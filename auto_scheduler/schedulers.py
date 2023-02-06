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
    if scheduledpasses:
        # Loop over passes
        start = False
        for satpass in scheduledpasses:
            if not start:
                duration_scheduled = satpass['ts'] - satpass['tr']
                tmin = satpass['tr']
                tmax = satpass['ts']
                start = True
            else:
                duration_scheduled += satpass['ts'] - satpass['tr']
                if satpass['tr'] < tmin:
                    tmin = satpass['tr']
                if satpass['ts'] > tmax:
                    tmax = satpass['ts']
        # Total time covered
        duration_total = tmax - tmin

        efficency = 100 * duration_scheduled.total_seconds() / duration_total.total_seconds()
        logging.info(f"{len(scheduledpasses):d} passes selected out of {len(passes):d}, "
                     f"{duration_scheduled.total_seconds():.0f} s out of "
                     f"{duration_total.total_seconds():.0f} s "
                     f"at {efficency:.3f}% efficiency")

    else:
        logging.info("No appropriate passes found for scheduling.")
