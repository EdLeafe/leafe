import datetime
import math
import pprint
import re
import string
from textwrap import TextWrapper
import time

import elasticsearch
from flask import abort, Flask, g, render_template, request, session, url_for

import utils


ADMIN_IP = "108.205.7.108"
LINK_PAT = re.compile(r"(https?://[^\s]+)")
PLACEHOLDER_TEXT = "ABCDEF%sZYXWVU"
# Elasticsearch doesn't alllow for accessing more than 10K records, even with
# using offsets. There are ways around it, but really, a search that pulls more
# than 10K is not a very good search.
MAX_RECORDS = 10000
LIMIT_MSG = "Note: Result sets are limited to %s records" % MAX_RECORDS

es_client = elasticsearch.Elasticsearch(host="dodata")
# My original names in the DB suck, so...
DB_TO_ELASTIC_NAMES = {
    "imsg": "msg_num",
    "clist": "list_name",
    "csubject": "subject",
    "cfrom": "from",
    "tposted": "posted",
    "cmessageid": "message_id",
    "creplytoid": "replyto_id",
    "mtext": "body",
    "id": "id",
}
ELASTIC_TO_DB_NAMES = {v: k for k, v in DB_TO_ELASTIC_NAMES.items()}


def db_names_from_elastic(recs):
    return [
        dict((ELASTIC_TO_DB_NAMES.get(k), v) for k, v in rec.items()) for rec in recs
    ]


def _extract_records(resp, translate_to_db=True):
    recs = [r["_source"] for r in resp["hits"]["hits"]]
    excepts = 0
    for rec in recs:
        try:
            rec["posted"] = datetime.datetime.strptime(
                rec["posted"], "%Y-%m-%dT%H:%M:%S"
            )
        except ValueError:
            rec["posted"] = datetime.datetime.strptime(
                rec["posted"], "%Y-%m-%d %H:%M:%S"
            )
            excepts += 1
    if translate_to_db:
        allrecs = [utils.DotDict(rec) for rec in db_names_from_elastic(recs)]
    else:
        allrecs = [utils.DotDict(rec) for rec in recs]
    g.date_excepts = excepts
    return allrecs


def _get_sort_order(order_by):
    return {
        "recent_first": "posted:desc",
        "oldest_first": "posted:asc",
        "author_name": "from:asc",
        "natural": "",
#        "recent_first": {"posted": "desc"},
#        "oldest_first": {"posted": "asc"},
#        "author_name": {"from": "asc"},
#        "natural": "",
    }.get(order_by)


def _proper_listname(val):
    return {
        "profox": "ProFox",
        "prolinux": "ProLinux",
        "propython": "ProPython",
        "valentina": "Valentina",
        "codebook": "Codebook",
        "dabo-dev": "Dabo-Dev",
        "dabo-users": "Dabo-Users",
    }.get(val, "")


def _listAbbreviation(val):
    return {
        "profox": "p",
        "prolinux": "l",
        "propython": "y",
        "valentina": "v",
        "codebook": "c",
        "testing": "t",
        "dabo-dev": "d",
        "dabo-users": "u",
    }.get(val, "")


def _listFromAbbreviation(val):
    return {
        "p": "profox",
        "l": "prolinux",
        "y": "propython",
        "v": "valentina",
        "c": "codebook",
        "t": "testing",
        "d": "dabo-dev",
        "u": "dabo-users",
    }.get(val, "")


def archives_form():
    g.listname = session.get("listname", "")
    return render_template("archives_form.html")


def _format_author(val):
    split_val = val.split("<")[0]
    if not split_val:
        return val
    return split_val.replace('"', "")


def _format_date(val):
    return val.strftime("%Y-%m-%d at %H:%M:%S")


def _format_short_date(val):
    return val.strftime("%Y-%m-%d %H:%M")


def _pager_text():
    thispage = g.page
    pagecount = g.total_pages
    if pagecount == 1:
        return ""

    url = g.url.split("?")[0]
    prevpage = max(1, thispage - 1)
    nextpage = min(thispage + 1, pagecount)
    page_links = []
    for pg in range(pagecount):
        pgnum = pg + 1
        linkstate = "active" if thispage == pgnum else "waves-effect"
        page_links.append(
            f"""<li class={linkstate}><a href={url}?page={pgnum}>{pgnum}</a></li>"""
        )
    page_link_text = "\n        ".join(page_links)

    if thispage == 1:
        prev_text = (
            """<li class="grey-text"><i class="material-icons">chevron_left</i></li>"""
        )
    else:
        prev_text = f"""<li class="waves-effect"><a href="{url}?page={prevpage}"><i class="material-icons">chevron_left</i></a></li>"""
    if thispage == pagecount:
        next_text = (
            """<li class="grey-text"><i class="material-icons">chevron_right</i></li>"""
        )
    else:
        next_text = f"""<li class="waves-effect"><a href="{url}?page={nextpage}"><i class="material-icons">chevron_right</i></a></li>"""

    return f"""      <div class="row">
      <ul class="pagination">
        {prev_text}
        {page_link_text}
        {next_text}
      </ul>
    </div>
    """


