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
        """
        Return the string representation of this satellite.

        Valid Python expression that could be used to recreate the object.
        """
        return f'auto_scheduler.Satellite(' \
            'tle={' \
            f'"tle0": "{self.tle0.strip()}",' \
            f'"tle1": "{self.tle1.strip()}",' \
            f'"tle2": "{self.tle2.strip()}",' \
            f'"norad_cat_id": "{self.id}"' \
            '}, transmitter={' \
            f'"uuid": "{self.transmitter}",' \
            f'"success_rate": "{self.success_rate}",' \
            f'"good_count": "{self.good_count}",' \
            f'"data_count": "{self.data_count}",' \
            f'"mode": "{self.mode}"' \
            '})'

    def __eq__(self, other):
        """
        Check if two Satellites are equal.
        """
        for attribute_name in [
                'tle0', 'tle1', 'tle2', 'id', 'name', 'transmitter', 'success_rate', 'good_count',
                'data_count', 'mode'
        ]:
            if not self.__getattribute__(attribute_name) == other.__getattribute__(attribute_name):
                return False
        return True
