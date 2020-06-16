# Make the base image configurable.
ARG BASEIMAGE=centos:7
FROM ${BASEIMAGE}

USER root
WORKDIR /root

RUN yum install -y make gcc openssl openssl-devel zlib-devel wget ntp epel-release which && \
    yum clean all

RUN cd /tmp && \
    wget https://cache.ruby-lang.org/pub/ruby/2.6/ruby-2.6.6.tar.gz && \
    gzip -d ruby-2.6.6.tar.gz && \
    tar -xf ruby-2.6.6.tar && \
    rm -f ruby-2.6.6.tar && \
    cd ruby-2.6.6 && \
    ./configure && \
    make && \
    make install

# Install fluentd
RUN yum install -y rubygems
RUN gem install fluentd --no-document
RUN fluentd --setup /etc/fluent
COPY fluent.conf /etc/fluent/fluent.conf

# Install elasticsearch
COPY elasticsearch.repo /etc/yum.repos.d/elasticsearch.repo
RUN rpm --import https://artifacts.elastic.co/GPG-KEY-elasticsearch
RUN yum install -y --enablerepo=elasticsearch elasticsearch

# Install supervisord
RUN yum install -y python-pip
RUN python -m pip install --upgrade pip
RUN pip install supervisor

COPY supervisord.conf /etc/supervisord.conf
RUN yum install -y mlocate

CMD ["supervisord", "-c", "/etc/supervisord.conf"]
