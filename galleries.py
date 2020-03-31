from __future__ import print_function

import os
import random
import six
from six.moves.urllib import parse

from flask import g, render_template

import utils

BASE_URI = "//67bc544c4d4c52d03a29-d7000c07746d5de17226f99a444d9940.ssl.cf1.rackcdn.com"
DOBASE = "https://com-leafe-images.nyc3.cdn.digitaloceanspaces.com/galleries"


def index():
    g.gallery_names = utils.get_gallery_names()
    return render_template("gallery_listing.html")


def show_gallery(gallery_name):
    g.gallery_name = gallery_name
    all_photos = utils.get_photos_in_gallery(gallery_name)
    g.photos = [six.ensure_text(os.path.join(DOBASE, parse.quote(ph)))
            for ph in all_photos]
    random.shuffle(g.photos)
    return render_template("gallery.html")


#def debug_gallery(gallery_name):
#    import pudb
#    pudb.set_trace()
#    cont = utils.get_gallery_container()
#    all_photos = cont.list_object_names(prefix=gallery_name)
#    photos = [six.text_type(os.path.join(DOBASE, parse.quote(ph)))
#            for ph in all_photos
#            if ph != gallery_name]
#    random.shuffle(photos)
#    return ""
#
#
#def download_photos():
#    """Script to download the gallery photos from Rackspace Cloud."""
#    base_folder = "/home/ed/dls/photos"
#    cont = utils.get_gallery_container()
#    gallery_names = [c.name.rstrip("/") for c in cont.list_subdirs()]
#    all_photos = cont.list_object_names()
#    for ph in all_photos:
#        if ph in gallery_names:
#            continue
#        remote_path = six.ensure_text(os.path.join(BASE_URI, parse.quote(ph)))
#        url = "https:{}".format(remote_path)
#        subfolder, fname = ph.split("/")
#        target_folder = os.path.join(base_folder, subfolder)
#        os.makedirs(target_folder, exist_ok=True)
#        print("Downloading {}...".format(fname))
#        utils.download(url, target_folder, fname)
