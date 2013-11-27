#!/usr/bin/python
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

import os
import logging
log = logging.getLogger('rhsm-app.' + __name__)

from collections import namedtuple

import rhsm.config
import subscription_manager.injection as inj
from subscription_manager.certlib import CertLib
from subscription_manager import repolib
from subscription_manager import utils

from yum.yumRepo import YumRepository

ALLOWED_CONTENT_TYPES = repolib.ALLOWED_CONTENT_TYPES


class UpgradeBase(object):
    def __init__(self, conduit):
        self.conduit = conduit
        self.identity = inj.require(inj.IDENTITY)
        if not self.identity.is_valid():
            raise ValueError('No consumer identity found.')
        self.cp = self._create_cp()

    def _create_cp(self):
        try:
            cp_provider = inj.require(inj.CP_PROVIDER)
            self.cp = cp_provider.get_consumer_auth_cp()
        except Exception:
            log.exception('Could not connect to subscription management service')
            raise


class EntitlementRefresher(UpgradeBase):
    def __init__(self, conduit):
        super(EntitlementRefresher, self).__init__(conduit)

    def refresh(self):
        # Update any entitlement certificates
        CertLib(uep=self.cp).update()
        inj.require(inj.CERT_SORTER).force_cert_check()


class RepoBuilder(UpgradeBase):
    BaseContentInfo = namedtuple('BaseContentInfo', ['content', 'cert'])

    class ContentInfo(BaseContentInfo):
        """Multiple entitlement certificates can have the same content, and we need
        to reference the entitlement certificate when we build the RhsmRepo object.
        This class is a simple container to hold both the Content and EntitlementCertificate
        but we define __eq__ and __hash__ based on the Content object so that when we
        place ContentInfo objects into a set, we won't have any collisions on Content.
        """

        def __eq__(self, other):
            return isinstance(other, self.__class__) and self.content == other.content

        def __hash__(self):
            return hash(self.content)

    def __init__(self, conduit):
        super(RepoBuilder, self).__init__(conduit)
        self.config = rhsm.config.initConfig()

    def _matching_content(self, tags):
        ent_dir = inj.require(inj.ENT_DIR)
        certs = ent_dir.list_valid()
        content_set = set()

        for cert in certs:
            if not cert.content:
                continue

            for content in cert.content:
                if content.content_type not in ALLOWED_CONTENT_TYPES:
                    log.debug("Content type %s is not allowed. Skipping content %s" %
                            (content.content_type, content.label))
                    continue
                content_matches = all(x in tags for x in content.required_tags)
                if content_matches:
                    content_set.add(self.ContentInfo(content, cert))
        return content_set

    def build_repos(self, tags):
        return [RhsmRepo(content_info, self.config) for content_info in self._matching_content(tags)]


class RhsmRepo(YumRepository):
    def __init__(self, content_info, config):
        content = content_info.content
        cert = content_info.cert
        self.rhsm_config = config

        super(RhsmRepo, self).__init__(content.label)

        self.name = content.name
        self.sslcacert = self.rhsm_config.get('rhsm', 'repo_ca_cert')
        self.sslcientcert = cert.path
        self.sslclientkey = self._get_key_path(cert)
        self.metadata_expire = content.metadata_expire

        self.proxy = self._get_proxy()
        self.proxy_username = self.rhsm_config.get('server', 'proxy_user')
        self.proxy_password = self.rhsm_config.get('server', 'proxy_password')

        baseurl = self.rhsm_config.get('rhsm', 'baseurl')
        if content.gpg:
            self.gpgkey = [utils.yum_url_join(baseurl, content.gpg)]
        else:
            self.gpgkey = []
            self.gpgcheck = False

        if content.enabled:
            self.enable()
        else:
            self.disable()

    def _get_key_path(self, cert):
        """
        Returns the full path to the cert's key.pem.
        """
        dir_path, cert_filename = os.path.split(cert.path)
        key_filename = "%s-key.%s" % tuple(cert_filename.split("."))
        key_path = os.path.join(dir_path, key_filename)
        return key_path

    def _get_proxy(self):
        proxy = ""
        proxy_host = self.rhsm_config.get('server', 'proxy_hostname')
        proxy_port = self.rhsm_config.get('server', 'proxy_port')
        if proxy_host != "":
            proxy = "https://%s" % proxy_host
            if proxy_port != "":
                proxy = "%s:%s" % (proxy, proxy_port)
        return proxy


class PostInstaller(UpgradeBase):
    def __init__(self, conduit):
        super(PostInstaller, self).__init__(conduit)

    def remove_release(self):
        consumer = self.cp.getConsumer(self.identity.uuid)
        if 'releaseVer' in consumer:
            self.cp.updateConsumer(self.identity.uuid, release="")
