#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import time

import utils


def write_to_log(txt):
    with open("cloud_upload.log", "a") as ff:
        ff.write("{}\n".format(txt))


crs = utils.get_cursor()
crs.execute("select iid, ctype, cfile from files where uploaded = 0")
recs = crs.fetchall()
if not recs:
    sys.exit()

for rec in recs:
    iid = rec["iid"]
    section = rec["ctype"]
    filename = rec["cfile"]
    fname = os.path.basename(filename)
    remote_folder = "cb" if section == "c" else ""
    local = os.path.join("/", "var", "www", "uploads", fname)
    folder = os.path.join("ftp", remote_folder)

    write_to_log("{}: Uploading {} to: {}".format(time.ctime(), local, folder))
    try:
        utils.upload_to_DO(local, folder=folder, public=True)
    except Exception as e:
        write_to_log("{}".format(e))
        raise
    write_to_log("{}: Completed upload of {}\n\n".format(time.ctime(), local))

    crs.execute("update files set uploaded=1 where iid = %s", (iid,))
