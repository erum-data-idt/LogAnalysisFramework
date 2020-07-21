from future.utils import iteritems
from future.utils import listitems

from past.builtins import basestring
from builtins import zip
from builtins import object
from builtins import range
from builtins import int

# Copyright (C) 2002-2017 CERN for the benefit of the ATLAS collaboration

## @package PyJobTransforms.trfValidation
#
# @brief Validation control for job transforms
# @details Contains validation classes controlling how the transforms
# will validate jobs they run.
# @author atlas-comp-transforms-dev@cern.ch
# @version $Id: trfValidation.py 782012 2016-11-03 01:45:33Z uworlika $
# @note Old validation dictionary shows usefully different options:
# <tt>self.validationOptions = {'testIfEmpty' : True, 'testIfNoEvents' : False, 'testIfExists' : True,
#                          'testIfCorrupt' : True, 'testCountEvents' : True, 'extraValidation' : False,
#                          'testMatchEvents' : False, 'testEventMinMax' : True , 'stopOnEventCountNone' : True,
#                          'continueOnZeroEventCount' : True}</tt>
import fnmatch
import os
import re

from subprocess import Popen, STDOUT, PIPE

import logging
msg = logging.getLogger(__name__)

from PyUtils import RootUtils

from PyJobTransforms.trfExitCodes import trfExit
from PyJobTransforms.trfLogger import stdLogLevels
from PyJobTransforms.trfArgClasses import argFile

import PyJobTransforms.trfExceptions as trfExceptions
import PyJobTransforms.trfUtils as trfUtils


## @brief Class of patterns that can be ignored from athena logfiles
class ignorePatterns(object):

    ## @brief Load error patterns from files
    #  @details Load regular expressions to be used in logfile parsing
    #  Files to load up structured error patterns from
    #  @param extraSearch Extra regexp strings to @a search against
    def __init__(self, files=['atlas_error_mask.db'], extraSearch = []):
        # Setup structured search patterns
        self._structuredPatterns = []
        self._initalisePatterns(files)

        # Setup extra search patterns
        self._searchPatterns = []
        self._initialiseSerches(extraSearch)

    @property
    def structuredPatterns(self):
        return self._structuredPatterns

    @property
    def searchPatterns(self):
        return self._searchPatterns

    def _initalisePatterns(self, files):
        for patternFile in files:
            if patternFile == "None":
                continue
            fullName = trfUtils.findFile(os.environ['DATAPATH'], patternFile)
            if not fullName:
                msg.warning('Error pattern file {0} could not be found in DATAPATH'.format(patternFile))
                continue
            try:
                with open(fullName) as patternFileHandle:
                    msg.debug('Opened error file {0} from here: {1}'.format(patternFile, fullName))

                    for line in patternFileHandle:
                        line = line.strip()
                        if line.startswith('#') or line == '':
                            continue
                        try:
                            # N.B. At the moment release matching is not supported!
                            (who, level, message) = [ s.strip() for s in line.split(',', 2) ]
                            if who == "":
                                # Blank means match anything, so make it so...
                                who = "."
                            reWho = re.compile(who)
                            reLevel = level # level is not a regexp (for now)
                            reMessage = re.compile(message)
                        except ValueError:
                            msg.warning('Could not parse this line as a valid error pattern: {0}'.format(line))
                            continue
                        except re.error as e:
                            msg.warning('Could not parse valid regexp from {0}: {1}'.format(message, e))
                            continue

                        msg.debug('Successfully parsed: who={0}, level={1}, message={2}'.format(who, level, message))

                        self._structuredPatterns.append({'service': reWho, 'level': level, 'message': reMessage})

            except (IOError, OSError) as xxx_todo_changeme:
                (errno, errMsg) = xxx_todo_changeme.args
                msg.warning('Failed to open error pattern file {0}: {1} ({2})'.format(fullName, errMsg, errno))


    def _initialiseSerches(self, searchStrings=[]):
        for string in searchStrings:
            try:
                self._searchPatterns.append(re.compile(string))
                msg.debug('Successfully parsed additional logfile search string: {0}'.format(string))
            except re.error as e:
                msg.warning('Could not parse valid regexp from {0}: {1}'.format(string, e))



