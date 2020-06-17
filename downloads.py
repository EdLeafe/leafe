import datetime
from functools import partial
import os
import re
import smtplib
import stat
import shutil
import time

from flask import abort, g, redirect, render_template, request, url_for

import utils


UPLOAD_DIR = "/var/www/uploads"
DOWNLOAD_PATH = "download_file"
DLBASE = f"https://leafe.com/{DOWNLOAD_PATH}"
#CDNBASE = "https://baba3e9f50e49daa7c3f-032440835eb7c07735745c77228f7f03.ssl.cf1.rackcdn.com"
CDNBASE = "https://com-leafe-images.nyc3.cdn.digitaloceanspaces.com/ftp"
LICENSES = {"f": "Freeware ", "s": "Shareware ", "c": "Commercial ",
        "d": "Demoware ", "g": "GPL Software ", "l": "LGPL Software ",
        "m": "Creative Commons License ", "o": "Other Open Source License "}

search_term = ""


def _cost_type(val, cost):
    license = LICENSES.get(val, "")
    if cost:
       cost_text = " - $%s" % cost
    else:	
       cost_text = ""
    return "".join([license, cost_text])


def _hilite_match(val, txt):
    if not val:
        return txt
    pat = re.compile(rf"\b{val}\b", re.I)
    repl = f'<span class="searchmatch">{val}</span>'
    return pat.sub(repl, txt)


def download_file(url, url2=None):
    passed_url = os.path.join(url, url2) if url2 else url
    full_url = os.path.join(CDNBASE, passed_url)
    return redirect(full_url)


def main_page():
    return render_template("downloads.html")


def search_dls():
    global search_term
    search_term = request.form.get("term")
    term = """ and mdesc like '%%%s%%' 
            or ctitle like '%%%s%%' 
            or cauthor like '%%%s%%' """ % (search_term, search_term, search_term)
    return _run_query(term=term)


def all_dls():
    return _run_query(term="")


def _update_link(link):
    """The database contains links in the format
    'http://leafe.com/download/<fname>'. I want this to be more explicit by
    specifying the link as '/download_file/<fname>', so this function does
    that. When I convert the site to use exclusively this newer code, I can
    update the database, making this function moot.
    """
    return link.replace("/download/", "/download_file/")


def _run_query(term=None):
    term = term or ""
    crs = utils.get_cursor()
    sql = """select * from files where lpublish = 1 %s
            order by ctype ASC, dlastupd DESC;""" % term
    crs.execute(sql)
    recs = crs.fetchall()

    g.vfp = [d for d in recs if d["ctype"] == "v"]
    g.dabo = [d for d in recs if d["ctype"] == "b"]
    g.python = [d for d in recs if d["ctype"] == "p"]
    g.osx = [d for d in recs if d["ctype"] == "x"]
    g.cb = [d for d in recs if d["ctype"] == "c"]
    g.fox2x = [d for d in recs if d["ctype"] == "f"]
    g.other = [d for d in recs if d["ctype"] == "o"]

    hl_func = partial(_hilite_match, search_term)

    func_dict = {"hilite": hl_func, "cost_calc": _cost_type, "any": any,
            "update_link": _update_link}
    return render_template("download_list.html", **func_dict)


def upload():
    g.message = ""
    return render_template("upload.html")


def upload_file():
    post = request.form
    newfile = request.files.get("newfile")
    try:
        newname = newfile.filename
    except AttributeError:
        # Will happen if newfile is None
        abort(400, "No file specified")
    target_file = os.path.join(UPLOAD_DIR, newname.replace(os.sep, "_"))

    with open(target_file, "wb") as file_obj:
        shutil.copyfileobj(newfile.stream, file_obj)
    newfile.stream.close()
    file_size = os.stat(target_file)[stat.ST_SIZE]

    fsize = utils.human_fmt(file_size).replace(" ","")
    # Don't use the CDN; use the generic download URL that will redirect.
    fldr = {"c": "cb", "d": "dabo"}.get(post["section"], "")
    cfile = os.path.join(DLBASE, fldr, newname)

    sql = """INSERT INTO files (ctype, ctitle, mdesc, cfile, ccosttype, ncost,
            csize, cauthor, cauthoremail, dlastupd, lpublish)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    args = (post.get("section"), post.get("title"), post.get("description"),
            cfile, post.get("file_license"), post.get("cost"), fsize,
            post.get("author"), post.get("author_email"),
            datetime.date.today(), False)
    crs = utils.get_cursor()
    crs.execute(sql, args)

    body = """Originating IP = %s
Section = %s
Title = %s
File = %s
License = %s
Cost = %s
Size = %s
Author = %s
Email = %s

Description:
%s
""" % (request.remote_addr, post.get("section"), post.get("title"), newname, post.get("file_license"), post.get("cost"),
    fsize, post.get("author"), post.get("author_email"), post.get("description"))

    msg = """From: File Uploads <files@leafe.com>
X-Mailer: flask script
To: Ed Leafe <ed@leafe.com>
Subject: New Uploaded File
Date: %s

%s
""" % (time.strftime("%c"), body)
    smtp = smtplib.SMTP("mail.leafe.com")
    smtp.sendmail("files@leafe.com", "ed@leafe.com", msg)

    g.message = "Your file has been uploaded."
    return render("upload.html")

