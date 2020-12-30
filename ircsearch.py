import cgi
import copy
import datetime as dt
import hashlib
import random
import re
import time

from elasticsearch import Elasticsearch
from flask import abort, g, render_template, request, session

import utils
from utils import logit


START_DATE = "2016-01-01"
END_DATE = "2020-12-31"
INDEX = "irclog"
HOST = "dodata"
PER_PAGE = 100
LINK_PAT = re.compile(r"(.*)\b(https?://\S+)(.*)", re.I)
COLORS = (
    "#407a40",
    "#42427e",
    "#488888",
    "#4b904b",
    "#4d4d93",
    "#539e9e",
    "#57a657",
    "#5959a9",
    "#5fb4b4",
    "#62bb62",
    "#6464bf",
    "#6acaca",
    "#6ed16e",
    "#7070d5",
    "#76e0e0",
    "#818144",
    "#854685",
    "#8c4a4a",
    "#97974f",
    "#9b519b",
    "#a25555",
    "#a9a942",
    "#ad5b5b",
    "#adad5b",
    "#b15db1",
    "#b86161",
    "#c3c366",
    "#c668c6",
    "#ce6c6c",
    "#dc74dc",
)
es_client = Elasticsearch(host=HOST)


def _make_username():
    now = dt.datetime.now().strftime("%T.%f").encode("utf8")
    return hashlib.md5(now).hexdigest()


def _get_channels():
    logit("CHANNELS", {"aggs": {"channels": {"terms": {"field": "channel", "size": 1000}}}})
    resp = es_client.search(
        index=INDEX,
        body={"aggs": {"channels": {"terms": {"field": "channel.keyword", "size": 1000}}}},
        size=0,
    )
    clist = resp.get("aggregations").get("channels").get("buckets")
    retlist = [cl["key"] for cl in clist]
    retlist.sort()
    return retlist


def _get_sort_order(order_by):
    sorttext = {"recent_first": "posted:desc", "oldest_first": "posted:asc"}.get(
        order_by
    )
    return [sorttext]


def show_search_form():
    g.channels = _get_channels()
    logit("Got channels")
    g.startdate = START_DATE
    g.enddate = END_DATE
    return render_template("irc_search_form.html")


def make_clickable(p):
    mtch = LINK_PAT.match(p)
    if not mtch:
        if "<span " in p or "<b>" in p:
            return p
        return cgi.escape(p)
    pre, uri, post = mtch.groups()
    if "<span " in uri:
        # Hilited text, don't make a link
        return p
    link = '<a href="%s" target="_new">%s</a>' % (uri, uri)
    return "".join((pre, link, post))


def POST_search_results():
    form = request.form
    sel_channel = form.get("channel")
    sort_order = form.get("sort_order")
    search_terms = form.get("msg_text")
    search_nick = form.get("nick")
    if not (search_terms or search_nick):
        abort(400, "You must supply search terms and/or a nick")
    start_date = form.get("start_date")
    end_date = form.get("end_date")

    kwargs = utils.search_term_query(search_terms, "remark", start_date, end_date)
    bqbm = kwargs["body"]["query"]["bool"]["must"]
    neg_bqbm = kwargs["body"]["query"]["bool"]["must_not"]
    bqbf = kwargs["body"]["query"]["bool"]["filter"]

    if sel_channel:
        bqbf.append({"term": {"channel.keyword": sel_channel}})
    if search_nick:
        bqbf.append({"term": {"nick": search_nick}})
    if sort_order:
        kwargs["sort"] = _get_sort_order(sort_order)
    kwargs["size"] = 10000

    startTime = time.time()
    logit("POST SEARCH KW", kwargs)
    print("POST SEARCH KW", kwargs)
    resp = es_client.search(index=INDEX, **kwargs)
    g.elapsed = "%.4f" % (time.time() - startTime)
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
    g.results = [hit["_source"] for hit in hits]
    g.num_results = len(g.results)
    g.kwargs = kwargs
    return render_template("irc_search_results.html", make_clickable=make_clickable)


def earlier(channel, end, size):
    return chan_range(channel, "lt", end, size, "desc")


def later(channel, start, size):
    return chan_range(channel, "gte", start, size, "asc")


def chan_range(chan, op, tm, size, ordr):
    return {
        "body": {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"channel.keyword": chan}},
                        {"range": {"posted": {op: tm}}}
                    ]
                }
            }
        },
        "size": size,
        "sort": ["posted:{}".format(ordr)],
    }


def _pick_color():
    return random.choice(COLORS)


def show_timeline(channel, start, end, middle=False):
    """If 'middle' is True, we need to do 2 queries, with half of the results
    earlier than the 'start', and the other half later.
    """
    if middle:
        before = earlier(channel, start, 10)
        logit("BEFORE", before)
        resp = es_client.search(index=INDEX, **before)
        hits_before = resp["hits"]["hits"]
        hits_before.reverse()
        after = later(channel, start, PER_PAGE - 10)
        logit("AFTER", after)
        resp = es_client.search(index=INDEX, **after)
        hits_after = resp["hits"]["hits"]
        hits = hits_before + hits_after
        g.rows = [hit["_source"] for hit in hits]
        g.hilite_time = start
    else:
        if end:
            adjective = "earlier"
            kwargs = earlier(channel, end, PER_PAGE)
        else:
            adjective = "later"
            kwargs = later(channel, start, PER_PAGE)
        logit("TIMELINE", kwargs)
        resp = es_client.search(index=INDEX, **kwargs)
        hits = resp["hits"]["hits"]
        if not hits:
            abort(404, "There are no %s messages" % adjective)
        if end:
            hits.reverse()
        g.rows = [hit["_source"] for hit in hits]
        g.hilite_time = ""
    sess_map = session.get("color_map", {})
    g.color_map = {}
    for row in g.rows:
        nick = row["nick"]
        if nick in g.color_map:
            continue
        g.color_map[nick] = sess_map.get(nick) or _pick_color()
    session["color_map"] = g.color_map
    logit("ROWS", g.rows)
    return render_template("irc_timeline.html", make_clickable=make_clickable)
