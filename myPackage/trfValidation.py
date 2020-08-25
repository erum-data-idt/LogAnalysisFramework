from future.utils import iteritems
from builtins import object

## @package PyJobTransforms.trfValidation
#
# @brief Validation control for user job
# @details Contains validation classes controlling how the transforms
# @author vogelgonzalez@uni-wuppertal.de
# @version $Id: trfValidation.py 782012 2016-11-03 01:45:33Z uworlika $

import os
import json
import os.path as path
from elasticsearch import Elasticsearch
from myPackage.trfLogger import stdLogLevels

import logging
msg = logging.getLogger(__name__)

## @brief A class holding report information from an ES index
#  This is pretty much a virtual class, fill in the specific methods
#  when you know what type of logfile you are dealing with
class logFileReport(object):
    def __init__(self, index=None, body={}, msgLimit=100, msgDetailLevel=stdLogLevels['ERROR']):

        self._index = index
        self._body = body
        self._msgLimit = msgLimit
        self._msgDetails = msgDetailLevel

        if index:
            self.searchIndex()

    def resetReport(self):
        pass

    def searchIndex(self):
        pass

    def worstError(self):
        pass

    def firstError(self):
        pass

    def __str__(self):
        return ''


## @class logFileReport
#  @brief Logfile suitable for scanning logfiles with an athena flavour, i.e.,
#  lines of the form "SERVICE  LOGLEVEL  MESSAGE"
class userLogFileReport(logFileReport):
    ## @brief Class constructor
    #  @param logfile Logfile (or list of logfiles) to scan
    #  @param substepName Name of the substep executor, that has requested this log scan
    #  @param msgLimit The number of messages in each category on which a
    def __init__(self, index, body, msgLimit, msgDetailLevel=stdLogLevels['ERROR']):

        self.resetReport()

        super(userLogFileReport, self).__init__(index, body, msgLimit, msgDetailLevel)

    ## Produce a python dictionary summary from querying the index for inclusion
    #  in the job report
    @property
    def python(self):
        errorDict = {'countSummary': {}, 'details': {}}
        for level, count in iteritems(self._levelCounter):
            errorDict['countSummary'][level] = count
            if self._levelCounter[level] > 0 and len(self._errorDetails[level]) > 0:
                errorDict['details'][level] = []
                for error in self._errorDetails[level]:
                    errorDict['details'][level].append(error)
        return errorDict

    def resetReport(self):
        self._levelCounter = {}
        for level in list(stdLogLevels) + ['UNKNOWN']:
            self._levelCounter[level] = 0

        self._errorDetails = {}
        for level in self._levelCounter:
            self._errorDetails[level] = []
            # Format:
            # List of dicts {'message': errMsg, 'firstLine': lineNo, 'count': N}


    def findFile(self,pathvar, fname):
        # First see if the file already includes a path.
        msg.debug('Finding full path for {fileName} in path {path}'.format(
            fileName = fname,
            path = pathvar
        ))
        if fname.startswith('/'):
            return(fname)

        # Split the path.
        pathElements = pathvar.split(':')
        for pathElement in pathElements:
            if path.exists(path.join(pathElement, fname)):
                return(path.join(pathElement, fname))

        return(None)


    ## An error file consists of non-standard logging error lines
    def errorFileHandler(self, errorfile):
        # loading non-categorized error line(s) from error file
        linesList = []
        fullName = self.findFile(os.environ['DATAPATH'], errorfile)
        if not fullName:
            msg.warning('Error file {0} could not be found in DATAPATH'.format(errorfile))
        try:
            with open(fullName) as errorFileHandle:
                msg.debug('Opened error file {0} from here: {1}'.format(errorfile, fullName))

                for line in errorFileHandle:
                    #line = line.rstrip('\n')
                    linesList.append(json.loads(line))
        except OSError as e:
            msg.warning('Failed to open error file {0}: {1}'.format(fullName, e))
        return linesList

    def searchIndex(self, resetReport=False):
        try: 
            es = Elasticsearch([{'host': 'localhost', 'port': 9200}])
        except IOError as e: 
            msg.error('Failed to establish a connection to ElasticSearch server: {0}'.format(e))

        nonStandardErrorsList = self.errorFileHandler('nonStandardErrors.db')
        msg.debug('List of unstructured errors: {0}'.format(nonStandardErrorsList))

        if resetReport:
            self.resetReport()

        msg.debug('Implementing search query for index {0}'.format(self._index))
        results = {}
        seenNonStandardError = ''
        try:
            results = es.search(index=self._index, size = 1000, body=self._body)
        except IOError as e:
            msg.error('Failed to open log file index {0}: {1:s}'.format(self._index, e))
            # Return this as a small report
            self._levelCounter['ERROR'] = 1
            self._errorDetails['ERROR'] = {'message': str(e), 'firstLine': 0, 'count': 1}
            return
        ## Loop over the hits returned by the search
        for hit in results['hits']['hits']:
            if 'line' in hit["_source"]:# if the record is unstructured, match whole line
                #if any(hit["_source"]['line'] in l['line'] for l in nonStandardErrorsList):
                for l in nonStandardErrorsList:
                    if hit["_source"]['line'] in l['line']:
                        msg.warning('Loading error handler')
                        #self.loadErrorHandler(l['errorHandler'])
                        print("message: {} handler: {}".format(hit["_source"]['line'], l['errorHandler']))
                        continue
                msg.debug('Non-standard line in %s: %s' % (self._index, hit["_source"]['line']))
                self._levelCounter['UNKNOWN'] += 1
                continue

            # we need to produce an intermediate output, an error dictionary, then commit to transform error dictionary
            # Line was matched successfully
            fields = {}
            for matchKey in ('service', 'level', 'message'):#or, this can be an argument
                fields[matchKey] = hit["_source"][matchKey]
            #msg.debug('Line parsed as: {0}'.format(fields))
            msg.info('Line parsed as: {0}'.format(fields))
            #print('Line parsed as: {0}'.format(fields))

            # this nees to be set to the original position in the log file of the record
            lineCounter = 1

            # Count this error
            self._levelCounter[fields['level']] += 1


            # Record some error details
            if stdLogLevels[fields['level']] >= self._msgDetails:
                if self._levelCounter[fields['level']] <= self._msgLimit:
                    detailsHandled = False
                    for seenError in self._errorDetails[fields['level']]:
                        if seenError['message'] == fields['message']:
                            seenError['count'] += 1
                            detailsHandled = True
                            break
                    if detailsHandled is False:
                        self._errorDetails[fields['level']].append({'message': fields['message'], 'firstLine': lineCounter, 'count': 1})
                elif self._levelCounter[fields['level']] == self._msgLimit + 1:
                    msg.warning("Found message number {0} at level {1} - this and further messages will be supressed from the report".format(self._levelCounter[fields['level']], fields['level']))
                else:
                    # Overcounted
                    pass
        reporte = self.python
        print('reporte {}'.format(reporte))


    ## Return the worst error found from querying the index (first error of the most serious type)
    def worstError(self):
        worst = stdLogLevels['DEBUG']
        worstName = 'DEBUG'
        for lvl, count in iteritems(self._levelCounter):
            if count > 0 and stdLogLevels.get(lvl, 0) > worst:
                worstName = lvl
                worst = stdLogLevels[lvl]
        if len(self._errorDetails[worstName]) > 0:
            firstError = self._errorDetails[worstName][0]
        else:
            firstError = None

        return {'level': worstName, 'nLevel': worst, 'firstError': firstError}


    ## Return the first error found in the logfile above a certain loglevel
    def firstError(self, floor='ERROR'):
        firstLine = firstError = None
        firstLevel = stdLogLevels[floor]
        firstName = floor
        for lvl, count in iteritems(self._levelCounter):
            if (count > 0 and stdLogLevels.get(lvl, 0) >= stdLogLevels[floor] and
                (firstError is None or self._errorDetails[lvl][0]['firstLine'] < firstLine)):
                firstLine = self._errorDetails[lvl][0]['firstLine']
                firstLevel = stdLogLevels[lvl]
                firstName = lvl
                firstError = self._errorDetails[lvl][0]

        return {'level': firstName, 'nLevel': firstLevel, 'firstError': firstError}



#does the position of a message in the log file map to a position in the index? Does it get properly assigned
# in the error dictionaries?
# investigate the reason for using property
