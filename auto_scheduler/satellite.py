from auto_scheduler.tle import parse_tle0


class Satellite:
    """Satellite class"""

    # pylint: disable=too-many-instance-attributes,too-few-public-methods

    def __init__(self, tle, transmitter):
        """
        Satellite Constructor.

        # Arguments
        tle (list of dict): The TLE of this satellite as provided by SatNOGS DB /api/tles endpoint.
                            Keys: [tle0, tle1, tle2, *tle_source, sat_id, norad_cat_id, *updated]
        transmitter (dict): The transmitter of this satellite
                            Keys: [uuid, success_rate, good_rate, data_count, mode]
        """
        # pylint: disable=invalid-name
        self.tle0 = tle['tle0']
        self.tle1 = tle['tle1']
        self.tle2 = tle['tle2']
        self.id = tle['norad_cat_id']
        self.name = parse_tle0(tle['tle0'])
        self.transmitter = transmitter['uuid']
        self.success_rate = transmitter['success_rate']
        self.good_count = transmitter['good_count']
        self.data_count = transmitter['data_count']
        self.mode = transmitter['mode']

    def __repr__(self):
        # pylint: disable=consider-using-f-string
        return "%s %s %d %d %d %s %s" % (self.id, self.transmitter, self.success_rate,
                                         self.good_count, self.data_count, self.mode, self.name)
