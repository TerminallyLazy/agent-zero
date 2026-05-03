import os
import re
import pytest
from usr.plugins.dj_booth.helpers.icecast import (
    IcecastManager, render_icecast_xml,
)


def test_render_xml_substitutes_all_fields():
    cfg = {
        "icecast_port": 8000,
        "icecast_admin_password": "adminpw",
        "icecast_source_password": "sourcepw",
        "stream_name": "TestRadio",
        "stream_description": "desc",
        "stream_genre": "Test",
        "stream_url": "http://localhost:8000",
        "mount": "/stream",
        "max_listeners": 50,
        "public_listing": False,
    }
    xml = render_icecast_xml(cfg)
    assert "<port>8000</port>" in xml
    assert "<source-password>sourcepw</source-password>" in xml
    assert "<admin-password>adminpw</admin-password>" in xml
    assert "<mount-name>/stream</mount-name>" in xml
    assert "<max-listeners>50</max-listeners>" in xml
    assert "<public>0</public>" in xml
    assert "/tmp/dj_booth_logs" in xml
    assert "/tmp/dj_booth_icecast.pid" in xml


def test_render_xml_public_listing_true():
    cfg = {"icecast_port": 8000, "icecast_admin_password": "a",
           "icecast_source_password": "s", "stream_name": "n",
           "stream_description": "d", "stream_genre": "g",
           "stream_url": "u", "mount": "/m", "max_listeners": 1,
           "public_listing": True}
    xml = render_icecast_xml(cfg)
    assert "<public>1</public>" in xml


def test_parse_listener_count_from_status_json():
    sample = '{"icestats":{"source":{"listenurl":"http://localhost:8000/stream","listeners":7}}}'
    assert IcecastManager.parse_listener_count(sample, "/stream") == 7


def test_parse_listener_count_multi_mount():
    sample = '''{"icestats":{"source":[
        {"listenurl":"http://x/stream","listeners":3},
        {"listenurl":"http://x/other","listeners":99}
    ]}}'''
    assert IcecastManager.parse_listener_count(sample, "/stream") == 3


def test_parse_listener_count_no_source():
    assert IcecastManager.parse_listener_count('{"icestats":{}}', "/stream") == 0


def test_parse_listener_count_malformed():
    assert IcecastManager.parse_listener_count("not json", "/stream") == 0


def test_get_singleton():
    m1 = IcecastManager.get()
    m2 = IcecastManager.get()
    assert m1 is m2
