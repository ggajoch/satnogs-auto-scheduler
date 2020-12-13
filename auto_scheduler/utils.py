from auto_scheduler import Satellite, Twolineelement


def get_priority_passes(passes, priorities, favorite_transmitters, only_priority, min_priority):
    priority = []
    normal = []
    for satpass in passes:
        # Is this satellite a priority satellite?
        # Is this transmitter a favorite transmitter?
        # Is the priority high enough?
        if satpass['satellite']['id'] in priorities and \
           satpass['transmitter']['uuid'] == favorite_transmitters[satpass['satellite']['id']] and \
           priorities[satpass['satellite']['id']] >= min_priority:
            satpass['priority'] = priorities[satpass['satellite']['id']]
            satpass['transmitter']['uuid'] = favorite_transmitters[satpass['satellite']['id']]

            priority.append(satpass)
        elif only_priority:
            # Find satellite transmitter with highest number of good observations
            max_good_count = max([
                s['transmitter']['good_count'] for s in passes
                if s['satellite']["id"] == satpass['satellite']["id"]
            ])
            if max_good_count > 0:
                satpass['priority'] = \
                    (float(satpass['altt']) / 90.0) \
                    * satpass['transmitter']['success_rate'] \
                    * float(satpass['transmitter']['good_count']) / max_good_count
            else:
                satpass['priority'] = (float(satpass['altt']) /
                                       90.0) * satpass['transmitter']['success_rate']

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
                satellites.append(
                    Satellite(Twolineelement(*tle['lines']), transmitter['uuid'],
                              transmitter['success_rate'], transmitter['good_count'],
                              transmitter['data_count'], transmitter['mode']))
    return satellites


def print_scheduledpass_summary(scheduledpasses, ground_station_id, printer=print):
    printer("GS   | Sch | NORAD | Start time          | End time            | Duration |  El | " +
            "Priority | Transmitter UUID       | Mode       | Satellite name ")

    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        printer(
            "%4d | %3s | %05d | %s | %s | %s  | %3.0f | %4.6f | %s | %-10s | %s" %
            (ground_station_id, 'Y' if satpass['scheduled'] else 'N', int(
             satpass['satellite']['id']), satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"),
             satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"), str(satpass['td']).split(".")[0], float(satpass['altt']) if satpass['altt']
             else 0., satpass.get('priority', 0.0), satpass['transmitter'].get('uuid', ''),
             satpass['transmitter'].get('mode', ''), satpass['satellite']['name'].rstrip()))
