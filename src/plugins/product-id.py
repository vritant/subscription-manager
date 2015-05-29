#
# Copyright (c) 2010 Red Hat, Inc.
#
# Authors: Jeff Ortel <jortel@redhat.com>
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

import collections
import sys
import logging

from yum.plugins import TYPE_CORE
import yum

sys.path.append('/usr/share/rhsm')


from subscription_manager import logutil
from subscription_manager import productid
from subscription_manager.utils import chroot
from subscription_manager.injectioninit import init_dep_injection

requires_api_version = '2.6'
plugin_type = (TYPE_CORE,)


class YumPackageManager(object):
    def __init__(self, base):
        self.base = base
        self.log = logging.getLogger('rhsm-app.' + __name__ +
                                     self.__class__.__name__)
        self.repos_with_errors = collections.defaultdict(list)

    def get_enabled(self):
        """find yum repos that are enabled"""
        lst = []
        enabled = self.base.repos.listEnabled()

        # We have to look in all repos for productids, not just
        # the ones we create, or anaconda doesn't install it.
        # skip repo's that we don't have productid info for...
        for repo in enabled:
            try:
                fn = repo.retrieveMD(productid.PRODUCTID)
                cert = productid._get_cert(fn)
                lst.append((cert, repo.id))
            except yum.Errors.RepoMDError, e:
                # This is the normal path for non RHSM repos, so
                # we don't log errors.
                self.repos_with_errors[repo.id].append(e)
            except Exception, e:
                self.log.warn("Error loading productid metadata for %s." % repo)
                self.log.exception(e)
                self.repos_with_errors[repo.id].append(e)

        if self.repos_with_errors:
            self.log.debug("Unable to load productid metadata for repos: %s",
                           self.repos_with_errors.keys())
        return lst

    # find the list of repo's that provide packages that
    # are actually installed.
    def get_active(self):
        """find yum repos that have packages installed"""

        active = set([])

        # If a package is in a enabled and 'protected' repo

        # This searches all the package sacks in this yum instances
        # package sack, aka all the enabled repos
        packages = self.base.pkgSack.returnPackages()

        for p in packages:
            repo = p.repoid
            # if a pkg is in multiple repo's, this will consider
            # all the repo's with the pkg "active".
            # NOTE: if a package is from a disabled repo, we won't
            # find it with this, because 'packages' won't include it.
            db_pkg = self.base.rpmdb.searchNevra(name=p.name, arch=p.arch)
            # that pkg is not actually installed
            if not db_pkg:
                # Effect of this is that a package that is only
                # available from disabled repos, it is not considered
                # an active package.
                # If none of the packages from a repo are active, then
                # the repo will not be considered active.
                #
                # Note however that packages that are installed, but
                # from an disabled repo, but that are also available
                # from another enabled repo will mark both repos as
                # active. This is why add on repos that include base
                # os packages almost never get marked for product cert
                # deletion. Anything that could have possible come from
                # that repo or be updated with makes the repo 'active'.
                continue

            # The pkg is installed, so the repo it was installed
            # from is considered 'active'
            # yum on 5.7 list everything as "installed" instead
            # of the repo it came from
            if repo in (None, "installed"):
                continue
            active.add(repo)

        return active

    def check_version_tracks_repos(self):
        major, minor, micro = yum.__version_info__
        yum_version = productid.RpmVersion(version="%s.%s.%s" % (major, minor, micro))
        needed_version = productid.RpmVersion(version="3.2.28")
        if yum_version >= needed_version:
            return True
        return False


def posttrans_hook(conduit):
    """
    Update product ID certificates.
    """
    # register rpm name for yum history recording
    # yum on 5.7 doesn't have this method, so check for it
    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName("subscription-manager")

    try:
        init_dep_injection()
    except ImportError, e:
        conduit.error(3, str(e))
        return

    logutil.init_logger_for_yum()
    # If a tool (it's, e.g., Anaconda and Mock) manages a chroot via
    # 'yum --installroot', we must update certificates in that directory.
    chroot(conduit.getConf().installroot)
    try:
        pm = productid.ProductManager()
        pm.update(YumPackageManager(conduit._base))
        conduit.info(3, 'Installed products updated.')
    except Exception, e:
        conduit.error(3, str(e))
