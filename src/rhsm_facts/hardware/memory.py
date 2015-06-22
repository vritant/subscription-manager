# Module to probe Hardware info from the system
#
# Copyright (c) 2010-2015 Red Hat, Inc.
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
import re

from rhsm_facts import exceptions

log = logging.getLogger('rhsm-app.' + __name__)


class MeminfoCollectorError(exceptions.FactCollectorError):
    pass


class MemoryInfo(object):
    key_value_regex_string = r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB'
    fact_namespace = "memory"

    def __init__(self, meminfo_string=None):
        self.data = {}
        self.meminfo_string = meminfo_string
        self.useful_fields = ["MemTotal", "SwapTotal"]
        self.key_value_regex = re.compile(self.key_value_regex_string)

    def parse(self):
        mem_info = {}

        # most of this mem info changes constantly, which makes decding
        # when to update facts painful, so lets try to just collect the
        # useful bits
        for info in self.meminfo_string.splitlines():
            match = self.key_value_regex.match(info)
            if not match:
                continue
            key, value = match.groups(['key', 'value'])
            if key in self.useful_fields:
                nkey = '.'.join([self.fact_namespace, key.lower()])
                mem_info[nkey] = "%s" % int(value)
        return mem_info


class ProcMemoryinfo(MemoryInfo):
    meminfo_filename = "/proc/meminfo"

    def __init__(self):
        super(ProcMemoryinfo, self).__init__()
        self.meminfo_string = self.read_file(self.meminfo_filename)
        self.data = self.parse()

    def read_file(self, meminfo_filename):
        with open(meminfo_filename, 'r') as meminfo_fo:
            meminfo_string = meminfo_fo.read()
        return meminfo_string


class Memory(object):
    def __init__(self, prefix=None, testing=None):
        self.data = {}
        self.prefix = prefix or ''

    def collect(self, collected_facts):
        try:
            memory = ProcMemoryinfo()
        except Exception, e:
            log.exception(e)
            raise MeminfoCollectorError(e)

        collected_facts.update(memory.data)
        return collected_facts
