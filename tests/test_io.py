#!/usr/bin/env python3

from auto_scheduler.io import read_priorities_transmitters

a_fixture = ({
    '42759': 1.0,
    '42761': 1.0,
    '40654': 1.0,
    '32789': 1.0,
    '40032': 1.0,
    '40074': 1.0,
    '39432': 1.0,
    '40025': 1.0,
    '40021': 1.0,
    '42017': 1.0,
    '39444': 1.0,
    '40024': 1.0,
    '43786': 1.0,
    '40719': 1.0,
    '43803': 1.0,
    '43792': 1.0,
    '41732': 1.0,
    '40912': 1.0,
    '40911': 1.0,
    '40906': 1.0,
    '40909': 1.0,
    '40910': 1.0,
    '40903': 1.0,
    '43770': 1.0,
    '40967': 1.0,
    '43137': 1.0,
    '43017': 1.0
}, {
    '42759': 'XdKYnxrPbyXKJRtQjrHXu6',
    '42761': 's7WSyh6UFkfkzeW4rro6Ze',
    '40654': 'wnYjL6yjW3wxsVUhqS2duM',
    '32789': 'RGrApAMv8gLbweTgXRhZGa',
    '40032': '6DQp67crsBzih2LWRGFNFM',
    '40074': 'HWdDcVRpjQJCxMbtRkL5em',
    '39432': 'a5kpE63CcUXcGwLN4fY26k',
    '40025': 'qgm5DPSVdJ86YzehiYWQcX',
    '40021': 'LyLQ3K5KTts6gJGQTVuSDP',
    '42017': 'msnC2ijNNoQ2ECKunbpAkm',
    '39444': 'Pt4MFHSC8UFHu3aTQTLz9K',
    '40024': 's8jpdkUffam9RxRArizMQd',
    '43786': 'Mhtbkk6uei97oKEmLkGLBm',
    '40719': 'yzLZeFypEj65qUKis3XrTd',
    '43803': 'ocoEf6MEZtiZgvEWSWsqtY',
    '43792': 'y5GTUBzux5RccNkkSvcsfJ',
    '41732': 'FZJsiKhdoSGUDKMbg7si7f',
    '40912': 'EifSE4XNdP9LyoFNcbcNJo',
    '40911': 'fhM8LwHgZaPL6MjtjLL4MC',
    '40906': 'GKvyYnXuEeNMhviHYHBDh9',
    '40909': 'gz28Jj9NyRm7jMb5UK5Pv5',
    '40910': 'MQpfemiY9Pxga9ehRkmd9R',
    '40903': 'XWkgoTzbierFtJcCBZxPv4',
    '43770': 'bxfwWfvm9UaXRvVfyhcjt6',
    '40967': 'ZyjKNJ9KqnTHBCUzAPN5G5',
    '43137': '3rLGJWqj3XZ6Z8vADCRwiW',
    '43017': 'KgazZMKEa74VnquqXLwAvD'
})


def test_read_priorities_transmitters():
    a = read_priorities_transmitters("tests/prios1.txt")
    assert (a_fixture == a)


def test_read_priorities_transmitters_trailing_newline():
    b = read_priorities_transmitters("tests/prios1_trailing_newline.txt")
    assert (a_fixture == b)
