from __future__ import print_function

import os
import random
import six
from six.moves.urllib import parse

from flask import g, render_template

import utils

DO_BASE = "https://com-leafe-images.nyc3.cdn.digitaloceanspaces.com/galleries"


def index():
    g.gallery_names = utils.get_gallery_names()
    return render_template("gallery_listing.html")


def show_gallery(gallery_name):
    g.gallery_name = gallery_name
    all_photos = utils.get_photos_in_gallery(gallery_name)
    g.photos = {
        six.ensure_text(os.path.join(DO_BASE, parse.quote(ph))): md for ph, md in all_photos.items()
    }
    #    random.shuffle(g.photos)
    return render_template("gallery.html")
