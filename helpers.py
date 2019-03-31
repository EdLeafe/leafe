#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Helper functions

Consists of functions to typically be used within templates, but also
available to Controllers. This module is available to templates as 'h'.
"""
# Import helpers as desired, or define your own, ie:
#from webhelpers.html.tags import checkbox, password

import datetime
import inspect
import logging
import random
import re
from subprocess import Popen, PIPE
from textwrap import TextWrapper


MAIN_CONF = "/etc/postfix/main.cf"
VALID_NAMES = ("leafe_com", "daboserver_com", "sa_home", "iphone", "hotel",
        "roaming")
copyright = u"Copyright ©%s Ed Leafe" % datetime.datetime.now().year


def runproc(cmd):
    proc = Popen([cmd], shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE,
            close_fds=True)
    stdout_text, stderr_text = proc.communicate()
    return stdout_text, stderr_text


def wrapper(txt):
    tw = TextWrapper(width=100)
    out = []
    for ln in txt.splitlines():
        wrapped = tw.wrap(ln)
        if wrapped:
            out.extend(wrapped)
        else:
            out.extend(" ")
    return "\n".join(out)


def maskEmail(val):
    pat = re.compile("([^@]+)@([^@\.]+)\.([^@]+)")
    ats = ("AT", "at", "At", "(AT)", "(at)", "/at/", "/AT/", ".AT.", ".at.")
    atString = random.choice(ats)
    dot1 = "DOT"
    dot = ""
    for ch in dot1:
        if random.randrange(0,2):
            dot += "."
        dot += ch
    return pat.sub("\g<1> " + atString + " \g<2> " + dot + " \g<3>", val)


def _location_line(loc):
    mtch = "%s =" % loc
    cmd = "grep '%s' %s" % (mtch, MAIN_CONF)
    out, err = runproc(cmd)
    return out.strip()


def get_location_addr(loc):
    """Returns the current address for the specified location."""
    # Make sure that the address is valid
    if not loc in VALID_NAMES:
        return "Invalid location: '%s'\n" % loc
    line = _location_line(loc)
    return line.split(" = ")[-1]


def write_conf(txt, log):
    fname = "/tmp/mainconftempfile"
    with open(fname, "w") as tmp:
        tmp.write(txt)
    cmd = "sudo cp %s %s" % (fname, MAIN_CONF)
    out, err = runproc(cmd)
    return err, out


def get_sa_home_ip():
    return get_location_addr("sa_home")


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
