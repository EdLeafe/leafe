import json
import re

from flask import g, render_template, request

import threadize


def show_form():
    g.chunks = []
    return render_template("twitterthread_form.html")


def make_thread():
    rf = request.form
    txt = rf["source"]
    number_style = rf["number_style"]
    break_at = rf["break_at"]
    end_text = rf["end_text"]
    g.number_style = number_style
    g.break_at = break_at
    g.chunks = threadize.make_thread(txt, number_style, break_at, end_text)
    if request.headers.get("Accept") == "application/json":
        return json.dumps(g.chunks)
    return render_template("twitterthread_results.html")
