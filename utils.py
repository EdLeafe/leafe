import datetime
from functools import wraps, update_wrapper
import logging
import math
import os
import random
import re
from subprocess import Popen, PIPE
import time
import uuid

import boto
from flask import make_response
import pymysql
from pymysql.err import InternalError as PymysqlInternalError
import requests


main_cursor = None
HOST = "dodata"
conn = None

LOG = logging.getLogger(__name__)
BASE_DIR = "/home/ed/projects/leafe"
LOGIT_FILE = os.path.join(BASE_DIR, "LOGOUT")
PHRASE_PAT = re.compile('"([^"]*)"*')

IntegrityError = pymysql.err.IntegrityError


def logit(*msgs):
    tm = datetime.datetime.utcnow().replace(microsecond=0)
    tmstr = time.strftime("%Y-%m-%dT%H:%M:%S")
    msg_str = " ".join(["%s" % m for m in msgs])
    msg = tmstr + " " + msg_str
    with open(LOGIT_FILE, "a") as ff:
        ff.write("{}\n".format(msg))


class DotDict(dict):
    """
    Dictionary subclass that allows accessing keys via dot notation.

    If the key is not present, an AttributeError is raised.
    """
    _att_mapper = {}
    _fail = object()

    def __init__(self, *args, **kwargs):
        super(DotDict, self).__init__(*args, **kwargs)

    def __getattr__(self, att):
        att = self._att_mapper.get(att, att)
        ret = self.get(att, self._fail)
        if ret is self._fail:
            raise AttributeError("'%s' object has no attribute '%s'" %
                    (self.__class__.__name__, att))
        return ret

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def runproc(cmd):
    proc = Popen([cmd], shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE,
            close_fds=True)
    stdout_text, stderr_text = proc.communicate()
    return stdout_text, stderr_text


def parse_creds():
    with open("/home/ed/projects/leafe/.dbcreds") as ff:
        lines = ff.read().splitlines()
    ret = {}
    for ln in lines:
        key, val = ln.split("=")
        ret[key] = val
    return DotDict(ret)


def connect(creds=None):
    cls = pymysql.cursors.DictCursor
    # If credentials aren't supplied, use the ones in .dbcreds
    creds = creds or parse_creds()
    ret = pymysql.connect(host=creds.get("host") or HOST, user=creds["username"],
            passwd=creds["password"], db=creds["dbname"], charset="utf8",
            cursorclass=cls)
    return ret


def gen_uuid():
    return str(uuid.uuid4())


def get_cursor():
    global conn, main_cursor
    if not (conn and conn.open):
        LOG.debug("No DB connection")
        main_cursor = None
        conn = connect()
    conn.ping(reconnect=True)
    if not main_cursor:
        LOG.debug("No cursor")
        main_cursor = conn.cursor(pymysql.cursors.DictCursor)
    return main_cursor


def commit():
    conn.commit()


def debugout(*args):
    with open("/tmp/debugout", "a") as ff:
        ff.write("YO!")
    argtxt = [str(arg) for arg in args]
    msg = "  ".join(argtxt) + "\n"
    with open("/tmp/debugout", "a") as ff:
        ff.write(msg)


def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Last-Modified"] = datetime.datetime.now()
        response.headers["Cache-Control"] = "no-store, no-cache, " \
                "must-revalidate, post-check=0, pre-check=0, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response
        
    return update_wrapper(no_cache, view)


def human_fmt(num):
    """Human friendly file size"""
    # Make sure that we get a valid input. If an invalid value is passed, we
    # want the exception to be raised.
    num = int(num)
    units = list(zip(["bytes", "K", "MB", "GB", "TB", "PB"],
            [0, 0, 1, 2, 2, 2]))
    if num > 1:
        exponent = min(int(math.log(num, 1024)), len(units) - 1)
        quotient = float(num) / 1024**exponent
        unit, num_decimals = units[exponent]
        format_string = "{:.%sf} {}" % (num_decimals)
        return format_string.format(quotient, unit)
    if num == 0:
        return "0 bytes"
    if num == 1:
        return "1 byte"


def _user_creds():
    with open("/home/ed/docreds.rc") as ff:
        creds = ff.read()
    user_creds = {}
    for ln in creds.splitlines():
        if ln.startswith("spacekey"):
            user_creds["spacekey"] = ln.split("=")[-1].strip()
        elif ln.startswith("secret"):
            user_creds["secret"] = ln.split("=")[-1].strip()
        elif ln.startswith("bucket"):
            user_creds["bucket"] = ln.split("=")[-1].strip()
    return user_creds


