"""
Helper app. This creates routes and renders templates for development.
For production, everything will get baked out into flat files.
"""
import os
from flask import Flask, g, render_template, url_for
from flask_peewee.db import Database
from peewee import DateField, DecimalField, CharField
# mise en place

ROOT = os.path.realpath(os.path.dirname(__file__))
f = lambda *fn: os.path.join(ROOT, *fn)

DEBUG = True

DATABASE = {
	'name': f('drought.db'),
	'engine': 'peewee.SqliteDatabase'
}

DATE_FORMAT = "%b %d, %Y"

app = Flask(__name__)
app.config.from_object(__name__)

db = Database(app)

IMG_PATH = 'img/drought/'

# models
class Report(db.Model):
	"""
	A weekly drought report.

	Drought levels are stored as unique amounts, not aggregates, meaning that
	adding all drought levels (including "nothing") should equal 100.
	"""
	date = DateField()
	locale = CharField()

	# drought levels
	nothing = DecimalField()
	d0 = DecimalField()
	d1 = DecimalField()
	d2 = DecimalField()
	d3 = DecimalField()
	d4 = DecimalField()

	def __unicode__(self):
		return u'%s: %s' % (self.locale, self.date.strftime(DATE_FORMAT))


# views
@app.route('/')
def us():
	"""
	Show the US-level view of the drought.
	"""
	g.IMG_PATH = static(IMG_PATH)
	drought = Report.select().where(Report.locale == 'US')

	return render_template('drought.html', drought=drought, static=static)


def static(filename):
	"""
	Return a static url for the given filename.
	Meant for use in templates.
	"""
	return url_for('static', filename=filename)


