from auto_scheduler import Satellite


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
            max_good_count = max(s['transmitter']['good_count'] for s in passes
                                 if s['satellite']["id"] == satpass['satellite']["id"])
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
    Extract satellites of interest based on the list of transmitters of interest

    # Arguments
    transmitters (list): List of transmitters of interest
    tles (list): List of TLEs for all satellites

    # Returns
    List of satellites

    # Return type
    list(auto_scheduler.Satelllite)
    '''
    satellites = []
    for transmitter in transmitters:
        for tle in tles:
            if tle['norad_cat_id'] == transmitter['norad_cat_id']:
                satellites.append(Satellite(tle, transmitter))
    return satellites


def search_satellites(transmitters_receivable, transmitters_stats, tles_all, satellites_by_norad_id,
                      skip_frequency_violators):
    '''
    Extract satellites of interest based on the list of transmitters of interest

    NOTE:
    The transmitter mode is truncated. This was done in previous versions of the auto-scheduler
    probably by accident (un-escaped whitespace in a whitespace-seperated text file), for
    backward compatibility now. Can be removed if all code using this object is validated against
    using the full 'mode' text string.

    # Arguments
    transmitters (list): List of transmitters of interest
    tles (list): List of TLEs for all satellites

    # Returns
    List of satellites

    # Return type
    list(auto_scheduler.Satelllite)
    '''
    # pylint: disable=too-many-arguments

    norad_cat_ids_alive = satellites_by_norad_id.keys()

    # Extract NORAD IDs from transmitters
    norad_cat_ids_of_interest = sorted(
        set(transmitter["norad_cat_id"] for transmitter in transmitters_receivable.values()
            if transmitter["norad_cat_id"] in norad_cat_ids_alive))

    # Filter TLEs for objects of interest only
    tles = list(filter(lambda entry: entry['norad_cat_id'] in norad_cat_ids_of_interest, tles_all))

    # Filter transmitters based on ground station capability
    transmitters_of_interest = []

    for uuid, stats in transmitters_stats.items():
        # Skip transmitters which do not have statistics in SatNOGS Network (yet)

        if uuid not in transmitters_receivable:
            continue

        # Skip dead satellites
        if transmitters_receivable[uuid]["norad_cat_id"] not in norad_cat_ids_alive:
            continue

        transmitters_of_interest.append({
            "norad_cat_id":
            transmitters_receivable[uuid]["norad_cat_id"],
            "uuid":
            uuid,
            "success_rate":
            stats["success_rate"] / 100.0,
            "good_count":
            stats["good_count"],
            "data_count":
            stats["total_count"],
            "mode":
            str(transmitters_receivable[uuid]["mode"]).split()[0]
        })

    satellites = []
    for transmitter in transmitters_of_interest:
        for tle in tles:
            if tle['norad_cat_id'] == transmitter['norad_cat_id']:
                satellites.append(Satellite(tle, transmitter))

    # Skip satellites with frequency misuse (avoids scheduling permission errors)
    if skip_frequency_violators:
        satellites = list(
            filter(lambda sat: not satellites_by_norad_id[sat.id]['is_frequency_violator'],
                   satellites))
    return satellites


def print_scheduledpass_summary(scheduledpasses,
                                ground_station_id,
                                satellites_catalog,
                                printer=print):
    printer("  GS | Sch | NORAD | Start time          | End time            | Duration |  El | " +
            "Priority | Transmitter UUID       | Mode       | Freq   | Satellite name")
    printer(f"{' '*128} | misuse | ")

    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        sat_entry = satellites_catalog[int(satpass['satellite']['id'])]

        printer(f"{ground_station_id:4d} | "
                f"{'Y' if satpass['scheduled'] else 'N':3s} | "
                f"{int(satpass['satellite']['id']):05d} | "
                f"{satpass['tr'].strftime('%Y-%m-%dT%H:%M:%S'):s} | "
                f"{satpass['ts'].strftime('%Y-%m-%dT%H:%M:%S'):s} | "
                f"{str(satpass['td']).split('.', maxsplit=1)[0]:s} | "
                f"{float(satpass['altt']) if satpass['altt'] else 0.:3.0f} | "
                f"{satpass.get('priority', 0.0):4.6f} | "
                f"{satpass['transmitter'].get('uuid', ''):s} | "
                f"{satpass['transmitter'].get('mode', ''):<11s} | "
                f"{'Y' if sat_entry['is_frequency_violator'] else 'N':6s} | "
                f"{sat_entry['name']:s}")
