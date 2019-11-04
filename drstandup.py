import datetime
import hashlib
import random

from flask import abort, g, redirect, render_template, request, url_for

team_names = []
with open("cx_team_names.txt") as ff:
    team_names = ff.readlines()


def random_order():
    dtstr = datetime.datetime.utcnow().strftime("%Y%m%d")
    dated_team = [("{}{}".format(dtstr, nm), nm) for nm in team_names]
    hashed_team = [(hashlib.md5(dtnm.encode("UTF-8")).hexdigest(), nm)
            for dtnm, nm in dated_team]
    hashed_team.sort()
    names = "".join(["• {}".format(nm) for _, nm in hashed_team])
    line = "--------------------------------------------\n"
    return "{}{}{}".format(line, names, line)
