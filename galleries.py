from __future__ import print_function

import os
import random
import six
from six.moves.urllib import parse

from flask import g, render_template
import pyrax

import utils

BASE_URI = "//67bc544c4d4c52d03a29-d7000c07746d5de17226f99a444d9940.ssl.cf1.rackcdn.com"
DOBASE = "https://com-leafe-images.nyc3.cdn.digitaloceanspaces.com/galleries"


def index():
    cont = utils.get_gallery_container()
    g.gallery_names = [c.name.rstrip("/") for c in cont.list_subdirs()]
    return render_template("gallery_listing.html")


def show_gallery(gallery_name):
    cont = utils.get_gallery_container()
    g.gallery_name = gallery_name
    all_photos = cont.list_object_names(prefix=gallery_name)
    g.photos = [six.text_type(os.path.join(BASE_URI, parse.quote(ph)))
            for ph in all_photos
            if ph != gallery_name]
    random.shuffle(g.photos)
    return render_template("gallery.html")


def debug_gallery(gallery_name):
    import pudb
    pudb.set_trace()
    cont = utils.get_gallery_container()
    all_photos = cont.list_object_names(prefix=gallery_name)
    photos = [six.text_type(os.path.join(BASE_URI, parse.quote(ph)))
            for ph in all_photos
            if ph != gallery_name]
    random.shuffle(photos)
    return ""