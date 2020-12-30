import requests

from flask import render_template


BLOG_URL = "https://blog.leafe.com/category/art,photography/feed/"


def about():
    return render_template("art_about.html")


def design():
    return render_template("art_design.html")


def photo_principles():
    return render_template("art_photo_principles.html")


def art_blog():
    resp = requests.get(BLOG_URL)
    with open("blog.xml", "w") as ff:
        ff.write(resp.text)
