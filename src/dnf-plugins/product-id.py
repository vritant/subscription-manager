#
# Copyright (c) 2015 Red Hat, Inc.
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

import sys
import collections

from dnfpluginscore import _, logger
import dnf
import librepo

sys.path.append('/usr/share/rhsm')

from subscription_manager import logutil
from subscription_manager import productid
from subscription_manager.utils import chroot
from subscription_manager.injectioninit import init_dep_injection


class PackageManager(object):
    _enabled = []
    _active = []
    _repos_with_errors = collections.defaultdict(list)

    @property
    def enabled(self):
        return self._enabled

    @property
    def active(self):
        return self._active

    @property
    def repos_with_errors(self):
        return self._repos_with_errors


class DnfPackageManager(PackageManager):
    def __init__(self, base):
        self.base = base

    def _download_productid(self, repo):
        with dnf.util.tmpdir() as tmpdir:
            handle = repo._handle_new_remote(tmpdir)
            handle.setopt(librepo.LRO_PROGRESSCB, None)
            handle.setopt(librepo.LRO_YUMDLIST, [productid.PRODUCTID])
            res = handle.perform()
        return res.yum_repo.get(productid.PRODUCTID, None)

    def get_enabled(self):
        """find repos that are enabled"""
        lst = []
        enabled = self.base.repos.iter_enabled()

        # skip repo's that we don't have productid info for...
        for repo in enabled:
            try:
                # We have to look in all repos for productids, not just
                # the ones we create, or anaconda doesn't install it.
                fn = self._download_productid(repo)
                if not fn:
                    self._repos_with_errors[repo.id].append(repo.id)
                    continue

                # Make _get_cert raise an exception
                cert = productid._get_cert(fn)
                if cert is None:
                    # and then append it to the errors for that repo
                    continue
                lst.append((cert, repo.id))
            except Exception, e:
                log.warn("Error loading productid metadata for %s." % repo)
                log.exception(e)
                self._repos_with_errors[repo.id].append(e)

        if self.repos_with_errors:
            log.debug("Unable to load productid metadata for repos: %s",
                      self.repos_with_errors)
        return lst

    # find the list of repo's that provide packages that
    # are actually installed.
    def get_active(self):
        """find yum repos that have packages installed"""
        # installed packages
        installed_na = self.base.sack.query().installed().na_dict()
        # available version of installed
        avail_pkgs = self.base.sack.query().available().filter(name=[k[0] for k in installed_na.keys()])

        active = set()
        for p in avail_pkgs:
            if (p.name, p.arch) in installed_na:
                active.add(p.repoid)

        return active

    def check_version_tracks_repos(self):
        return True


class ProductId(dnf.Plugin):
    name = 'product-id'

    def __init__(self, base, cli):
        super(ProductId, self).__init__(base, cli)
        self.base = base
        self.cli = cli

    def transaction(self):
        """
        Update product ID certificates.
        """
        if len(self.base.transaction) == 0:
            # nothing to update after empty transaction
            return

        try:
            init_dep_injection()
        except ImportError as e:
            logger.error(str(e))
            return

        logutil.init_logger_for_yum()
        chroot(self.base.conf.installroot)
        try:
            pm = productid.ProductManager()
            dnfpm = DnfPackageManager(self.base)
            pm.update(package_manager=dnfpm)
            logger.info(_('Installed products updated.'))
        except Exception as e:
            logger.error(str(e))

