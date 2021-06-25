* [Introduction](#introduction)
* [The Framework](#the-Framework)
  + [Collecting and matching component](#collecting-and-matching-component)
  + [Storage and indexing component](#storage-and-indexing-component)
  + [Message analysis and reporting component](#message-analysis-and-reporting-component)
    + [Validation module](#validation-module)
    + [Logger module](#logger-module)
    + [Reports module](#reports-module)
  + [Main script](#main-script)
* [Image construction](#image-construction)
* [Image repository](#image-repository)
* [Testing locally with Docker](#testing-locally-with-Docker)
* [Testing with Singularity in a grid environment](#testing-with-Singularity-in-a-grid-environment)

# Introduction

Our goal is to develop a framework for the analysis of logs produced in user jobs, which can be easily deployed as an additional Docker layer on top of pre-existing containers used to execute a given payload. The requirements for selecting the components of a containerized log-analysis framework can be summarized as follows:
- The framework should have the least number of components
- The components should be light-weight, open-source projects widely used in industry
- Ease of process configuration and management. Unprivileged containers typically lack init systems, which require kernel functionality. It is important to avoid components that have complicated init-scripts handled by systemd or SysVinit.

Our log-management framework consists of only two main components, fluentd and Elasticsearch, which are popular open-source projects with large support communities and simple configurations. A third light-weight component, supervisord, is added as a process manager started by the container's entry-point script. This complies with the design model for Docker containers as hosting a single service/process per container.

# The Framework
The log-analysis framework consists of a processing pipeline that ingests input log files produced by the container's main payload and outputs structured data based on regular patterns identified in the records. This structured data is further processed in a python layer to extract useful information relevant to the job's outcome. The main components in this pipeline :

## Collecting and matching component 
Fluentd is a cross platform open-source data collection software project written in ruby (version >=2.4 is required). Fluentd's builtin input plugin (in_tail) is used to read lines from log files. The input plugin “in_tail” works as the common tail command, but it is configured in this case to read from the head of the file and can thus be used to read the input log file. The lines in the log are then parsed using regular expressions (ruby regexp) by fluentd's matching feature, which creates a stream of matched structured data (relative to the regular expression) and a stream of unmatched messages. Both streams are then stored in separate Elasticsearch indexes via a dedicated output plugin using a RESTful interface. Currently, the regular expressions in fluentd's configuration file (fluent.conf) mine the logs for patterns typically found in a wide spectrum of logs, mainly consisting of service, level, message fields. Unstructured messages are stored as a single field (‘line’).

```
<match log>
  @type rewrite_tag_filter
  <rule>
    key line
    pattern /(?<logtime>[^\s]*)\s+(?<service>[^\s]+\w)(.*)\s+(?<level>INFO|CRITICAL|WARNING|VERBOSE|ERROR|DEBUG|FATAL|CATASTROPHE)\s+(?<message>.*)/
    tag log.matched
  </rule>
  <rule>
    key line
    pattern /(?<logtime>[^\s]*)\s+(?<service>[^\s]+\w)(.*)\s+(?<level>INFO|CRITICAL|WARNING|VERBOSE|ERROR|DEBUG|FATAL|CATASTROPHE)\s+(?<message>.*)/
    tag log.unmatched
    invert true
  </rule>
</match>
```


## Storage and indexing component
Elasticsearch is a distributed full-text search engine based on the Lucene library. Elasticsearch is our choice for storage of the data streams processed by fluentd via a third-party output plugin (fluent-plugin-elasticsearch). The output streams are stored as Elasticsearch indexes, which can be queried using the search engine's full Query DSL (Domain Specific Language) based on JSON. An alternative to Elasticsearch is to store the data in JSON-formatted files. However, an additional software layer would need to be developed to provided the searching capability.

## Message analysis and reporting component
This component consists of a python package containing classes and methods for defining queries to Elasticsearch and generating reports in JSON format based on the results. This python software layer consists of three components:

### Validation module
Class definition and methods for implementing queries to Elasticsearch using the python Elasticsearch client, a thin wrapper around Elasticsearch’s REST API. Currently, only the processing of structured data is fully implemented, and base methods for processing unstructured data are only provided as placeholders.

The results of the query can be filtered and stored in an internal dictionary accessed through Validation.python, which returns a python dictionary summary of the filtered query. If Validation.\_msgDetails='WARNING' (default), all structured data records found with logging severity level equal to WARNING or higher are returned. Additionally, it provides two methods that perform simple analyses on the data returned by the queries:
- Validation.worstError: returns the first record found with highest logging severity level
- Validation.firstError: returns the first record found with ERROR logging severity level

Unstructured messages can be be matched to user defined patterns using regular expressions. These example messages can be added to an existing "knowledge" file (nonStandardErrors.db) listing common error messages, e.g., ‘std::bad_alloc’
```
{"line": "terminate called after throwing an instance of std::bad_alloc", "errorHandler": "badAllocExceptionParser"}
{"line": "15:54:17 InDetJobProperties::setupDefaults():  jobproperties.Beam.beamType() is collisions bunch spacing is 25", "errorHandler": "PrintExceptionParser"}
```

### Logger module
Class definition for configuring the package's own logging. Additionally, structured messages are ordered using the object Logger.stdLogLevels defined in this class. A common use case is implemented based on the logging severity levels: FATAL, CRITICAL, ERROR, WARNING, INFO, VERBOSE, DEBUG

### Reports module
Class definition and methods for generating a job report based on the search engine's query results and the subsequent data analysis performed by Validation.firstError and Validation.worstError. Currently only JSON formatted reports are implemented (Reports.writeJSONReport), but other formats can be later implemented such as pickle, text and xml

## Main script
This is the main script for log-analisis steering kept at scripts/scanner.py. It creates instances of classes from the Validation and Reports modules to implement queries and produce a report, for example:

```
search=userLogFileReport('fluentd.log.matched', {"query": {"bool" : {"should" : [{"match" : {"level" : "FATAL" }}, {"match" : {"level" : "CRITICAL" }}, {"match" : {"level" : "ERROR" }}, {"match" : {"level" : "WARNING" }}]}}}, 100)
jobReport=trfJobReport(search)
jobReport.writeJSONReport(filename='jobReport.json')
```
The query DSL body used in the search could eventually be generated by a module using input from the user. This generates a JSON file containing all messages with logging severity level = WARNING, ERROR, FATAL or CRITICAL. It also specifies the first message with FATAL level (worstError), and first message with ERROR level (firstError)

# Image construction
The containerized framework is currently deployed as Docker images. The images can be built using the Dockerfile contained in this repository using the following commands:

```
git clone https://github.com/erum-data-idt/LogAnalysisFramework.git
cd LogAnalysisFramework/
docker build -t <Docker Hub repository user>/<repository name>:tag .
```
Note the "." at the end of the build command, this points to the Dockerfile in the current folder. A CentOS 7 base image is used to install the framework, which comes with Python version 2.7.5. Given that support for Python 2 ended in January 2021, a migration to Python 3 is needed, either by direct installation or via virtual environments.

# Image repository
An image generated using the steps listed above is maintained at Docker Hub and can be pulled using the following command:
```
docker pull marcvog/fluentd:latest
```

# Testing locally with Docker
```
docker run -d --name fluent marcvog/fluentd:latest
docker exec -it fluent /bin/bash
export DATAPATH=/root # wait a couple of minutes!
python scanner.py
```

# Testing with Singularity in a grid environment

Due to security concerns associated to the Docker daemon, most containerized user jobs running in grid environments use Singularity containers. Given that Docker supports a friendlier set of tools for image creation and configuration, images are preferentially built using Docker and automatically transformed to singularity when pulled from the grid. Typically in a grid environment, permissions are changed when a writable singularity sandbox is created. The user who runs the image owns all files and folders and executes all the scripts and services. 

The log-analysis framework can be added to any pre-existing container that runs a log file producing payload. In this case, the base image to the framework needs to be updated to the one running the payload. This is done during the build process

```
docker build -t <Docker Hub repository user>/<repository name>:tag --build-arg BASEIMAGE=<payload base image> .
```
Next, the location of the log file needs to be specified in the input plugin block in fluent.conf
```
<source>
  @type tail
  path /path/to/some.log
  tag log
  read_from_head true
  pos_file /var/log/fluentd/tail.log.pos
  <parse>
    @type none
    message_key line
  </parse>
</source>
```
Finally, the following sequence of commands needs to be added to the original script or command executing the payload
```
unset PYTHONPATH; unset PYTHONHOME; export PATH=/usr/sue/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH; supervisord -c /usr/local/loganalysis/supervisord/etc/ supervisord.conf; sleep 5m; export DATAPATH=/usr/local/loganalysis/fluentd; python /usr/local/loganalysis/fluentd/scanner.py
```
It is only necessary to reset the python path if the payload comes with its own python installation. This can probably be better handled with virtual python environments.