## @brief A class holding report information from scanning a logfile
#  This is pretty much a virtual class, fill in the specific methods
#  when you know what type of logfile you are dealing with
class logFileReport(object):
    def __init__(self, logfile=None, msgLimit=10, msgDetailLevel=stdLogLevels['ERROR']):

        # We can have one logfile or a set
        if isinstance(logfile, basestring):
            self._logfile = [logfile, ]
        else:
            self._logfile = logfile

        self._msgLimit = msgLimit
        self._msgDetails = msgDetailLevel
        self._re = None

        if logfile:
            self.scanLogFile(logfile)

    def resetReport(self):
        pass

    def scanLogFile(self):
        pass

    def worstError(self):
        pass

    def firstError(self):
        pass

    def __str__(self):
        return ''


## @class athenaLogFileReport
#  @brief Logfile suitable for scanning logfiles with an athena flavour, i.e.,
#  lines of the form "SERVICE  LOGLEVEL  MESSAGE"
class athenaLogFileReport(logFileReport):
    ## @brief Class constructor
    #  @param logfile Logfile (or list of logfiles) to scan
    #  @param substepName Name of the substep executor, that has requested this log scan
    #  @param msgLimit The number of messages in each category on which a
    def __init__(self, logfile, substepName=None, msgLimit=10, msgDetailLevel=stdLogLevels['ERROR'], ignoreList=None):
        if ignoreList:
            self._ignoreList = ignoreList
        else:
            self._ignoreList = ignorePatterns()

        ## @note This is the regular expression match for athena logfile lines
        # Match first strips off any HH:MM:SS prefix the transform has added, then
        # takes the next group of non-whitespace characters as the service, then
        # then matches from the list of known levels, then finally, ignores any last
        # pieces of whitespace prefix and takes the rest of the line as the message
        self._regExp = re.compile(r'(?P<service>[^\s]+\w)(.*)\s+(?P<level>' + '|'.join(stdLogLevels) + r')\s+(?P<message>.*)')

        self._metaPat = re.compile(r"MetaData:\s+(.*?)\s*=\s*(.*)$")
        self._metaData = {}
        self._substepName = substepName
        self._msgLimit = msgLimit

        self.resetReport()

        super(athenaLogFileReport, self).__init__(logfile, msgLimit, msgDetailLevel)

    ## Produce a python dictionary summary of the log file report for inclusion
    #  in the executor report
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
        for level in list(stdLogLevels) + ['UNKNOWN', 'IGNORED']:
            self._levelCounter[level] = 0

        self._errorDetails = {}
        for level in self._levelCounter:
            self._errorDetails[level] = []
            # Format:
            # List of dicts {'message': errMsg, 'firstLine': lineNo, 'count': N}
        self._dbbytes = 0
        self._dbtime  = 0.0

    ## Generally, a knowledge file consists of non-standard logging error/abnormal lines
    #  which are left out during log scan and could help diagnose job failures.
    def knowledgeFileHandler(self, knowledgefile):
        # load abnormal/error line(s) from the knowledge file(s)
        linesList = []
        fullName = trfUtils.findFile(os.environ['DATAPATH'], knowledgefile)
        if not fullName:
            msg.warning('Knowledge file {0} could not be found in DATAPATH'.format(knowledgefile))
        try:
            with open(fullName) as knowledgeFileHandle:
                msg.debug('Opened knowledge file {0} from here: {1}'.format(knowledgefile, fullName))

                for line in knowledgeFileHandle:
                    if line.startswith('#') or line == '' or line =='\n':
                        continue
                    line = line.rstrip('\n')
                    linesList.append(line)
        except OSError as e:
            msg.warning('Failed to open knowledge file {0}: {1}'.format(fullName, e))
        return linesList

    def scanLogFile(self, resetReport=False):
        nonStandardErrorsList = self.knowledgeFileHandler('nonStandardErrors.db')

        if resetReport:
            self.resetReport()

        for log in self._logfile:
            msg.debug('Now scanning logfile {0}'.format(log))
            seenNonStandardError = ''
            # N.B. Use the generator so that lines can be grabbed by subroutines, e.g., core dump svc reporter
            try:
                myGen = trfUtils.lineByLine(log, substepName=self._substepName)
            except IOError as e:
                msg.error('Failed to open transform logfile {0}: {1:s}'.format(log, e))
                # Return this as a small report
                self._levelCounter['ERROR'] = 1
                self._errorDetails['ERROR'] = {'message': str(e), 'firstLine': 0, 'count': 1}
                return
            for line, lineCounter in myGen:
                m = self._metaPat.search(line)
                if m is not None:
                    key, value = m.groups()
                    self._metaData[key] = value

                m = self._regExp.match(line)
                if m is None:
                    # We didn't manage to get a recognised standard line from the file
                    # But we can check for certain other interesting things, like core dumps
                    if 'Core dump from CoreDumpSvc' in line:
                        msg.warning('Detected CoreDumpSvc report - activating core dump svc grabber')
                        self.coreDumpSvcParser(log, myGen, line, lineCounter)
                        continue
                    # Add the G4 exceptipon parsers
                    if 'G4Exception-START' in line:
                        msg.warning('Detected G4 exception report - activating G4 exception grabber')
                        self.g4ExceptionParser(myGen, line, lineCounter, 40)
                        continue
                    if '*** G4Exception' in line:
                        msg.warning('Detected G4 9.4 exception report - activating G4 exception grabber')
                        self.g494ExceptionParser(myGen, line, lineCounter)
                        continue
                    # Add the python exception parser
                    if 'Shortened traceback (most recent user call last)' in line:
                        msg.warning('Detected python exception - activating python exception grabber')
                        self.pythonExceptionParser(myGen, line, lineCounter)
                        continue
                    # Add parser for missed bad_alloc
                    if 'terminate called after throwing an instance of \'std::bad_alloc\'' in line:
                        msg.warning('Detected bad_alloc!')
                        self.badAllocExceptionParser(myGen, line, lineCounter)
                        continue
                    # Parser for ROOT reporting a stale file handle (see ATLASG-448)
                    if 'SysError in <TFile::ReadBuffer>: error reading from file' in line:
                        self.rootSysErrorParser(myGen, line, lineCounter)
                        continue

                    if 'SysError in <TFile::WriteBuffer>' in line:
                        self.rootSysErrorParser(myGen, line, lineCounter)
                        continue
                    # Check if the line is among the non-standard logging errors from the knowledge file
                    if any(line in l for l in nonStandardErrorsList):
                        seenNonStandardError = line
                        continue

                    msg.debug('Non-standard line in %s: %s' % (log, line))
                    self._levelCounter['UNKNOWN'] += 1
                    continue

                # Line was matched successfully
                fields = {}
                for matchKey in ('service', 'level', 'message'):
                    fields[matchKey] = m.group(matchKey)
                msg.debug('Line parsed as: {0}'.format(fields))

                # Check this is not in our ignore list
                ignoreFlag = False
                for ignorePat in self._ignoreList.structuredPatterns:
                    serviceMatch = ignorePat['service'].match(fields['service'])
                    levelMatch = (ignorePat['level'] == "" or ignorePat['level'] == fields['level'])
                    messageMatch = ignorePat['message'].match(fields['message'])
                    if serviceMatch and levelMatch and messageMatch:
                        msg.info('Error message "{0}" was ignored at line {1} (structured match)'.format(line, lineCounter))
                        ignoreFlag = True
                        break
                if ignoreFlag is False:
                    for searchPat in self._ignoreList.searchPatterns:
                        if searchPat.search(line):
                            msg.info('Error message "{0}" was ignored at line {1} (search match)'.format(line, lineCounter))
                            ignoreFlag = True
                            break
                if ignoreFlag:
                    # Got an ignore - message this to a special IGNORED error
                    fields['level'] = 'IGNORED'
                else:
                    # Some special handling for specific errors (maybe generalise this if
                    # there end up being too many special cases)
                    # Upgrade bad_alloc to CATASTROPHE to allow for better automated handling of
                    # jobs that run out of memory
                    if 'std::bad_alloc' in fields['message']:
                        fields['level'] = 'CATASTROPHE'

                # concatenate the seen non-standard logging error to the FATAL
                if fields['level'] == 'FATAL':
                    if seenNonStandardError:
                        line += '; ' + seenNonStandardError

                # Count this error
                self._levelCounter[fields['level']] += 1

                # Record some error details
                # N.B. We record 'IGNORED' errors as these really should be flagged for fixing
                if fields['level'] == 'IGNORED' or stdLogLevels[fields['level']] >= self._msgDetails:
                    if self._levelCounter[fields['level']] <= self._msgLimit: 
                        detailsHandled = False
                        for seenError in self._errorDetails[fields['level']]:
                            if seenError['message'] == line:
                                seenError['count'] += 1
                                detailsHandled = True
                                break
                        if detailsHandled is False:
                            self._errorDetails[fields['level']].append({'message': line, 'firstLine': lineCounter, 'count': 1})
                    elif self._levelCounter[fields['level']] == self._msgLimit + 1:
                        msg.warning("Found message number {0} at level {1} - this and further messages will be supressed from the report".format(self._levelCounter[fields['level']], fields['level']))
                    else:
                        # Overcounted
                        pass
                if 'Total payload read from COOL' in fields['message']:
                    msg.debug("Found COOL payload information at line {0}".format(line))
                    a = re.match(r'(\D+)(?P<bytes>\d+)(\D+)(?P<time>\d+[.]?\d*)(\D+)', fields['message'])
                    self._dbbytes += int(a.group('bytes'))
                    self._dbtime  += float(a.group('time'))


    ## Return data volume and time spend to retrieve information from the database
    def dbMonitor(self):
        return {'bytes' : self._dbbytes, 'time' : self._dbtime} if self._dbbytes > 0 or self._dbtime > 0 else None

    ## Return the worst error found in the logfile (first error of the most serious type)
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

    ## @brief Attempt to suck a core dump report from the current logfile
    # This function scans logs in two different directions:
    # 1) downwards, to exctract information after CoreDrmpSvc; and 2) upwards, to find abnormal lines
    # @note: Current downwards scan just eats lines until a 'normal' line is seen.
    # There is a slight problem here in that the end of core dump trigger line will not get parsed
    # TODO: fix this (OTOH core dump is usually the very last thing and fatal!)
    def coreDumpSvcParser(self, log, lineGenerator, firstline, firstLineCount):
        abnormalLinesList = self.knowledgeFileHandler('coreDumpKnowledgeFile.db')
        _eventCounter = _run = _event = _currentAlgorithm = _functionLine = _currentFunction = None
        coreDumpReport = 'Core dump from CoreDumpSvc'
        linesToBeScaned = 50
        seenAbnormalLines = []
        abnormalLinesReport = {}
        lastNormalLineReport = {}
        coreDumpDetailsReport = {}

        for line, linecounter in lineGenerator:
            m = self._regExp.match(line)
            if m is None:
                if 'Caught signal 11(Segmentation fault)' in line:
                    coreDumpReport = 'Segmentation fault'
                if 'Event counter' in line:
                    _eventCounter = line

                #Lookup: 'EventID: [Run,Evt,Lumi,Time,BunchCross,DetMask] = [267599,7146597,1,1434123751:0,0,0x0,0x0,0x0]'
                if 'EventID' in line:
                    match = re.findall('\[.*?\]', line)
                    if match and match.__len__() >= 2:      # Assuming the line contains at-least one key-value pair.
                        brackets = "[]"
                        commaDelimer = ','
                        keys = (match[0].strip(brackets)).split(commaDelimer)
                        values = (match[1].strip(brackets)).split(commaDelimer)

                        if 'Run' in keys:
                            _run = 'Run: ' + values[keys.index('Run')]

                        if 'Evt' in keys:
                            _event = 'Evt: ' + values[keys.index('Evt')]

                if 'Current algorithm' in line:
                    _currentAlgorithm = line
                if '<signal handler called>' in line:
                    _functionLine = linecounter+1
                if _functionLine and linecounter is _functionLine:
                    if ' in ' in line:
                        _currentFunction = 'Current Function: ' + line.split(' in ')[1].split()[0]
                    else:
                        _currentFunction = 'Current Function: ' + line.split()[1]
            else:
                # Can this be done - we want to push the line back into the generator to be
                # reparsed in the normal way (might need to make the generator a class with the
                # __exec__ method supported (to get the line), so that we can then add a
                # pushback onto an internal FIFO stack
                # lineGenerator.pushback(line)
                break
        _eventCounter = 'Event counter: unknown' if not _eventCounter else _eventCounter
        _run = 'Run: unknown' if not _run else _run
        _event = 'Evt: unknown' if not _event else _event
        _currentAlgorithm = 'Current algorithm: unknown' if not _currentAlgorithm else _currentAlgorithm
        _currentFunction = 'Current Function: unknown' if not _currentFunction else _currentFunction
        coreDumpReport = '{0}: {1}; {2}; {3}; {4}; {5}'.format(coreDumpReport, _eventCounter, _run, _event, _currentAlgorithm, _currentFunction)

        ## look up for lines before core dump for "abnormal" and "last normal" line(s)

        #  make a list of last e.g. 50 lines before core dump
        #  A new "line generator" is required to give access to the upper lines
        linesList = []
        lineGen = trfUtils.lineByLine(log)
        for line, linecounter in lineGen:
            if linecounter in range(firstLineCount - linesToBeScaned, firstLineCount-1):
                linesList.append([linecounter, line])
            elif linecounter == firstLineCount:
                break

        for linecounter, line in reversed(linesList):
            if re.findall(r'|'.join(abnormalLinesList), line):
                seenLine = False
                for dic in seenAbnormalLines:
                    # count repetitions or similar (e.g. first 15 char) abnormal lines
                    if dic['message'] == line or dic['message'][0:15] == line[0:15]:
                        dic['count'] += 1
                        seenLine = True
                        break
                if seenLine is False:
                    seenAbnormalLines.append({'message': line, 'firstLine': linecounter, 'count': 1})
            else:
                if line != '':
                    lastNormalLineReport = {'message': line, 'firstLine': linecounter, 'count': 1}
                    break
                else:
                    continue

        # write the list of abnormal lines into a dictionary to report
        # The keys of each abnormal line are labeled by a number starting with 0
        # e.g. first abnormal line's keys are :{'meesage0', 'firstLine0', 'count0'}
        for a in range(len(seenAbnormalLines)):
            abnormalLinesReport.update({'message{0}'.format(a): seenAbnormalLines[a]['message'], 'firstLine{0}'.format(a): seenAbnormalLines[a]['firstLine'], 'count{0}'.format(a): seenAbnormalLines[a]['count']})
        coreDumpDetailsReport = {'abnormalLine(s) before CoreDump': abnormalLinesReport, 'lastNormalLine before CoreDump': lastNormalLineReport}

        # concatenate an extract of first seen abnormal line to the core dump message
        if len(seenAbnormalLines) > 0:
            coreDumpReport += '; Abnormal line(s) seen just before core dump: ' + seenAbnormalLines[0]['message'][0:30] + '...[truncated] ' + '(see the jobReport)'

        # Core dumps are always fatal...
        msg.debug('Identified core dump - adding to error detail report')
        self._levelCounter['FATAL'] += 1
        self._errorDetails['FATAL'].append({'moreDetails': coreDumpDetailsReport, 'message': coreDumpReport, 'firstLine': firstLineCount, 'count': 1})

    def g494ExceptionParser(self, lineGenerator, firstline, firstLineCount):
        g4Report = firstline
        g4lines = 1
        if not 'Aborting execution' in g4Report:
            for line, linecounter in lineGenerator:
                g4Report += os.linesep + line
                g4lines += 1
                # Test for the closing string
                if '*** ' in line:
                    break
                if g4lines >= 25:
                    msg.warning('G4 exception closing string not found within {0} log lines of line {1}'.format(g4lines, firstLineCount))
                    break

        # G4 exceptions can be fatal or they can be warnings...
        msg.debug('Identified G4 exception - adding to error detail report')
        if "just a warning" in g4Report:
            if self._levelCounter['WARNING'] <= self._msgLimit:
                self._levelCounter['WARNING'] += 1
                self._errorDetails['WARNING'].append({'message': g4Report, 'firstLine': firstLineCount, 'count': 1})
            elif self._levelCounter['WARNING'] == self._msgLimit + 1:
                msg.warning("Found message number {0} at level WARNING - this and further messages will be supressed from the report".format(self._levelCounter['WARNING']))
        else:
            self._levelCounter['FATAL'] += 1
            self._errorDetails['FATAL'].append({'message': g4Report, 'firstLine': firstLineCount, 'count': 1})

    def g4ExceptionParser(self, lineGenerator, firstline, firstLineCount, g4ExceptionLineDepth):
        g4Report = firstline
        g4lines = 1
        for line, linecounter in lineGenerator:
            g4Report += os.linesep + line
            g4lines += 1
            # Test for the closing string
            if 'G4Exception-END' in line:
                break
            if g4lines >= g4ExceptionLineDepth:
                msg.warning('G4 exception closing string not found within {0} log lines of line {1}'.format(g4lines, firstLineCount))
                break

        # G4 exceptions can be fatal or they can be warnings...
        msg.debug('Identified G4 exception - adding to error detail report')
        if "-------- WWWW -------" in g4Report:
            if self._levelCounter['WARNING'] <= self._msgLimit:
                self._levelCounter['WARNING'] += 1
                self._errorDetails['WARNING'].append({'message': g4Report, 'firstLine': firstLineCount, 'count': 1})
            elif self._levelCounter['WARNING'] == self._msgLimit + 1:
                msg.warning("Found message number {0} at level WARNING - this and further messages will be supressed from the report".format(self._levelCounter['WARNING'])) 
        else:
            self._levelCounter['FATAL'] += 1
            self._errorDetails['FATAL'].append({'message': g4Report, 'firstLine': firstLineCount, 'count': 1})

    def pythonExceptionParser(self, lineGenerator, firstline, firstLineCount):
        pythonExceptionReport = ""
        lastLine = firstline
        lastLine2 = firstline
        pythonErrorLine = firstLineCount
        pyLines = 1
        for line, linecounter in lineGenerator:
            if 'Py:Athena' in line and 'INFO leaving with code' in line:
                if len(lastLine)> 0:
                    pythonExceptionReport = lastLine
                    pythonErrorLine = linecounter-1
                else: # Sometimes there is a blank line after the exception
                    pythonExceptionReport = lastLine2
                    pythonErrorLine = linecounter-2
                break
            if pyLines >= 25:
                msg.warning('Could not identify python exception correctly scanning {0} log lines after line {1}'.format(pyLines, firstLineCount))
                pythonExceptionReport = "Unable to identify specific exception"
                pythonErrorLine = firstLineCount
                break
            lastLine2 = lastLine
            lastLine = line
            pyLines += 1

        msg.debug('Identified python exception - adding to error detail report')
        self._levelCounter['FATAL'] += 1
        self._errorDetails['FATAL'].append({'message': pythonExceptionReport, 'firstLine': pythonErrorLine, 'count': 1})

    def badAllocExceptionParser(self, lineGenerator, firstline, firstLineCount):
        badAllocExceptionReport = 'terminate after \'std::bad_alloc\'.'

        msg.debug('Identified bad_alloc - adding to error detail report')
        self._levelCounter['CATASTROPHE'] += 1
        self._errorDetails['CATASTROPHE'].append({'message': badAllocExceptionReport, 'firstLine': firstLineCount, 'count': 1})

    def rootSysErrorParser(self, lineGenerator, firstline, firstLineCount):
        msg.debug('Identified ROOT IO problem - adding to error detail report')
        self._levelCounter['FATAL'] += 1
        self._errorDetails['FATAL'].append({'message': firstline, 'firstLine': firstLineCount, 'count': 1})

    def __str__(self):
        return str(self._levelCounter) + str(self._errorDetails)