def _linkify(txt):
    replacements = []
    set_links = set(LINK_PAT.findall(txt))
    links = list(set_links)
    # Shorter links may be a subset of longer links, so replace longer ones first.
    links.sort(key=len, reverse=True)
    for num, link in enumerate(links):
        # Some links can contain asterisks, which blows up re.
        link = link.replace("*", "[*]")
        try:
            linked = f'<a href="{link}" target="_blank">{link}</a>'
        except Exception:
            # Funky characters; not much you can do.
            continue
        # Replace the original links in the text with placeholders
        txt = txt.replace(link, PLACEHOLDER_TEXT % num)
        replacements.append(linked)
    # OK, now replace the placeholders with the links
    for num, link in enumerate(replacements):
        target = PLACEHOLDER_TEXT % num
        txt = txt.replace(target, replacements[num])
    return txt


def _wrap_text(txt):
    txt = txt.replace("<", "&lt;")
    txt = _linkify(txt)
    ret = []
    for ln in txt.splitlines():
        if ln.startswith(">"):
            ret.append(f'<p style="font-style: italic; color: grey">{ln}</p>')
        else:
            ret.append(f"<p>{ln}</p>")
    return "".join(ret)


def _regexp_casing(txt):
    """Since elasticsearch doesn't support case-insensitive searches, this is a
    brute-force method to accomplish the same thing.
    """

    def case_dupe(s):
        if s in string.ascii_letters:
            return "[" + s.upper() + s.lower() + "]"
        elif s in '.?+*|{}[]()"\\)]}':
            #        if s in '.?+*|{}[]()"\\)]}':
            return f"\\{s}"
        return s

    return "".join([case_dupe(char) for char in txt])


def _get_message(msg_num):
    msg_num = int(msg_num)
    kwargs = {"body": {"query": {"match": {"msg_num": msg_num}}}}
    resp = es_client.search(index="email", **kwargs)
    allrecs = _extract_records(resp, translate_to_db=False)
    if not allrecs:
        abort(404, "No message with id=%s exists" % msg_num)
    return allrecs[0]


def show_full_thread(msg_num):
    g.msg_num = msg_num = int(msg_num)
    g.listname = session.get("listname")
    g.message = _get_message(g.msg_num)
    g.subject = g.message["subject"]
    pat = re.compile(r"^(re: ?)*", re.I)
    clean_subj = pat.sub("", g.subject)
    subj_regexp = "([Rr][Ee]: ?)*" + _regexp_casing(clean_subj)
    kwargs = {
        "body": {
            "query": {"regexp": {"subject": subj_regexp}},
            "sort": {"posted": "asc"},
        }
    }
    resp = es_client.search(index="email", **kwargs)
    allrecs = _extract_records(resp, translate_to_db=False)
    if not allrecs:
        abort(404, "No message with id=%s exists" % msg_num)
    g.messages = allrecs
    func_dict = {
        "fmt_author": _format_author,
        "wrap": _wrap_text,
        "fmt_short_date": _format_short_date,
    }
    return render_template("fullthread.html", **func_dict)


def show_message_by_msgid(msg_id):
    kwargs = {"body": {"query": {"match": {"message_id": msg_id}}}}
    resp = es_client.search(index="email", **kwargs)
    allrecs = _extract_records(resp, translate_to_db=False)
    if not allrecs:
        abort(404, "No message with id=%s exists" % msg_id)
    g.message = allrecs[0]
    g.msg_num = msg_num = g.message.get("msg_num")
    g.subject = g.message.get("subject")
    g.author = _format_author(g.message.get("from"))
    g.copy_year = g.message.get("posted").year
    g.posted = _format_date(g.message.get("posted"))
    g.body = _wrap_text(g.message.get("body"))
    g.session = session
    list_abb = g.message.get("list_name")
    g.listname = session["listname"] = _listFromAbbreviation(list_abb)
    full_results = session.get("full_results", [])
    try:
        pos = full_results.index(msg_num)
        g.prev_msg_num = full_results[pos - 1] if pos > 0 else ""
        g.next_msg_num = full_results[pos + 1] if pos + 1 < len(full_results) else ""
    except ValueError:
        # Not coming from a search
        g.prev_msg_num = g.next_msg_num = ""
    return render_template("message.html")


def show_message(msg_num):
    g.msg_num = msg_num = int(msg_num)
    g.message = _get_message(msg_num)
    g.subject = g.message.get("subject")
    g.author = _format_author(g.message.get("from"))
    g.copy_year = g.message.get("posted").year
    g.posted = _format_date(g.message.get("posted"))
    g.body = _wrap_text(g.message.get("body"))
    g.session = session
    g.listname = session.get("listname")
    full_results = session.get("full_results", [])
    try:
        pos = full_results.index(msg_num)
        g.prev_msg_num = full_results[pos - 1] if pos > 0 else ""
        g.next_msg_num = full_results[pos + 1] if pos + 1 < len(full_results) else ""
    except ValueError:
        # Not coming from a search
        g.prev_msg_num = g.next_msg_num = ""
    return render_template("message.html")


