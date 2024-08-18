import copy
import datetime as dt
import hashlib

from elasticsearch7 import Elasticsearch
from flask import Flask, abort, g, redirect, render_template, request, session
from flask import url_for, make_response, render_template

import dbutil

INDEX = "irclog"
HOST = "159.203.122.132"
es_client = Elasticsearch(host=HOST)


def show(channel, start):
    return "Received: %s @ %s" % (channel, start)


def _make_username():
    now = dt.datetime.now().strftime("%T.%f").encode("utf8")
    return hashlib.md5(now).hexdigest()


def _get_channels():
    resp = es_client.search("irclog", body={"aggs": {"channels": {"terms": {"field": "channel"}}}})
    clist = resp.get("aggregations").get("channels").get("buckets")
    return [cl["key"] for cl in clist]


def show_search_form():
    g.channels = _get_channels()
    return render_template("search_form.html")


def POST_search_results():
    form = request.form
    sel_channel = form.get("select_channel")
    user_data = session.get("user", {})
    if user_data:
        username = user_data["username"]
        data = dbutil.get_user_data(username)
        if data:
            user_data.update(data)
    else:
        username = _make_username()
        session["user"] = username
        user_data = {"username": username}

    sort_order = form.get("sort_order")
    search_terms = form.get("search_terms")
    if not search_terms:
        abort(400, "You must supply search terms")
    exact = bool(form.get("phrase"))
    match_type = "match_phrase" if exact else "match"

    if sel_channel == "_all":
        body = {"query": {match_type: {"remark": search_terms}}}
    else:
        body = {
            "query": {
                "bool": {
                    "must": [{match_type: {"remark": search_terms}}],
                    "filter": [{"term": {"channel": sel_channel}}],
                }
            }
        }

    kwargs = {"body": body, "size": 10000, "sort": ["posted:%s" % sort_order]}

    resp = es_client.search(INDEX, **kwargs)
    hits = resp["hits"]["hits"]

    def hilite(s):
        """Hilite the search terms in the remark"""
        if isinstance(search_terms, (list, tuple)):
            terms = search_terms
        else:
            terms = [search_terms]
        for term in terms:
            s = s.replace(term, "<span class=hilite>%s</span>" % term)
        return s

    g.hilite = hilite
    g.rows = [hit["_source"] for hit in hits]
    g.offset = user_data.get("offset", 0)

    dbutil.store_data(username, user_data)
    session["user"] = copy.deepcopy(user_data)
    return render_template("search_results.html")
