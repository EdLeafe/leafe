import datetime

from flask import Flask, g, render_template, request, url_for

import archives
import art
import downloads

app = Flask(__name__)
app.secret_key = b"C\xba\x87\xbf\xca'i\xbf\xab\xc4\x9b\x97\xdc\xef\xb0\x9a\xed"


@app.route("/")
def index():
    g.timenow = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    g.param_str = "%s" % dir(request)
    return render_template("index.html")

@app.route("/addalias")
def addalias():
    return "<h3>The addalias function is not yet implemented.</h3>"

@app.route("/email_lists")
def show_email_lists():
    g.email_list_card_color = "light-blue lighten-5 black-text "
    return render_template("email_lists.html")

@app.route("/profox_faq")
def show_profox_faq():
    g.email_list_card_color = "light-blue lighten-5 black-text "
    return render_template("profox_faq.html")

@app.route("/archives/full_thread/<msg_num>", methods=["GET"])
def show_full_thread(msg_num):
    return archives.show_full_thread(msg_num)

@app.route("/archives/msg/<msg_num>", methods=["GET"])
def show_message(msg_num):
    return archives.show_message(msg_num)

@app.route("/archives/results/<listname>", methods=["POST"])
def achives_post_results(listname):
    return archives.archives_results_POST(listname)

@app.route("/archives/results/<listname>", methods=["GET"])
def achives_get_results(listname):
    return archives.archives_results_GET(listname)

@app.route("/archives/<listname>", methods=["GET"])
def achives_get_listname(listname):
    return archives.archives_form(listname)

@app.route("/archives", methods=["GET"])
def achives_get():
    return archives.archives_form()

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

@app.route("/ip.html")
def get_ip():
    g.remote_ip = request.environ["REMOTE_ADDR"]
    return render_template("ip.html")

@app.route("/ip")
def get_plain_ip():
    addr = request.environ['REMOTE_ADDR']
    return f"{addr}"

@app.route("/art")
def get_art():
    return art.about()

@app.route("/art/galleries")
def show_galleries():
    return art.show_galleries()

@app.errorhandler(404)
def not_found(e):
    g.url = request.url
    g.error = e
    return render_template("not_found.html")


if __name__ == "__main__":
    app.run(host='0.0.0.0')