class scriptLogFileReport(logFileReport):
    def __init__(self, logfile=None, msgLimit=200, msgDetailLevel=stdLogLevels['ERROR']):
        self._levelCounter = {}
        self._errorDetails = {}
        self.resetReport()
        super(scriptLogFileReport, self).__init__(logfile, msgLimit, msgDetailLevel)

    def resetReport(self):
        self._levelCounter.clear()
        for level in list(stdLogLevels) + ['UNKNOWN', 'IGNORED']:
            self._levelCounter[level] = 0

        self._errorDetails.clear()
        for level in self._levelCounter:  # List of dicts {'message': errMsg, 'firstLine': lineNo, 'count': N}
            self._errorDetails[level] = []

    def scanLogFile(self, resetReport=False):
        if resetReport:
            self.resetReport()

        for log in self._logfile:
            msg.info('Scanning logfile {0}'.format(log))
            try:
                myGen = trfUtils.lineByLine(log)
            except IOError as e:
                msg.error('Failed to open transform logfile {0}: {1:s}'.format(log, e))
                # Return this as a small report
                self._levelCounter['ERROR'] = 1
                self._errorDetails['ERROR'] = {'message': str(e), 'firstLine': 0, 'count': 1}
                return

            for line, lineCounter in myGen:
                # TODO: This implementation currently only scans for Root SysErrors.
                # General solution would be a have common error parser for all system level
                # errors those all also handled by AthenaLogFileReport.
                if line.__contains__('SysError in <TFile::ReadBuffer>') or \
                   line.__contains__('SysError in <TFile::WriteBuffer>'):
                    self.rootSysErrorParser(line, lineCounter)

    # Return the worst error found in the logfile (first error of the most serious type)
    def worstError(self):
        worstlevelName = 'DEBUG'
        worstLevel = stdLogLevels[worstlevelName]
        for levelName, count in iteritems(self._levelCounter):
            if count > 0 and stdLogLevels.get(levelName, 0) > worstLevel:
                worstlevelName = levelName
                worstLevel = stdLogLevels[levelName]

        if len(self._errorDetails[worstlevelName]) > 0:
            firstError = self._errorDetails[worstlevelName][0]
        else:
            firstError = None

        return {'level': worstlevelName, 'nLevel': worstLevel, 'firstError': firstError}

    def __str__(self):
        return str(self._levelCounter) + str(self._errorDetails)

    def rootSysErrorParser(self, line, lineCounter):
        msg.debug('Identified ROOT IO problem - adding to error detail report')
        self._levelCounter['FATAL'] += 1
        self._errorDetails['FATAL'].append({'message': line, 'firstLine': lineCounter, 'count': 1})



