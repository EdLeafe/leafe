import datetime

from flask import Flask, abort, g, render_template, request, session, url_for
from flask_session import Session

import archives
import art
import downloads
import drstandup
import galleries
import ircsearch
import twitterthread

app = Flask(__name__)
app.secret_key = b"C\xba\x87\xbf\xca'i\xbf\xab\xc4\x9b\x97\xdc\xef\xb0\x9a\xed"
app.url_map.strict_slashes = False
# For uwsgi
application = app

app.config["SESSION_PERMANENT"] = True
app.config["SESSION_TYPE"] = "filesystem"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(hours=12)
Session(app)

#### Basic routes ####
@app.route("/")
def index():
    g.timenow = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    g.param_str = "%s" % dir(request)
    return render_template("index.html")


@app.route("/robots.txt")
def robots():
    return """User-agent: *
Disallow: /
"""


@app.errorhandler(404)
def not_found(e):
    g.url = request.url
    g.error = e
    return render_template("not_found.html")


@app.route("/addalias")
def addalias():
    return "<h3>The addalias function is not yet implemented.</h3>"


@app.route("/ip.html")
def get_ip():
    g.remote_ip = request.environ["REMOTE_ADDR"]
    return render_template("ip.html")


@app.route("/ip")
def get_plain_ip():
    addr = request.environ["REMOTE_ADDR"]
    return f"{addr}"


#### Email list routes ####
@app.route("/email_lists")
def show_email_lists():
    g.email_list_card_color = "light-blue lighten-5 black-text "
    return render_template("email_lists.html")


@app.route("/profox_faq")
def show_profox_faq():
    g.email_list_card_color = "light-blue lighten-5 black-text "
    return render_template("profox_faq.html")


@app.route("/archives/showFullThd")
def old_full_thread():
    session["listname"] = request.args.get("cList", "")
    msg_num = request.args.get("cMsgNum")
    if not msg_num:
        abort(400, f"Invalid URL: {request.url}")
    return archives.show_full_thread(msg_num)


@app.route("/archives/full_thread/<msg_num>", methods=["GET"])
def show_full_thread(msg_num, the_rest=None):
    return archives.show_full_thread(msg_num)


@app.route("/archives/msg/<msg_num>", methods=["GET"])
def show_message(msg_num):
    return archives.show_message(msg_num)


@app.route("/archives/byMID/<listname>/<msg_id>", methods=["GET"])
@app.route("/archives/byMID/<msg_id>", methods=["GET"])
def show_message_by_msgid(msg_id, listname=None):
    return archives.show_message_by_msgid(msg_id)


@app.route("/archives/results", methods=["POST"])
def achives_post_results():
    return archives.archives_results_POST()


@app.route("/archives/results", methods=["GET"])
def achives_get_results():
    return archives.archives_results_GET()


@app.route("/archives/search", methods=["GET"])
@app.route("/archives", methods=["GET"])
def achives_get():
    return archives.archives_form()


#### Download routes ####
@app.route("/downloads")
def dls():
    return downloads.main_page()


@app.route("/search_dls", methods=["POST"])
def search_dls():
    return downloads.search_dls()


@app.route("/download_list")
def list_downloads():
    return downloads.all_dls()


@app.route("/download_file/<url>/<url2>")
@app.route("/download_file/<url>")
def download_file(url, url2=None):
    return downloads.download_file(url, url2=url2)


@app.route("/uploads")
def uploads():
    return downloads.upload()


@app.route("/upload_file", methods=["POST"])
def upload_file():
    return downloads.upload_file()


#### IRC log routes ####
@app.route("/ircsearch", methods=["GET"])
def get_ircsearch():
    return ircsearch.show_search_form()


@app.route("/ircsearch", methods=["POST"])
def post_ircsearch():
    return ircsearch.POST_search_results()


@app.route("/timeline-middle/<channel>/<start>")
def timeline_middle(channel, start, end=None):
    return ircsearch.show_timeline(channel, start, end, True)


@app.route("/timeline/<channel>/<start>", defaults={"end": ""})
@app.route("/timeline/<channel>/<start>/<end>")
def timeline(channel, start, end=None):
    return ircsearch.show_timeline(channel, start, end, False)


#### Twitter threading routes ####
@app.route("/twitterthread", methods=["GET"])
def get_twitterthread():
    return twitterthread.show_form()

@app.route("/twitter_format", methods=["POST"])
def make_twitter_thread():
    return twitterthread.make_thread()


#### Art / photo routes ####
@app.route("/art")
def get_art():
    return art.about()


@app.route("/art/design")
def get_art_design():
    return art.design()


@app.route("/art/galleries")
def show_galleries():
    return galleries.index()


@app.route("/art/galleries/<gallery>")
def show_gallery(gallery):
    return galleries.show_gallery(gallery)


@app.route("/imgtest")
def imgtest():
    return render_template("imgtest.html")


#### DataRobot routes
@app.route("/drstandup", methods=["GET", "POST"])
def standup_order():
    return drstandup.random_order()


#### Linda routes ####
@app.route("/linda")
def show_linda():
    return render_template("linda.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0")
