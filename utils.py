import os
import pyrax
import datetime
from functools import wraps, update_wrapper
import logging
import math
import re
from subprocess import Popen, PIPE
import uuid

from flask import make_response
import pymysql
import requests


main_cursor = None
HOST = "dodata"
conn = None

LOG = logging.getLogger(__name__)
BASE_DIR = "/home/ed/projects/leafe"
PHRASE_PAT = re.compile('"([^"]*)"*')

IntegrityError = pymysql.err.IntegrityError


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


def _parse_creds():
    with open("/home/ed/projects/leafe/.dbcreds") as ff:
        lines = ff.read().splitlines()
    ret = {}
    for ln in lines:
        key, val = ln.split("=")
        ret[key] = val
    return ret


def connect():
    cls = pymysql.cursors.DictCursor
    creds = _parse_creds()
    ret = pymysql.connect(host=HOST, user=creds["DB_USERNAME"],
            passwd=creds["DB_PWD"], db=creds["DB_NAME"], charset="utf8",
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


def get_client():
    pyrax.set_setting("identity_type", "rackspace")
    ctx = pyrax.create_context()
    credfile = os.path.join(BASE_DIR, ".raxcreds")
    ctx.set_credential_file(credfile, authenticate=True)
    client = ctx.DFW.object_store.client
    return client


def get_gallery_container():
    clt = get_client()
    return clt.get_container("galleries")


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
#    debug("Phrases:", phrases)
    terms = PHRASE_PAT.split(term_string)
#    debug("Terms:", terms)
    for phrase in phrases:
        terms.remove(phrase)
    words_required = []
    words_forbidden = []
    phrases_required = []
    phrases_forbidden = []
    for phrase in phrases:
        phrase = phrase.strip()
        if phrase.startswith("-"):
#            debug("Forbidden phrase:", phrase)
            phrases_forbidden.append(phrase[1:])
        else:
#            debug("Allowed phrase:", phrase)
            phrases_required.append(phrase)
    for term in terms:
        # A 'term' can consist of multiple words.
        term_words = term.split()
        for term_word in term_words:
            term_word = term_word.strip()
            if term_word.startswith("-"):
#                debug("Forbidden term:", term_word)
                words_forbidden.append(term_word[1:])
            else:
#                debug("Allowed term:", term_word)
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
