#! /usr/bin/env python

import sys

#from myPackage.trfLogger import msg
#msg.info('logging set in %s' % sys.argv[0])

import logging
logging.basicConfig(level=logging.DEBUG)

msg = logging.getLogger('myPackage')
msg.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
msg.addHandler(handler)

from myPackage.trfValidation import userLogFileReport
from myPackage.trfReports import trfJobReport

def main():
    """ Main program """

    msg.info('This is %s', sys.argv[0])
    for arg in sys.argv[1:]:
        print arg

    #search=userLogFileReport('fluentd.log.matched', {"query": {"match" : {"level" : {"query" : "ERROR" }}}}, 100)
    search=userLogFileReport('fluentd.log.matched', {"query": {"bool" : {"should" : [{"match" : {"level" : "FATAL" }}, {"match" : {"level" : "CRITICAL" }}, {"match" : {"level" : "ERROR" }}, {"match" : {"level" : "WARNING" }}]}}}, 100)


    jobReport=trfJobReport(search)
    jobReport.writeJSONReport(filename='jobReport.json')

    reporte = search.python
    print('reporte {}'.format(reporte))
    print('worstError {}'.format(search.worstError()))
    print('firstError {}'.format(search.firstError(floor='WARNING')))



if __name__ == '__main__':
    main()

