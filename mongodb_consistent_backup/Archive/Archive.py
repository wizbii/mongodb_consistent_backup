import logging

from mongodb_consistent_backup.Archive.Tar import Tar
from mongodb_consistent_backup.Common import Timer, config_to_string, parse_method
from mongodb_consistent_backup.Errors import Error, OperationError


class Archive:
    def __init__(self, config, backup_dir):
        self.config     = config
        self.backup_dir = backup_dir

        self.method    = None
        self._archiver = None
        self.timer     = Timer()
        self.init()

    def init(self):
        archive_method = self.config.archive.method
        if not archive_method or parse_method(archive_method) == "none":
            logging.info("Archiving disabled, skipping")
        else:
            self.method = parse_method(archive_method)
            logging.info("Using archiving method: %s" % self.method)
            try:
                self._archiver = globals()[self.method.capitalize()](
                    self.config,
                    self.backup_dir
                )
            except LookupError, e:
                raise OperationError('No archiving method: %s' % self.method)
            except Exception, e:
                raise Error("Problem performing %s! Error: %s" % (self.method, e))

    def compression(self, method=None):
        if self._archiver:
            return self._archiver.compression(method)

    def threads(self, threads=None):
        if self._archiver:
            return self._archiver.threads(threads)

    def archive(self):
        if self._archiver:
            config_string = config_to_string(self.config.archive[self.method])
            logging.info("Archiving with method: %s (options: %s)" % (self.method, config_string))
            self.timer.start()

            self._archiver.run()

            self.timer.stop()
            logging.info("Archiving completed in %.2f seconds" % self.timer.duration())

    def close(self):
        if self._archiver:
            return self._archiver.close()
