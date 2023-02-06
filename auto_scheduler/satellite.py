from auto_scheduler.tle import parse_tle0


class Satellite:
    """Satellite class"""

    # pylint: disable=too-many-instance-attributes,too-few-public-methods

    def __init__(self, tle, transmitter, success_rate, good_count, data_count, mode):
        """Define a satellite"""
        # pylint: disable=invalid-name,too-many-arguments

        self.tle0 = tle['tle0']
        self.tle1 = tle['tle1']
        self.tle2 = tle['tle2']
        self.id = tle['norad_cat_id']
        self.name = parse_tle0(tle['tle0'])
        self.transmitter = transmitter
        self.success_rate = success_rate
        self.good_count = good_count
        self.data_count = data_count
        self.mode = mode

    def __repr__(self):
        # pylint: disable=consider-using-f-string
        return "%s %s %d %d %d %s %s" % (self.id, self.transmitter, self.success_rate,
                                         self.good_count, self.data_count, self.mode, self.name)
