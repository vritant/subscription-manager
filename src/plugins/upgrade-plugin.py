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
import sys
from yum.plugins import TYPE_CORE, PluginYumExit

sys.path.append('/usr/share/rhsm')

requires_api_version = '2.6'
plugin_type = (TYPE_CORE,)

from subscription_manager.injectioninit import init_dep_injection
from subscription_manager.logutil import init_logger
from subscription_manager import upgrade


def _init(conduit):
    # register rpm name for yum history recording
    # old yums don't have this method, so check for it
    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName("subscription-manager")

    init_dep_injection()
    init_logger()


def postconfig_hook(conduit):
    _init(conduit)
    try:
        refresher = upgrade.EntitlementRefresher(conduit)
        # We need to refresh all the entitlement certs before
        # Yum reads the .repo files
        refresher.refresh()
    except Exception, e:
        conduit.error(3, 'Could not refresh certificates.')
        raise PluginYumExit(str(e))


def init_hook(conduit):
    try:
        builder = upgrade.RepoBuilder(conduit)
        upgrade_repos = builder.build_repos()
        repos = conduit.getRepos()
        for r in upgrade_repos:
            repos.add(r)
    except Exception, e:
        conduit.error(3, 'Could not build repos for upgrading.')
        raise PluginYumExit(str(e))
