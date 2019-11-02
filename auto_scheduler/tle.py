class twolineelement:
    """TLE class"""

    def __init__(self, tle0, tle1, tle2):
        """Define a TLE"""

        self.tle0 = tle0
        self.tle1 = tle1
        self.tle2 = tle2
        if tle0[:2] == "0 ":
            self.name = tle0[2:]
        else:
            self.name = tle0
            if tle1.split(" ")[1] == "":
                self.id = int(tle1.split(" ")[2][:4])
            else:
                self.id = int(tle1.split(" ")[1][:5])