def archives_results_GET():
    g.listname = session["listname"]
    g.elapsed = session["elapsed"]
    g.total_pages = session["total_pages"]
    g.limit_msg = session["limit_msg"]
    g.num_results = session["num_results"]
    g.full_results = session["full_results"]
    g.batch_size = session["batch_size"]
    g.page = int(request.args["page"])
    g.url = request.url
    g.remote_addr = request.remote_addr
    g.kwargs = session["kwargs"]
    g.offset = (g.page - 1) * g.batch_size
    # Make sure we don't exceed elasticsearch's limits
    g.kwargs["from_"] = min(g.offset, MAX_RECORDS - g.batch_size)
    resp = es_client.search(index="email", **g.kwargs)
    g.results = _extract_records(resp, translate_to_db=False)
    g.pager_text = _pager_text()
    g.session = session
    func_dict = {
        "enumerate": enumerate,
        "fmt_author": _format_author,
        "fmt_date": _format_date,
    }
    return render_template("archive_results.html", **func_dict)


def archives_results_POST():
    # Clear any old session data
    for key in (
        "listname",
        "elapsed",
        "total_pages",
        "limit_msg",
        "num_results",
        "full_results",
        "batch_size",
        "kwargs",
    ):
        session.pop(key, None)
    g.listname = session["listname"] = request.form.get("listname")
    body_terms = request.form.get("body_terms")
    subject = request.form.get("subject_phrase")
    author = request.form.get("author")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    # We want to include items on the end date, so extend the search to the
    # following date.
    end_date_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(
        days=1
    )
    end_date_plus = end_date_dt.strftime("%Y-%m-%d")
    sort_order = _get_sort_order(request.form.get("sort_order"))
    include_OT = bool(request.form.get("chk_OT"))
    include_NF = bool(request.form.get("chk_NF"))
    batch_size = int(request.form.get("batch_size"))

    kwargs = utils.search_term_query(body_terms, "body", start_date, end_date_plus)
    bqbm = kwargs["body"]["query"]["bool"]["must"]
    neg_bqbm = kwargs["body"]["query"]["bool"]["must_not"]

    listabb = _listAbbreviation(g.listname)
    if listabb:
        utils.add_match(bqbm, "list_name", listabb)
    if subject:
        utils.add_match_phrase(bqbm, "fulltext_subject", subject)
    if author:
        expr = "*%s*" % author
        bqbm.append({"wildcard": {"from": expr}})
    if listabb == "p":
        if not include_OT:
            utils.add_match(neg_bqbm, "subject", "[OT]")
        if not include_NF:
            utils.add_match(neg_bqbm, "subject", "[NF]")
    if sort_order:
        kwargs["sort"] = [sort_order]

    if not bqbm:
        del kwargs["body"]["query"]["bool"]["must"]
    if not neg_bqbm:
        del kwargs["body"]["query"]["bool"]["must_not"]
    session["query_body"] = kwargs["body"]

    # Get the total number of hits. This will return the total without
    # pulling all the data.
    kwargs["size"] = 10000
    kwargs["_source"] = ["msg_num"]
    startTime = time.time()

    utils.debugout("KWARGS", kwargs)
    resp = es_client.search(index="email", **kwargs)
    utils.debugout("RESP", resp)
    session["elapsed"] = g.elapsed = "%.4f" % (time.time() - startTime)
    g.full_results = [r["_source"]["msg_num"] for r in resp["hits"]["hits"]]
    session["full_results"] = g.full_results
    session["num_results"] = g.num_results = resp["hits"]["total"]["value"]
    g.limit_msg = "" if g.num_results <= MAX_RECORDS else LIMIT_MSG
    session["limit_msg"] = g.limit_msg

    # Now run the query for real
    kwargs.pop("_source")
    kwargs["size"] = batch_size
    g.offset = int(request.form.get("page", "0")) * batch_size
    # Make sure we don't exceed elasticsearch's limits
    kwargs["from_"] = min(g.offset, MAX_RECORDS - batch_size)

    session["batch_size"] = batch_size
    session["kwargs"] = g.kwargs = kwargs
    g.kwargs = f"<pre>{pprint.pformat(kwargs)}</pre"
    resp = es_client.search(index="email", **kwargs)
    total = "{:,}".format(resp["hits"]["total"]["value"])
    g.results = _extract_records(resp, translate_to_db=False)
    g.session = session

    # Set up environment vals
    g.url = request.url
    g.remote_addr = request.remote_addr
    g.from_admin = request.remote_addr == ADMIN_IP

    page = int(request.form.get("page", "1"))
    calc_pages = int(math.ceil(float(g.num_results) / batch_size))
    max_pages = int(MAX_RECORDS / batch_size)
    session["total_pages"] = g.total_pages = min(calc_pages, max_pages)
    page = min(page, g.total_pages)

    g.page = page
    g.pager_text = _pager_text()
    func_dict = {
        "enumerate": enumerate,
        "fmt_author": _format_author,
        "fmt_date": _format_date,
    }
    return render_template("archive_results.html", **func_dict)


# BATCH_SIZE = 250
# MAX_PAGES = int(MAX_RECORDS / BATCH_SIZE)
