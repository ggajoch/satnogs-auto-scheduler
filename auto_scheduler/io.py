import csv
import logging
import os

logger = logging.getLogger(__name__)


def read_transmitters_stats(filename):
    """
    Read transmitter statistics from file

    # Return type
    list(dict)
    """
    transmitters_stats = []
    with open(filename, "r") as fp_transmitters:
        for line in fp_transmitters.readlines():
            item = line.split()
            transmitters_stats.append({
                "norad_cat_id": int(item[0]),
                "uuid": item[1],
                "success_rate": float(item[2]) / 100.0,
                "good_count": int(item[3]),
                "data_count": int(item[4]),
                "mode": item[5]
            })
    return transmitters_stats


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

    if not filename:
        logger.debug('No priority file defined.')
        return ({}, {})

    if not os.path.exists(filename):
        # No priorites file found, return empty objects
        logger.warning('Could not read priority file %s.', filename)
        return ({}, {})

    priorities = {}
    transmitters = {}
    with open(filename, "r") as fp_priorities:
        reader = csv.reader(strip_comments(fp_priorities), delimiter=' ')
        for row in reader:
            if len(row) != 3:
                # Skip malformed lines
                logger.warning(
                    'Malformed line in priority file %s,\n expected 3 parameters but found %d',
                    filename, len(row))
                continue

            norad_id, prio, transmitter = row
            priorities[norad_id] = float(prio)
            transmitters[norad_id] = transmitter
    return (priorities, transmitters)


def read_tles(tles_file):
    """
    Read TLEs from file using 3LE format.

    Deprecated. Serialization using JSON is preferred.
    """
    with open(tles_file, "r") as fp_tles:
        lines = fp_tles.readlines()
        for i in range(0, len(lines), 3):
            tle0 = lines[i]
            tle1 = lines[i + 1]
            tle2 = lines[i + 2]

            if tle1.split(" ")[1] == "":
                norad_cat_id = int(tle1.split(" ")[2][:4])
            else:
                norad_cat_id = int(tle1.split(" ")[1][:5])

            yield {'norad_cat_id': norad_cat_id, 'tle0': tle0, 'tle1': tle1, 'tle2': tle2}