def get_client():
    user_creds = _user_creds()
    conn = boto.connect_s3(aws_access_key_id=user_creds["spacekey"],
            aws_secret_access_key=user_creds["secret"],
            host="nyc3.digitaloceanspaces.com")
    bucket = conn.get_bucket(user_creds["bucket"])
    return bucket


def upload_to_DO(fpath, folder=None, public=False):
    """Uploads the specified file to the default DigitalOcean space. If a
    folder is specified, that will be used as a prefix for the remote file.
    Example:
    
        fpath = "/home/ed/photos/test_image.jpg"
        folder = None
        -> will create the key 'test_image.jpg'

        fpath = "/home/ed/photos/test_image.jpg"
        folder = "Family Photos/June"
        -> will create the key 'Family Photos/June/test_image.jpg'

    If the parameter 'public' is True, the remote file will be made publicly available.
    """
    folder = folder or ""
    fname = os.path.basename(fpath)
    remote_path = os.path.join(folder, fname)
    clt = get_client()
    remote_file = clt.new_key(remote_path)
    with open(fpath, "rb") as file_to_upload:
        remote_file.set_contents_from_file(file_to_upload)
    if public:
        remote_file.make_public()


def get_gallery_names():
    clt = get_client()
    prefix = "galleries/"
    all_names = clt.list(prefix=prefix, delimiter="/")
    full_names = (itm.name for itm in all_names)
    names = (itm.split(prefix)[-1] for itm in full_names)
    cleaned = [itm.rstrip("/") for itm in names if itm]
    return cleaned


def get_photos_in_gallery(gallery_name):
    clt = get_client()
    prefix = "galleries/{}/".format(gallery_name)
    all_photos = clt.list(prefix=prefix)
    photos_with_meta = {itm.name.split("galleries/")[-1]: clt.get_key(itm).metadata for itm in
            all_photos}
    photo_keys = list(photos_with_meta.keys())
    random.shuffle(photo_keys)
    shuffled_photos = {pk: photos_with_meta.get(pk) for pk in photo_keys if not pk.endswith("/")}
    return shuffled_photos


def download(remote_url, folder, fname):
    """Download the file at the remote address, and write it to the specified
    folder
    """
    dl = requests.get(remote_url, allow_redirects=True)
    location = os.path.join(folder, fname)
    with open(location, "wb") as ff:
        ff.write(dl.content)


def _parse_search_terms(term_string):
    phrases = PHRASE_PAT.findall(term_string)
#    logit("Phrases:", phrases)
    terms = PHRASE_PAT.split(term_string)
#    logit("Terms:", terms)
    for phrase in phrases:
        terms.remove(phrase)
    words_required = []
    words_forbidden = []
    phrases_required = []
    phrases_forbidden = []
    for phrase in phrases:
        phrase = phrase.strip()
        if phrase.startswith("-"):
#            logit("Forbidden phrase:", phrase)
            phrases_forbidden.append(phrase[1:])
        else:
#            logit("Allowed phrase:", phrase)
            phrases_required.append(phrase)
    for term in terms:
        # A 'term' can consist of multiple words.
        term_words = term.split()
        for term_word in term_words:
            term_word = term_word.strip()
            if term_word.startswith("-"):
#                logit("Forbidden term:", term_word)
                words_forbidden.append(term_word[1:])
            else:
#                logit("Allowed term:", term_word)
                words_required.append(term_word)
    # We have the values in lists, but we need simple strings
    return (" ".join(words_required), " ".join(words_forbidden),
            " ".join(phrases_required), " ".join(phrases_forbidden))


def add_match(lst, key, val, operator=None):
    if operator:
        lst.append({"match": {key: {"query": val, "operator": operator}}})
    else:
        lst.append({"match": {key: val}})


def add_match_phrase(lst, key, val):
    lst.append({"match_phrase": {key: val}})


def search_term_query(search_text, search_field, start_date, end_date):
    kwargs = {"body": {"query": {
            "bool": {
                "filter": [],
                "must": [],
                "must_not": [],
            }}}}
    bqbm = kwargs["body"]["query"]["bool"]["must"]
    neg_bqbm = kwargs["body"]["query"]["bool"]["must_not"]
    bqbf = kwargs["body"]["query"]["bool"]["filter"]

    (words_required, words_forbidden, phrases_required,
            phrases_forbidden) = _parse_search_terms(search_text)
    if words_required:
        add_match(bqbm, search_field, words_required, operator="and")
    if words_forbidden:
        add_match(neg_bqbm, search_field, words_forbidden, operator="and")
    if phrases_required:
        add_match_phrase(bqbm, search_field, phrases_required)
    if phrases_forbidden:
        add_match_phrase(neg_bqbm, search_field, phrases_forbidden)
    bqbf.append({"range": {"posted": {"gte": start_date, "lt": end_date}}})

    return kwargs
