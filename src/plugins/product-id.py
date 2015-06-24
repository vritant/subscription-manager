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

import sys
from yum.plugins import TYPE_CORE, TS_INSTALL_STATES

sys.path.append('/usr/share/rhsm')


from subscription_manager import logutil
from subscription_manager.productid import ProductManager
from subscription_manager.utils import chroot
from subscription_manager.injectioninit import init_dep_injection

requires_api_version = '2.6'
plugin_type = (TYPE_CORE,)

import logging
log = logging.getLogger('rhsm-app.' + __name__)


def is_rhsm_repo(repo):
    repo_items = repo.iteritems()
    for key, value in repo_items:
        log.debug('key=%s, value=%s', key, value)
        if key == 'generated_by' and value == 'subscription-manager':
            return True
    return False


def iter_rhsm_items(repo):
    repo_items = repo.iteritems()
    for rhsm_key, rhsm_item in [(item_key, item_value)
                                for (item_key, item_value)
                                in repo_items
                                if item_key.startswith('rhsm_')]:
        yield rhsm_key, rhsm_item


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

    yb = conduit._base


    # If a tool (it's, e.g., Anaconda and Mock) manages a chroot via
    # 'yum --installroot', we must update certificates in that directory.
    chroot(conduit.getConf().installroot)
    try:
        pm = ProductManager()
        pm.update(conduit._base)
        conduit.info(3, 'Installed products updated.')
    except Exception, e:
        conduit.error(3, str(e))
        return

    # enabled repos, all, not just rhsm
    rhsm_enabled_repos = {}
    all_enabled_repos = yb.repos.listEnabled()
    for enabled_repo in all_enabled_repos:
        if is_rhsm_repo(enabled_repo):
            rhsm_enabled_repos[enabled_repo.name] = enabled_repo

    log.debug("rhsm_enabled_repos=%s", rhsm_enabled_repos)

    ts_info = conduit.getTsInfo()
    for tx_member in ts_info:
        if tx_member.output_state in TS_INSTALL_STATES:
            log.debug(tx_member)
            log.debug(tx_member.pkgtup)
            pos = yb.rpmdb.searchPkgTuple(tx_member.pkgtup)
            po = pos[0]

            # This is post tranaction, and we should have added
            # any repos that rhsm repos that were used in ProductManager.update
            # so pm.db should have the repo
            from_repo = po.yumdb_info.from_repo
            pids = pm.db.search_by_repo(from_repo)

            rhsm_repo = rhsm_enabled_repos.get(from_repo, None)
            log.debug("rhsm_repo=%s", rhsm_repo)
            if rhsm_repo:
                rhsm_item_iter = iter_rhsm_items(rhsm_repo)
                # populate the rhsm_ info
                for rhsm_key, rhsm_value in rhsm_item_iter:
                    setattr(po.yumdb_info, rhsm_key, rhsm_value)

            # Or, we could see if its a rhsm_repo
            # if we know the from_repo, and it's ours, add a 'rhsm_installed'
            if pids:
                po.yumdb_info.rhsm_installed = "1"

            # we could lookup from_repo in redhat.repo or Repo(), and
            # transfer any redhat.repo rhsm_* info here (or the ent cert
            # info...)

            log.debug("pids=%s", pids)

            # in addition to adding an entry to productid.js, lets also
            # tag this particular installed package as being installed via
            # the product id.
            for pid in pids:
                po.yumdb_info.product_id = pid
                log.debug("yumdb.product_id=%s", pid)



