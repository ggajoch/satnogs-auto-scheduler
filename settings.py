from decouple import config

# Basic settings
DB_BASE_URL = config('DB_BASE_URL', default='https://db.satnogs.org')
NETWORK_BASE_URL = config('NETWORK_BASE_URL', default='https://network.satnogs.org')
CACHE_AGE = config('CACHE_AGE', default=24)
MAX_NORAD_CAT_ID = config('CACHE_AGE', default=90000)

# Credentials
NETWORK_USERNAME = config('NETWORK_USERNAME', default='')
NETWORK_PASSWORD = config('NETWORK_PASSWORD', default='')
