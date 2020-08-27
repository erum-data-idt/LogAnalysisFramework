from __future__ import print_function
from __future__ import division
from future.utils import iteritems
from future.utils import itervalues


from builtins import object
from future import standard_library
standard_library.install_aliases()

from builtins import int

#  Classes whose instance encapsulates transform reports

__version__ = '$Revision: 000001 $'

import pickle as pickle
import json
import os.path
import platform
import pprint
import sys

from xml.etree import ElementTree

import logging
msg = logging.getLogger(__name__)



## @brief Base (almost virtual) report from which all reports derive
class trfReport(object):
    def __init__(self, query = {}):
        self._query = query
        self._dataDictionary = {}
        pass

    ## @brief String representation of the job report
    #  @details Uses pprint module to output the python object as text
    #  @note This is a 'property', so no @c fast option is available
    def __str__(self):
        return pprint.pformat(self.python())

    ## @brief Method which returns a python representation of a report
    def python(self):
        return {}

    ## @brief Method which returns a JSON representation of a report
    #  @details Calls @c json.dumps on the python representation
    def json(self):
        return json.dumps(self.python, type)

    ## @brief Method which returns an ElementTree.Element representation of the old POOLFILECATALOG report
    def classicEltree(self):
        return ElementTree.Element('POOLFILECATALOG')

    ## @brief Method which returns a python representation of a report in classic Tier 0 style
    def classicPython(self):
        return {}

    def writeJSONReport(self, filename, sort_keys = True, indent = 2):
        with open(filename, 'w') as report:
            try:
                if not self._dataDictionary:
                    self._dataDictionary = self.python()

                json.dump(self._dataDictionary, report, sort_keys = sort_keys, indent = indent)
            except TypeError as e:
                # TypeError means we had an unserialisable object - re-raise as a trf internal
                message = 'TypeError raised during JSON report output: {0!s}'.format(e)
                msg.error(message)
                raise trfExceptions.TransformReportException(trfExit.nameToCode('TRF_INTERNAL_REPORT_ERROR'), message)

    def writeTxtReport(self, filename, dumpEnv = True):
        with open(filename, 'w') as report:
            if not self._dataDictionary:
                self._dataDictionary = self.python()

            print('# {0} file generated on'.format(self.__class__.__name__), file=report)
            print(pprint.pformat(self._dataDictionary), file=report)
            if dumpEnv:
                print('# Environment dump', file=report)
                eKeys = list(os.environ)
                eKeys.sort()
                for k in eKeys:
                    print('%s=%s' % (k, os.environ[k]), file=report)

    def writeGPickleReport(self, filename):
        with open(filename, 'wb') as report:
            pickle.dump(self.classicPython(), report)

    def writeClassicXMLReport(self, filename):
        with open(filename, 'w') as report:
            #print(prettyXML(self.classicEltree(), poolFileCatalogFormat = True), file=report)
            print(self.classicEltree(), file=report)

    def writePilotPickleReport(self, filename):
        with open(filename, 'w') as report:
            if not self._dataDictionary:
                self._dataDictionary = self.python()

            pickle.dump(self._dataDictionary, report)


## Class holding a job report
class trfJobReport(trfReport):
    ## This is the version counter for job reports
    #  any changes to the format can be reflected by incrementing this counter
    _reportVersion = '1.0.0'

    def __init__(self, query = {}):
        super(trfJobReport, self).__init__(query)

    ## Generate the python transform job report
    def python(self):
        myDict = {'reportVersion': self._reportVersion,
                  'logReport': {},
                  'logFile': {}
                  }

        myDict['logReport']['messages'] = self._query.python
        myDict['logReport']['firstError'] = self._query.firstError(floor='WARNING')
        myDict['logReport']['worstError'] = self._query.worstError()

        return myDict

