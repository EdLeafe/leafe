import datetime

from flask import Flask, g, render_template, request, url_for

import archives
#import welcome

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
    g.email_list_card_color = "grey lighten-3 black-text "
    return render_template("email_lists.html")

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

@app.route("/ip.html")
def get_ip():
    g.remote_ip = request.environ["REMOTE_ADDR"]
    return render_template("ip.html")

@app.route("/ip")
def get_plain_ip():
    return f'{request.environ["REMOTE_ADDR"]}'
    return render_template("ip.html")


@app.route("/test")
def test():
    import test
    return test.test_page()


@app.errorhandler(404)
def not_found(e):
    g.url = request.url
    g.error = e
    return render_template("not_found.html")


#@app.route("/archives", strict_slashes=False)
#@app.route("/archives/<listname>")
#def get_archives(listname=None):
#    return archives.GET_archives(listname=listname)


if __name__ == "__main__":
    app.run(host='0.0.0.0')
