import csv
import logging
import os
import settings

from auto_scheduler import Twolineelement, Satellite


def read_priorities_transmitters(filename):
    # Priorities and favorite transmitters
    # read the following format
    #   43017 1. KgazZMKEa74VnquqXLwAvD
    if not filename or not os.path.exists(filename):
        # No priorites file found, return empty objects
        logging.warning('Could not read priority file {}.'.format(filename))
        return ({}, {})

    satprio = {}
    sattrans = {}
    with open(filename, "r") as fp:
        reader = csv.reader(filter(lambda row: row[0]!='#', fp),
                            delimiter=' ')
        for row in reader:
            if len(row) != 3:
                # Skip malformed lines
                continue
            sat, prio, transmitter = row
            satprio[sat] = float(prio)
            sattrans[sat] = transmitter
    return (satprio, sattrans)


def get_priority_passes(passes, priorities, favorite_transmitters, only_priority, min_priority):
    priority = []
    normal = []
    for satpass in passes:
        # Is this satellite a priority satellite?
        # Is this transmitter a favorite transmitter?
        # Is the priority high enough?
        if satpass['satellite']['id'] in priorities and
           satpass['transmitter']['uuid'] == favorite_transmitters[satpass['satellite']['id']] and
           priorities[satpass['satellite']['id']] >= min_priority:
            satpass['priority'] = priorities[satpass['satellite']['id']]
            satpass['transmitter']['uuid'] = favorite_transmitters[satpass['satellite']['id']]

            priority.append(satpass)
        elif only_priority:
            # Find satellite transmitter with highest number of good observations
            max_good_count = max([s['transmitter']['good_count'] for s in passes if s['satellite']["id"] == satpass['satellite']["id"]])
            if max_good_count > 0:
                satpass['priority'] = \
                    (float(satpass['altt']) / 90.0) \
                    * satpass['transmitter']['success_rate'] \
                    * float(satpass['transmitter']['good_count']) / max_good_count
            else:
                satpass['priority'] = (float(satpass['altt']) / 90.0) * satpass['transmitter']['success_rate']

            # Add if priority is high enough
            if satpass['priority'] >= min_priority:
                normal.append(satpass)
    return (priority, normal)


def satellites_from_transmitters(transmitters, tles):
    '''
    Extract interesting satellites from receivable transmitters
    '''
    satellites = []
    for transmitter in transmitters:
        for tle in tles:
            if tle['norad_cat_id'] == transmitter['norad_cat_id']:
                satellites.append(Satellite(Twolineelement(*tle['lines']),
                                            transmitter['uuid'],
                                            transmitter['success_rate'],
                                            transmitter['good_count'],
                                            transmitter['data_count'],
                                            transmitter['mode']))
    return satellites


def print_scheduledpass_summary(scheduledpasses, ground_station_id, printer=print):
    printer("GS  | Sch | NORAD | Start time          | End time            |  El | " +
                 "Priority | Transmitter UUID       | Mode       | Satellite name ")

    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        printer(
            "%3d | %3.d | %05d | %s | %s | %3.0f | %4.6f | %s | %-10s | %s"%(
             ground_station_id,
             satpass['scheduled'],
             int(satpass['satellite']['id']),
             satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
             satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"),
             float(satpass['altt']) if satpass['altt'] else 0.,
             satpass.get('priority', 0.0),
             satpass['transmitter'].get('uuid', ''),
             satpass['transmitter'].get('mode', ''),
             satpass['satellite']['name'].rstrip()))
