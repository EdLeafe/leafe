from __future__ import print_function

from io import BytesIO
import os
from pathlib import Path
import random
import urllib.parse as parse
from urllib.request import urlopen

from flask import g, render_template
from PIL import Image

import utils


DO_BASE = "https://com-leafe-images.nyc3.cdn.digitaloceanspaces.com/galleries"
THUMB_DIMENSION = 150
THUMB_DIRECTORY = Path("static/thumbs")


def dict_shuffle(dct):
    keys = list(dct.keys())
    random.shuffle(keys)
    return {k: dct[k] for k in keys}


def index():
    g.gallery_names = utils.get_gallery_names()
    return render_template("gallery_listing.html")


def _get_thumb(url):
    """Given a URL to a remote image, get the corresponding thumbnail from the `static/thumbs` directory.

    If no such thumbnail exists, generate it as save in the thumbs directory for future requests.
    """
    split_path = url.split("/galleries/")
    thumb_path = THUMB_DIRECTORY / split_path[-1]
    if not thumb_path.exists():
        print("GENTHUMB", thumb_path.as_posix())
        im = Image.open(BytesIO(urlopen(url).read()))
        im.thumbnail((THUMB_DIMENSION, THUMB_DIMENSION))
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        with thumb_path.open("wb") as ff:
            im.save(ff)

    # We need to remove the initial 'static' directory, as Flask will add it
    return thumb_path.as_posix().split('static/')[-1]



def show_gallery(gallery_name):
    def _safe_decode(s):
        try:
            return s.decode()
        except AttributeError:
            return s

    g.gallery_name = gallery_name
    all_photos = utils.get_photos_in_gallery(gallery_name)
    g.photos = {
        _safe_decode(os.path.join(DO_BASE, parse.quote(ph))): obj["Metadata"] for ph, obj in all_photos.items()
    }
    dict_shuffle(g.photos)
    func_dict = {
        "get_thumb": _get_thumb,
    }
    return render_template("gallery.html", **func_dict)
