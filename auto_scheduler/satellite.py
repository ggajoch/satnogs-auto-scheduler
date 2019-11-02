class satellite:
    """Satellite class"""

    def __init__(self, tle, transmitter, success_rate, good_count, data_count, mode):
        """Define a satellite"""

        self.tle0 = tle.tle0
        self.tle1 = tle.tle1
        self.tle2 = tle.tle2
        self.id = tle.id
        self.name = tle.name.strip()
        self.transmitter = transmitter
        self.success_rate = success_rate
        self.good_count = good_count
        self.data_count = data_count
        self.mode = mode

    def __repr__(self):
        return "%s %s %d %d %d %s %s" % (self.id, self.transmitter, self.success_rate, self.good_count,
                                         self.data_count, self.mode, self.name)
