from flask import Flask, render_template

from .aggregator import aggregate

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    records = aggregate(scrapers=[])
    return render_template("index.html", records=records)
