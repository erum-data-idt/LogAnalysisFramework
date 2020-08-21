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

def main():
    """ Main program """

    msg.info('This is %s', sys.argv[0])
    for arg in sys.argv[1:]:
        print arg

    search=userLogFileReport('fluentd.log.matched', {"query": {"match" : {"level" : {"query" : "ERROR" }}}}, 100)



if __name__ == '__main__':
    main()

