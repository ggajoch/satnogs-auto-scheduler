import csv
import logging
import os

logger = logging.getLogger(__name__)


def read_transmitters(transmitters_file):
    with open(transmitters_file, "r") as f:
        for line in f.readlines():
            item = line.split()
            yield {
                "norad_cat_id": int(item[0]),
                "uuid": item[1],
                "success_rate": float(item[2]) / 100.0,
                "good_count": int(item[3]),
                "data_count": int(item[4]),
                "mode": item[5]
            }


def strip_comments(csv_file):
    # source: https://stackoverflow.com/a/50592259
    for row in csv_file:
        raw = row.split('#')[0].strip()
        if raw:
            yield raw


def read_priorities_transmitters(filename):
    # Priorities and favorite transmitters
    # read the following format
    #   43017 1. KgazZMKEa74VnquqXLwAvD

    if not filename or not os.path.exists(filename):
        # No priorites file found, return empty objects
        logger.warning('Could not read priority file %s.', filename)
        return ({}, {})

    satprio = {}
    sattrans = {}
    with open(filename, "r") as fp:
        reader = csv.reader(strip_comments(fp), delimiter=' ')
        for row in reader:
            if len(row) != 3:
                # Skip malformed lines
                logger.warning('Malformed line, expected 3 parameters but found %d' % len(row))
                continue

            sat, prio, transmitter = row
            satprio[sat] = float(prio)
            sattrans[sat] = transmitter
    return (satprio, sattrans)
