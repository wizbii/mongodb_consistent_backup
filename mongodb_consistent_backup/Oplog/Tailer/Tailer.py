import bson
import os
import logging

from bson.timestamp import Timestamp
from multiprocessing import Event, Manager
from time import time, sleep

from TailThread import TailThread
from mongodb_consistent_backup.Common import parse_method, MongoUri, Timer, DB
from mongodb_consistent_backup.Errors import OperationError
from mongodb_consistent_backup.Oplog import OplogState


class Tailer:
    def __init__(self, manager, config, replsets, base_dir, status_secs=15):
	self.manager     = manager
        self.config      = config
        self.replsets    = replsets
        self.base_dir    = base_dir
        self.backup_name = self.config.name
        self.user        = self.config.user
        self.password    = self.config.password
        self.authdb      = self.config.authdb
        self.status_secs = status_secs

        self.timer    = Timer()
        self.shards   = {}
        self._summary = {}

    def compression(self, method=None):
        if method:
            self.config.oplog.compression = parse_method(method)
            logging.info("Setting oplog compression method to: %s" % self.config.oplog.compression)
        return parse_method(self.config.oplog.compression)

    def do_gzip(self):
        if self.compression() == 'gzip':
            return True
        return False

    def summary(self):
        return self._summary

    def prepare_oplog_files(self, shard_name):
        oplog_dir = "%s/%s" % (self.base_dir, shard_name)
        if not os.path.isdir(oplog_dir):
            os.makedirs(oplog_dir)
        oplog_file = "%s/oplog-tailed.bson" % oplog_dir
        oplog_state_file = "%s/state.bson" % oplog_dir
        return oplog_file, oplog_state_file

    def run(self):
        logging.info("Starting oplog tailers on all replica sets (options: gzip=%s, status_secs=%i)" % (self.do_gzip(), self.status_secs))
        self.timer.start()
        for shard in self.replsets:
            stop        = Event()
            secondary   = self.replsets[shard].find_secondary()
            mongo_uri   = secondary['uri']
            shard_name  = mongo_uri.replset

            oplog_file, oplog_state_file = self.prepare_oplog_files(shard_name)
            oplog_state = OplogState(self.manager, mongo_uri, oplog_file)
            thread = TailThread(
                stop,
                mongo_uri,
                self.config,
                oplog_file,
                oplog_state,
                self.do_gzip(),
                self.status_secs
            )
            self.shards[shard] = {
                'stop':   stop,
                'thread': thread,
                'state':  oplog_state,
                'state_file': oplog_state_file
            }
            self.shards[shard]['thread'].start()
            while not oplog_state.get('running'):
                sleep(0.5)

    def stop(self, kill=False, sleep_secs=2):
        logging.info("Stopping all oplog tailers")
        for shard in self.shards:
            replset    = self.replsets[shard]
            state      = self.shards[shard]['state']
            state_file = self.shards[shard]['state_file']
            stop       = self.shards[shard]['stop']
            thread     = self.shards[shard]['thread']

            try:
                uri = MongoUri(state.get('uri'))
            except Exception, e:
                raise OperationError(e)

            if not kill:
                # get current optime of replset primary to use a stop position
                try:
                    timestamp = replset.primary_optime(True, True)
                except:
                    logging.warning("Could not get current optime from PRIMARY! Using now as a stop time")
                    timestamp = Timestamp(int(time()), 0)
    
                # wait for replication to get in sync
                while state.get('last_ts') and state.get('last_ts') < timestamp:
                    logging.info('Waiting for %s tailer to reach ts: %s, currrent: %s' % (uri, timestamp, state.get('last_ts')))
                    sleep(sleep_secs)

            # set thread stop event
            self.shards[shard]['stop'].set()
            if kill:
                thread.terminate()
            sleep(sleep_secs)

            # wait for thread to stop
            while thread.is_alive():
                logging.info('Waiting for tailer %s to stop' % uri)
                sleep(sleep_secs)

            # gather state info
            self._summary[shard] = state.get().copy()

        self.timer.stop()
        logging.info("Oplog tailing completed in %.2f seconds" % self.timer.duration())

        return self._summary

    def close(self):
	for shard in self.shards:
	    try:
	        self.shards[shard]['stop'].set()
		thread = self.shards[shard]['thread']
		thread.terminate()
		while thread.is_alive():
		    sleep(1)
	    except Exception, e:
  	        logging.error("Cannot stop thread: %s" % e)
