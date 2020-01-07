from decouple import config

# Basic settings
DB_BASE_URL = config('DB_BASE_URL', default='https://db.satnogs.org')
NETWORK_BASE_URL = config('NETWORK_BASE_URL', default='https://network.satnogs.org')
CACHE_DIR = config('CACHE_DIR', default='/tmp/cache')
CACHE_AGE = config('CACHE_AGE', default=24, cast=float)  # In hours
MAX_NORAD_CAT_ID = config('MAX_NORAD_CAT_ID', default=90000, cast=int)
MIN_PASS_DURATION = config('MIN_PASS_DURATION', default=3, cast=float)  # In minutes

# Credentials
SATNOGS_API_TOKEN = config('SATNOGS_API_TOKEN', default='')
