#! /usr/bin/env python

import logging
import logging.config as lconfig
import os
import sys

## base logger
#  Note we do not setup a root logger, as this has nasty interactions with the PyUtils
#  root logger (double copies of messages). Instead we log in the transform module space.
msg = logging.getLogger('MyPackage')

## Map strings to standard logging levels
# FATAL is the same level as CRITICAL (used for parsing athena logfiles)
stdLogLevels = {'DEBUG' : logging.DEBUG,
                'VERBOSE' : logging.DEBUG,
                'INFO' : logging.INFO,
                'WARNING' : logging.WARNING,
                'ERROR' : logging.ERROR,
                'CRITICAL' : logging.CRITICAL,
                'FATAL' : logging.CRITICAL,
                'CATASTROPHE' : logging.CRITICAL+10,  # Special prority level to ensure an error is
                                                      # elevated to be the exitMsg
                }

## This is the correct order to put the most serious stuff first
stdLogLevelsByCritcality = ['FATAL', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'VERBOSE', 'DEBUG']

# If TRF_LOGCONF is defined then try to use that file
# for logging setup
if 'TRF_LOGCONF' in os.environ and os.access(os.environ['TRF_LOGCONF'], os.R_OK):
    lconfig.fileConfig(os.environ['TRF_LOGCONF'])
else:
    # Otherwise use a standard logging configuration
    hdlr = logging.StreamHandler(sys.stdout)
    # asctime seems too verbose...?
    frmt = logging.Formatter("%(name)s.%(funcName)s %(asctime)s %(levelname)s %(message)s")
#    frmt = logging.Formatter("Trf:%(name)s.%(funcName)s %(levelname)s %(message)s")
    hdlr.setFormatter(frmt)
    msg.addHandler(hdlr)
    msg.setLevel(logging.INFO)

## Change the loggging level of the root logger
def setRootLoggerLevel(level):
    msg.setLevel(level)

