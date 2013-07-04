import datetime
import glob
import os
from fabric.api import *

DATE_FORMAT = "usdm%y%m%dm"
ROOT = os.path.realpath(os.path.dirname(__file__))
URL = "http://droughtmonitor.unl.edu/shapefiles_combined/2013/usdm%i.zip"
YEARS = range(2000, 2013)

_f = lambda *fn: os.path.join(ROOT, *fn)

env.exclude_requirements = [
    'wsgiref', 'readline', 'ipython',
    'git-remote-helpers',
]

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

def reproject(infile):
    """
    Project a file to EPSG:4326.
    """
    filename = os.path.basename(infile)
    files = {
        'outfile': _f('data/shapefiles', filename),
        'infile' : infile
    }

    local('ogr2ogr -t_srs EPSG:4326 %(outfile)s %(infile)s' % files)


def topojson():
    """
    Create a single topojson file from every shapefile.
    """
    shapefiles = _f('data/shapefiles/*.shp')
    local('topojson --id-property DM -o %s -- %s' % (_f('data/drought.json'), shapefiles))


def update_shapefiles():
    """
    Download, unzip and reproject all shapefiles from US Drought Monitor
    """
    year = 2013
    url = URL % year

    # ensure directories exist
    local('mkdir -p %s' % _f('data/raw'))
    local('mkdir -p %s' % _f('data/shapefiles'))

    # grab the url
    # need to make this generic
    local('wget %s' % url)

    # this'll get less hard-coded later
    # move the downloaded zip file to ./data/raw
    local('mv usdm2013.zip %s' % (_f('data/raw')))

    # unzip files into a year directory, just to keep things sane
    local('unzip %s -d %s' % (_f('data/raw/usdm2013.zip'), _f('data/raw/', str(year))))

    # find all the shapefiles with glob, and loop through them
    # reproject each one
    for shp in glob.glob(_f('data/raw/', str(year), '*.shp')):
        reproject(shp)


