#
# Copyright (c) 2013 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import logging
import os

from rhsm.certificate import create_from_pem
from rhsm.config import initConfig
from subscription_manager.certdirectory import Path

CFG = initConfig()

log = logging.getLogger('rhsm-app.' + __name__)


class ConsumerIdentityData(object):
    consumer = None
    uuid = None
    name = None
    serial = None


class ConsumerIdentity(object):
    """Consumer info and certificate information.

    Includes helpers for reading/writing consumer identity certificates
    from disk."""

    PATH = CFG.get('rhsm', 'consumerCertDir')
    KEY = 'key.pem'
    CERT = 'cert.pem'

    @classmethod
    def keypath(cls):
        return Path.join(cls.PATH, cls.KEY)

    @classmethod
    def certpath(cls):
        return Path.join(cls.PATH, cls.CERT)

    @classmethod
    def read(cls):
        f = open(cls.keypath())
        key = f.read()
        f.close()
        f = open(cls.certpath())
        cert = f.read()
        f.close()
        return ConsumerIdentity(key, cert)

    @classmethod
    def exists(cls):
        return (os.path.exists(cls.keypath()) and
                os.path.exists(cls.certpath()))

    @classmethod
    def existsAndValid(cls):
        if cls.exists():
            try:
                cls.read()
                return True
            except Exception, e:
                log.warn('possible certificate corruption')
                log.error(e)
        return False

    def __init__(self, keystring, certstring):
        self.key = keystring
        # TODO: bad variables, cert should be the certificate object, x509 is
        # used elsewhere for the m2crypto object of the same name.
        self.cert = certstring
        self.x509 = create_from_pem(certstring)

    @property
    def uuid(self):
        subject = self.x509.subject
        return subject.get('CN')

    @property
    def name(self):
        altName = self.x509.alt_name
        # must account for old format and new
        return altName.replace("DirName:/CN=", "").replace("URI:CN=", "")

    @property
    def serial(self):
        return self.x509.serial

    # TODO: we're using a Certificate which has it's own write/delete, no idea
    # why this landed in a parallel disjoint class wrapping the actual cert.
    def write(self):
        from subscription_manager import managerlib
        self.__mkdir()
        f = open(self.keypath(), 'w')
        f.write(self.key)
        f.close()
        os.chmod(self.keypath(), managerlib.ID_CERT_PERMS)
        f = open(self.certpath(), 'w')
        f.write(self.cert)
        f.close()
        os.chmod(self.certpath(), managerlib.ID_CERT_PERMS)

    def delete(self):
        path = self.keypath()
        if os.path.exists(path):
            os.unlink(path)
        path = self.certpath()
        if os.path.exists(path):
            os.unlink(path)

    def __mkdir(self):
        path = Path.abs(self.PATH)
        if not os.path.exists(path):
            os.mkdir(path)

    def __str__(self):
        return 'consumer: name="%s", uuid=%s' % \
            (self.name,
             self.uuid)


class Identity(object):
    """Wrapper for sharing consumer identity without constant reloading."""
    def __init__(self):
        self._consumer = None
        self.reload()

    def reload(self):
        """Check for consumer certificate on disk and update our info accordingly."""
        log.debug("Loading consumer info from identity certificates.")
        try:
            self._consumer = self._get_consumer_identity()
            if not self._consumer:
                self.unset()
                return
            self.name = self._consumer.name
            self.uuid = self._consumer.uuid
            self.serial = self._consumer.serial

        # NOTE: shouldn't catch the global exception here, but that's what
        # existsAndValid did, so this is better.
        except Exception, e:
            log.debug("Reload of consumer identity cert %s raised an exception with msg: %s",
                      ConsumerIdentity.certpath(), e)
            self.consumer = None
            self.name = None
            self.uuid = None
            self.unset()

    def unset(self):
        self._consumer = None
        self.name = None
        self.uuid = None
        self.serial = None

    def _get_consumer_identity(self):
        # FIXME: wrap in exceptions, catch IOErrors etc, raise anything else
        return ConsumerIdentity.read()

    # this name is weird, since Certificate.is_valid actually checks the data
    # and this is a thin wrapper
    def is_valid(self):
        if self._consumer:
            return self.uuid is not None

    def get_uuid(self):
        if self._consumer:
            return self._consumer.uuid
        return None

    def set_uuid(self, value):
        if self._consumer:
            self._consumer.uuid = value
        assert('huh')

    def delete_uuid(self):
        if self._consumer:
            del self._consumer.uuid
    # The 2.4 way...
    uuid = property(get_uuid, set_uuid, delete_uuid)

    def __str__(self):
        return "<%s, name=%s, uuid=%s, consumer=%s>" % \
                (self.__class__.__name__,
                self.name, self.uuid, self._consumer)
