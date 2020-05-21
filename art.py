from flask import render_template


def about():
    return render_template("art_about.html")


def design():
    return render_template("art_design.html")


def photo_principles():
    return render_template("art_photo_principles.html")
