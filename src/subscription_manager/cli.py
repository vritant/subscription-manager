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
import logging
import os
import sys

from subscription_manager.printing_utils import columnize, _echo
from subscription_manager.i18n_optparse import OptionParser, WrappedIndentedHelpFormatter
from subscription_manager import utils

_ = gettext.gettext

log = logging.getLogger("rhsm-app." + __name__)


class InvalidCLIOptionError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class AbstractCLICommand(object):
    """
    Base class for rt commands. This class provides a templated run
    strategy.

    Each sub command will sub class this class.

    Note: CLI() is not a subclass of AbstractCLICommand(), but
    subclasses like managercli.RegisterCommand() are.

    CLI() is the base of the top level command, AbstractCliCommand() is
    the base of the subcommands.
    """
    name = "cli"
    aliases = []
    primary = False
    shortdesc = "A command thingy"

    def __init__(self):

        # include our own HelpFormatter that doesn't try to break
        # long words, since that fails on multibyte words
        self.parser = OptionParser(usage=self._get_usage(),
                                   description=self.shortdesc,
                                   formatter=WrappedIndentedHelpFormatter())

    def main(self, args=None):
        """Each subclass needs to implement main().

        'args' will be a list of command line options as strings.
        'args' is not and should not be a reference to sys.argv, and
        'args' will have had sys.argv[0] removed before calling this.

        Typically, the __main__ in the executable wrapper scripts
        (aka, /bin/subscription-manager) will read sys.argv and copy it
        to a list, removing [0], and passing it main().
        """
        raise NotImplementedError("Commands must implement: main(self, args=None)")

    def _validate_options(self):
        '''
        Validates the command's arguments.
        @raise InvalidCLIOptionError: Raised when arg validation fails.
        '''
        # No argument validation by default.
        pass

    def _get_usage(self):
        # usage format strips any leading 'usage' so
        # do not iclude it
        return _("%%prog %s [OPTIONS]") % self.name

    def _do_command(self):
        """
        Does the work that this command intends.
        """
        raise NotImplementedError("Commands must implement: _do_command(self)")


# taken wholseale from rho...
class CLI(object):
    """Base class for the top level CLI command.

    This class represents the top level CLI, that is responsible for
    settings up sub command classes, and invoking the sub command class
    based on the cli args.

    For a cli of 'subscription-manager register --username', this class
    parses cli and finds the subcommand name 'register' 'register' is looked
    up in the list of command_classes by comparing 'register' with each
    command classes .name attribute. It will also look for command class
    aliases and resolve them. So 'attach' has an alias of 'subscribe', so
    either 'attach' or 'subscribe' will match AttachCommand.

    main(args) will pass args to the resolve command_classes' .main. In
    the example above, this is RegisterCommand().main(["register", "--username"])
    """
    def __init__(self, command_classes=None):

        # log client versions early, server versions
        # are logged later if we detect we are using the network
        self.log_client_versions()

        command_classes = command_classes or []

        self.cmd_name_to_cmd = {}
        self.cli_commands = {}
        for clazz in command_classes:
            cmd = clazz()

            if cmd.name == "cli":
                continue

            self.cmd_name_to_cmd[cmd.name] = cmd
            self.cli_commands[cmd.name] = cmd

            for alias in cmd.aliases:
                self.cmd_name_to_cmd[alias] = cmd

    def log_client_versions(self):
        self.client_versions = utils.get_client_versions()
        log.info("Client Versions: %s" % self.client_versions)

    def _usage(self):
        print _("Usage: %s MODULE-NAME [MODULE-OPTIONS] [--help]") % os.path.basename(sys.argv[0])
        print "\r"
        items = self.cli_commands.items()
        items.sort()
        items_primary = []
        items_other = []
        for (name, cmd) in items:
            if (cmd.primary):
                items_primary.append(("  " + name, cmd.shortdesc))
            else:
                items_other.append(("  " + name, cmd.shortdesc))

        all_items = [(_("Primary Modules:"), '\n')] + \
                items_primary + [('\n' + _("Other Modules:"), '\n')] + \
                items_other
        self._do_columnize(all_items)

    def _do_columnize(self, items_list):
        modules, descriptions = zip(*items_list)
        print columnize(modules, _echo, *descriptions) + '\n'

    def pop_subcommand_from_args(self, args):
        """Given a list of args, find the first subcommands and it's following args.

        If no sub_cmds are found, return (None, args)
        If a sub_cmd is found, return sub_cmd, rest of args

        for args = ["--foo","not_a_subcommand", "cat-cert", "--blip", "filename1", "filename2"]
        and a sub command with name 'cat-cert', this returns
            CatCertCommand, ['--blip', 'filename1', 'filename2']

        Note the sub_cmd_name is not in the list returned.
        """
        sub_cmd = None

        for index, arg in enumerate(args):
            # ignore options
            if arg.startswith('-'):
                continue

            # look cmd name or aliases
            sub_cmd = self.cmd_name_to_cmd.get(arg, None)

            # return the first sub command, and the rest of the args
            if sub_cmd:
                # sub cmd and the rest of args
                new_args = args[index:]
                # just the rest of the args with command removed
                sub_cmd_args = new_args[1:]
                return sub_cmd, sub_cmd_args

        return sub_cmd, args

    def main(self, args):
        if len(args) < 1:
            self._usage()
            sys.exit(0)

        sub_cmd, sub_cmd_args = self.pop_subcommand_from_args(args)

        if not sub_cmd:
            self._usage()
            # Allow for a 0 return code if just calling --help
            return_code = 1
            if (len(args) > 1) and (args[1] == "--help"):
                return_code = 0
            sys.exit(return_code)

        try:
            return sub_cmd.main(args=sub_cmd_args)
        except InvalidCLIOptionError, error:
            print error


def system_exit(code, msgs=None):
    "Exit with a code and optional message(s). Saved a few lines of code."

    if msgs:
        if type(msgs) not in [type([]), type(())]:
            msgs = (msgs, )
        for msg in msgs:
            # see bz #590094 and #744536
            # most of our errors are just str types, but error's returned
            # from rhsm.connection are unicode type. This method didn't
            # really expect that, so make sure msg is unicode, then
            # try to encode it as utf-8.

            # if we get an exception passed in, and it doesn't
            # have a str repr, just ignore it. This is to
            # preserve existing behaviour. see bz#747024
            if isinstance(msg, Exception):
                msg = "%s" % msg

            if isinstance(msg, unicode):
                sys.stderr.write("%s\n" % msg.encode("utf8"))
            else:
                sys.stderr.write("%s\n" % msg)

    sys.exit(code)
