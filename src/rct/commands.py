#
# Copyright (c) 2010 - 2012 Red Hat, Inc.
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

import gettext
from subscription_manager.cli import AbstractCLICommand
_ = gettext.gettext


class RCTCliCommand(AbstractCLICommand):
    def __init__(self):
        super(RCTCliCommand, self).__init__()

        self._add_options()

    def _add_options(self):
        pass

    def main(self, args=None):
        # assumme command (sys.argv[0]) and subcommand ('cat-cert') have
        # been removed from args list at this point. So any
        # args can be considered filenames
        args = args or []

        (self.options, self.args) = self.parser.parse_args(args)

        self._validate_options()

        return_code = self._do_command()
        if return_code is not None:
            return return_code

    # TODO: make property
    def filenames(self):
        return self.args
