def parse_tle0(tle0):
    """
    Parse the tle0 line. This line only contains the
    satellite name, but sometimes it is prefixed with '0 '.

    Returns:
    name of the satellite
    """
    if tle0[:2] == "0 ":
        return tle0[2:].strip()
    return tle0.strip()
