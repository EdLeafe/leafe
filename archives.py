import datetime
import math
import re
import string
from textwrap import TextWrapper
import time

import elasticsearch
from flask import abort, Flask, g, render_template, request, session, url_for

import helpers as h

PHRASE_PAT = re.compile('"([^"]*)"*')
BATCH_SIZE = 250
# Elasticsearch doesn't alllow for accessing more than 10K records, even with
# using offsets. There are ways around it, but really, a search that pulls more
# than 10K is not a very good search.
MAX_RECORDS = 10000
MAX_PAGES = int(MAX_RECORDS / BATCH_SIZE)
LIMIT_MSG = "Note: Result sets are limited to %s records" % MAX_RECORDS

es_client = elasticsearch.Elasticsearch(host="dodb")
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
    return [dict((ELASTIC_TO_DB_NAMES.get(k), v)
            for k,v in rec.items()) for rec in recs]


def _extract_records(resp, translate_to_db=True):
    recs = [r["_source"] for r in resp["hits"]["hits"]]
    excepts = 0
    for rec in recs:
        try:
            rec["posted"] = datetime.datetime.strptime(
                    rec["posted"], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            rec["posted"] = datetime.datetime.strptime(
                    rec["posted"], "%Y-%m-%d %H:%M:%S")
            excepts += 1
    if translate_to_db:
        allrecs = [h.DotDict(rec) for rec in db_names_from_elastic(recs)]
    else:
        allrecs = [h.DotDict(rec) for rec in recs]
    g.date_excepts = excepts
    return allrecs


def _get_sort_order(order_by):
    return {"recent_first": "posted:desc",
            "oldest_first": "posted:asc",
            "author_name": "from:asc",
            "natural": ""}.get(order_by)


def _proper_listname(val):
    return {"profox": "ProFox", "prolinux": "ProLinux", "propython":
            "ProPython", "valentina": "Valentina", "codebook": "Codebook",
            "dabo-dev": "Dabo-Dev", "dabo-users": "Dabo-Users"}.get(val, "")


def _listAbbreviation(val):
    return {"profox": "p", "prolinux": "l", "propython": "y",
            "valentina": "v", "codebook": "c", "testing": "t",
            "dabo-dev": "d", "dabo-users": ""}.get(val, "")


def _add_match(lst, key, val, operator=None):
    if operator:
        lst.append({"match": {key: {"query": val, "operator": operator}}})
    else:
        lst.append({"match": {key: val}})


def _add_match_phrase(lst, key, val):
    lst.append({"match_phrase": {key: val}})


def _parse_search_terms(term_string):
    phrases = PHRASE_PAT.findall(term_string)
    terms = PHRASE_PAT.split(term_string)
    for phrase in phrases:
        terms.remove(phrase)
    words_required = []
    words_forbidden = []
    phrases_required = []
    phrases_forbidden = []
    for phrase in phrases:
        phrase = phrase.strip()
        if phrase.startswith("-"):
            phrases_forbidden.append(phrase[1:])
        else:
            phrases_required.append(phrase)
    for term in terms:
        # A 'term' can consist of multiple words.
        term_words = term.split()
        for term_word in term_words:
            term_word = term_word.strip()
            if term_word.startswith("-"):
                words_forbidden.append(term_word[1:])
            else:
                words_required.append(term_word)
    # We have the values in lists, but we need simple strings
    return (" ".join(words_required), " ".join(words_forbidden),
            " ".join(phrases_required), " ".join(phrases_forbidden))


def archives_form(listname=None):
    g.listname = listname
    g.proper_listname = _proper_listname(listname)
    return render_template("archives_form.html")
    

def _format_author(val):
    val = val.split("<")[0]
    return val.replace('"', '')


def _format_date(val):
    return val.strftime("%Y-%m-%d at %H:%M:%S")


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
        page_links.append(f"""<li class={linkstate}><a href={url}?page={pgnum}>{pgnum}</a></li>""")
    page_link_text = "\n        ".join(page_links)

    if thispage == 1:
        prev_text = """<li class="grey-text"><i class="material-icons">chevron_left</i></li>"""
    else:
        prev_text = f"""<li class="waves-effect"><a href="{url}?page={prevpage}"><i class="material-icons">chevron_left</i></a></li>"""
    if thispage == pagecount:
        next_text = """<li class="grey-text"><i class="material-icons">chevron_right</i></li>"""
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

def _wrap_text(txt):
    ret = []
    for ln in txt.splitlines():
        if ln.startswith(">"):
            ret.append(f"<p style=\"font-style: italic; color: grey\">{ln}</p>")
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
    resp = es_client.search("email", doc_type="mail", **kwargs)
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
    kwargs = {"body": {"query": {"regexp": {"subject": subj_regexp}},
		"sort": {"posted": "asc"}}}
    resp = es_client.search("email", doc_type="mail", **kwargs)
    allrecs = _extract_records(resp, translate_to_db=False)
    if not allrecs:
        abort(404, "No message with id=%s exists" % msg_num)
    g.messages = allrecs
    func_dict = {"fmt_author": _format_author, "wrap": _wrap_text}
    return render_template("fullthread.html", **func_dict)


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


def archives_results_GET(listname):
    g.listname = session["listname"] = listname
    g.elapsed = session["elapsed"]
    g.total_pages = session["total_pages"]
    g.limit_msg = session["limit_msg"]
    g.num_results = session["num_results"]
    g.full_results = session["full_results"]
    g.page = int(request.args["page"])
    g.url = request.url
    g.remote_addr = request.remote_addr
    g.kwargs = session["kwargs"]
    g.offset = (g.page - 1) * BATCH_SIZE
    # Make sure we don't exceed elasticsearch's limits
    g.kwargs["from_"] = min(g.offset, MAX_RECORDS - BATCH_SIZE)
    resp = es_client.search("email", doc_type="mail", **g.kwargs)
    g.results = _extract_records(resp, translate_to_db=False)
    g.pager_text = _pager_text()
    func_dict = {"enumerate": enumerate, "fmt_author": _format_author,
            "fmt_date": _format_date}
    return render_template("archive_results.html", **func_dict)


def archives_results_POST(listname):
    g.listname = session["listname"] = listname
    body_terms = request.form.get("body_terms")
    subject = request.form.get("subject_phrase")
    author = request.form.get("author")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    sort_order = _get_sort_order(request.form.get("sort_order"))
    include_OT = bool(request.form.get("chk_OT"))
    include_NF = bool(request.form.get("chk_NF"))

    kwargs = {"body": {"query": {
            "bool": {
                "must": [],
                "must_not": [],
            }}}}
    bqbm = kwargs["body"]["query"]["bool"]["must"]
    neg_bqbm = kwargs["body"]["query"]["bool"]["must_not"]

    listabb = _listAbbreviation(listname)
    _add_match(bqbm, "list_name", listabb)

    (words_required, words_forbidden, phrases_required,
            phrases_forbidden) = _parse_search_terms(body_terms)
    if words_required:
        _add_match(bqbm, "body", words_required, operator="and")
    if words_forbidden:
        _add_match(neg_bqbm, "body", words_forbidden, operator="and")
    if phrases_required:
        _add_match_phrase(bqbm, "body", phrases_required)
    if phrases_forbidden:
        _add_match_phrase(neg_bqbm, "body", phrases_forbidden)
    if subject:
        _add_match_phrase(bqbm, "fulltext_subject", subject)
    if author:
        expr = "*%s*" % author
        bqbm.append({"wildcard": {"from": expr}})
    if not include_OT:
        _add_match(neg_bqbm, "subject", "[OT]")
    if not include_NF:
        _add_match(neg_bqbm, "subject", "[NF]")

    bqbm.append({"range": {"posted": {"gte": start_date}}})
    bqbm.append({"range": {"posted": {"lte": end_date}}})
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
    resp = es_client.search("email", doc_type="mail", **kwargs)
    g.full_results = [r["_source"]["msg_num"] for r in resp["hits"]["hits"]]
    session["full_results"] = g.full_results
    g.num_results = resp["hits"]["total"]
    g.limit_msg = "" if g.num_results <= MAX_RECORDS else LIMIT_MSG
    session["num_results"] = g.num_results
    session["limit_msg"] = g.limit_msg

    # Now run the query for real
    kwargs.pop("_source")
    kwargs["size"] = BATCH_SIZE
    g.offset = int(request.form.get("page", "0")) * BATCH_SIZE
    # Make sure we don't exceed elasticsearch's limits
    kwargs["from_"] = min(g.offset, MAX_RECORDS - BATCH_SIZE)

    session["kwargs"] = g.kwargs = kwargs
    resp = es_client.search("email", doc_type="mail", **kwargs)
    session["elapsed"] = g.elapsed = "%.4f" % (time.time() - startTime)
    total = "{:,}".format(resp["hits"]["total"])
    g.results = _extract_records(resp, translate_to_db=False)
    g.session = session

    # Set up environment vals
    g.url = request.url
    g.remote_addr = request.remote_addr

    page = int(request.form.get("page", "1"))
    calc_pages = int(math.ceil(float(g.num_results) / BATCH_SIZE))
    session["total_pages"] = g.total_pages = min(calc_pages, MAX_PAGES)
    page = min(page, g.total_pages)

    g.page = page
    g.pager_text = _pager_text()
    func_dict = {"enumerate": enumerate, "fmt_author": _format_author,
            "fmt_date": _format_date}
    return render_template("archive_results.html", **func_dict)
