import datetime
import decimal
import glob
import json
import os
import urllib

from fabric.api import *
from lxml import etree

from app import app, db, Report

DATE_FORMAT = "usdm%y%m%d"
SHORT_DATE_FORMAT = "%y%m%d"

DROUGHT_URL = "http://droughtmonitor.unl.edu/shapefiles_combined/%(year)s/usdm%(year)s.zip"

ROOT = os.path.realpath(os.path.dirname(__file__))
YEARS = range(2000, 2014)

_f = lambda *fn: os.path.join(ROOT, *fn)

env.exclude_requirements = [
    'wsgiref', 'readline', 'ipython',
    'git-remote-helpers',
]

env.repos = {
    'origin': ['master', 'master:gh-pages'],
    'years': ['master', 'master:gh-pages']
}

env.states = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", 
              "DE", "DC", "FL", "GA", "HI", "ID", "IL", 
              "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
              "MA", "MI", "MN", "MS", "MO", "MT", "NE", 
              "NV", "NH", "NJ", "NM", "NY", "NC", "ND", 
              "OH", "OK", "OR", "PA", "PR", "RI", "SC", 
              "SD", "TN", "TX", "UT", "VT", "VA", "WA", 
              "WV", "WI", "WY"]

########################
# Project-level controls
########################

def deploy():
    for remote, branches in env.repos.items():
        for branch in branches:
            local('git push %s %s' % (remote, branch))


def freeze():
    """
    pip freeze > requirements.txt, excluding virtualenv clutter
    """
    reqs = local('pip freeze', capture=True).split('\n')
    reqs = [r for r in reqs if r.split('==')[0] not in env.exclude_requirements]
    reqs = '\n'.join(reqs)

    with open('requirements.txt', 'wb') as f:
        f.write(reqs)

    print reqs

##############
# Maps and GIS
##############

def raster():
    """
    Create a raster image for each weekly drought snapshot.
    This runs one year at a time to isolate errors.
    """
    for year in YEARS:
        local(_f('bin/raster.js --year %i' % year))

    # update weeks.js
    weeksjs()


def reproject(infile):
    """
    Project a file to EPSG:4326.
    """
    filename = os.path.basename(infile).lower()
    files = {
        'outfile': _f('data/shapefiles', filename),
        'infile' : infile
    }
    # ogr2ogr won't overwrite
    if os.path.exists(files['outfile']):
        local('rm %(outfile)s' % files)

    local('ogr2ogr -t_srs EPSG:4326 %(outfile)s %(infile)s' % files)


def reproject_year(year):
    """
    Project shapefiles for a single year.
    """
    year = str(year)
    for shp in glob.iglob(_f('data/raw', year, '*.shp')):
        reproject(shp)


def reproject_all():
    """
    Find all the shapefiles with glob, and loop through them
    reproject each one
    """
    for shp in glob.iglob(_f('data/raw/**/*.shp')):
        reproject(shp)


def topojson():
    """
    Create a single topojson file from every shapefile.
    """
    shapefiles = _f('data/shapefiles/*.shp')
    local('topojson --id-property DM -o %s -- %s' % (_f('data/drought.json'), shapefiles))


def update_shapefiles(year=2013):
    """
    Download, unzip and reproject all shapefiles from US Drought Monitor
    """
    year = str(year)
    url = DROUGHT_URL % {'year': year}

    # ensure directories exist
    local('mkdir -p %s' % _f('data/raw'))
    local('mkdir -p %s' % _f('data/shapefiles'))

    # grab the url
    # need to make this generic
    zipfile = _f('data/raw', year + '.zip')
    local('curl %s > %s' % (url, zipfile))

    # unzip files into a year directory, just to keep things sane
    dest = _f('data/raw/', year)
    local('unzip -u -d %s %s' % (dest, zipfile))

    reproject_year(year)


def update(start=2000, end=2013):
    """
    Run update_shapefiles for years between start and end.
    """
    start = int(start)
    end = int(end)

    for year in range(start, end + 1):
        update_shapefiles(year)


def weeks():
    """
    Get a list of weeks represented in our shapefile directory.
    These will match names of shapefiles embedded in drought.json.
    """
    images = glob.glob(_f('static/img/drought', '*.png'))
    for image in images:
        name = os.path.basename(image)
        name, ext = os.path.splitext(name)
        yield name


def weeksjs():
    """
    Render a javascript file for weekly shapefile snapshots.
    """
    outfile = _f('static/js/weeks.js')
    js = "var WEEKS = %s;" % json.dumps(list(weeks()), indent=4)
    with open(outfile, 'wb') as f:
        f.write(js)

#################
# App controls
#################

def create_tables(fail_silently=True):
    """
    Create tables needed to store drought data
    """
    db.connect_db()
    Report.create_table(fail_silently=bool(fail_silently))


def drop_tables(fail_silently=False):
    """
    Drop tables. Be careful here.
    """
    db.connect_db()
    Report.drop_table(fail_silently=bool(fail_silently))


def reset_db():
    """
    Drop and recreate tables.
    """
    drop_tables()
    create_tables()


def load_data(locale='US'):
    """
    Load US-level or state-level drought data from Drought Monitor's XML.

    <week name="total" date="130716">
        <Nothing>46.45</Nothing>
        <D0>53.55</D0>
        <D1>41.02</D1>
        <D2>28.66</D2>
        <D3>11.15</D3>
        <D4>3.63</D4>
    </week>

    """
    # make sure we're connected
    db.connect_db()

    if locale == "US":
        url = "http://droughtmonitor.unl.edu/tabular/total_archive.xml"

    else:
        locale = locale.upper()
        url = "http://droughtmonitor.unl.edu/tabular/%s.xml" % locale

    # grab xml from the drought monitor
    root = etree.parse(url).getroot()

    # and load!
    for week in root.findall('week'):
        
        # get a date
        date = datetime.datetime.strptime(
            week.get('date'), SHORT_DATE_FORMAT).date()

        # get or update a Report object
        try:
            report = Report.get(Report.date == date, Report.locale == locale)
        except Report.DoesNotExist:
            report = Report(date=date, locale=locale)

        # update data
        nothing = week.find('Nothing').text
        D0 = decimal.Decimal(week.find('D0').text)
        D1 = decimal.Decimal(week.find('D1').text)
        D2 = decimal.Decimal(week.find('D2').text)
        D3 = decimal.Decimal(week.find('D3').text)
        D4 = decimal.Decimal(week.find('D4').text)

        # remove the combined areas
        report.D0 = D0 - D1
        report.D1 = D1 - D2
        report.D2 = D2 - D3
        report.D3 = D3 - D4
        report.D4 = D4

        # store the overlapping (as reported) data
        report.D0_D4 = D0
        report.D1_D4 = D1
        report.D2_D4 = D2
        report.D3_D4 = D3

        report.nothing = nothing

        # save and we're done
        report.save()

        print "Updated: %s" % unicode(report)


def load_all():
    """
    Load all US and state-level data.
    """
    load_data('US')
    
    for state in env.states:
        load_data(state)


def devserver():
    """
    Run the Flask development server.
    """
    app.run(debug=True)

