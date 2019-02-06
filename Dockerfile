FROM centos:centos7
MAINTAINER Tim Vaillancourt <tim.vaillancourt@percona.com>

RUN yum install -y https://repo.percona.com/yum/percona-release-latest.noarch.rpm && \
    percona-release enable psmdb-40 release && \
    yum install -y percona-server-mongodb-tools && \
    yum clean all

ADD build/rpm/RPMS/x86_64/mongodb_consistent_backup*.el7.x86_64.rpm /
RUN yum localinstall -y /mongodb_consistent_backup*.el7.x86_64.rpm && \
	yum clean all && rm -f /mongodb_consistent_backup*.el7.x86_64.rpm

USER mongodb_consistent_backup
ENTRYPOINT ["mongodb-consistent-backup"]
CMD ["--help"]
