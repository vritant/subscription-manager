#!/usr/bin/python

#
# Copyright (c) 2014 Red Hat, Inc.
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
import fnmatch
import os
import re
import shutil
import subprocess

from glob import glob
from setuptools import setup, find_packages

from distutils import cmd, log
from distutils.command.install_data import install_data as _install_data
from distutils.command.build import build as _build
from distutils.command.clean import clean as _clean
from distutils.dir_util import remove_tree


class Utils(object):
    @staticmethod
    def create_dest_dir(dest):
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))

    @staticmethod
    def run_if_new(src, dest, callback):
        Utils.create_dest_dir(dest)
        src_mtime = os.stat(src)[8]
        try:
            dest_mtime = os.stat(dest)[8]
        except OSError:
            dest_mtime = 0
        if src_mtime > dest_mtime:
            callback(src, dest)


# Courtesy http://wiki.maemo.org/Internationalize_a_Python_application
class build_trans(cmd.Command):
    description = 'Compile .po files into .mo files'

    def initialize_options(self):
        self.build_base = None

    def finalize_options(self):
        self.set_undefined_options('build', ('build_base', 'build_base'))

    def compile(self, src, dest):
        log.info("Compiling %s" % src)
        cmd = ['msgfmt', '-c', '--statistics', '-o', dest, src]
        rc = subprocess.call(cmd)
        if rc != 0:
            raise RuntimeError("msgfmt failed for %s to %s" % (src, dest))

    def run(self):
        po_dir = os.path.join(os.curdir, 'po')
        for path, names, filenames in os.walk(po_dir):
            for f in filenames:
                if f.endswith('.po'):
                    lang = f[:-3]
                    src = os.path.join(path, f)
                    dest_path = os.path.join(self.build_base, 'locale', lang, 'LC_MESSAGES')
                    dest = os.path.join(dest_path, 'rhsm.mo')
                    Utils.run_if_new(src, dest, self.compile)


class clean(_clean):
    def initialize_options(self):
        self.egg_base = None
        _clean.initialize_options(self)

    def finalize_options(self):
        self.set_undefined_options('egg_info', ('egg_base', 'egg_base'))
        _clean.finalize_options(self)

    def run(self):
        if self.all:
            for f in glob(os.path.join(self.egg_base, '*.egg-info')):
                log.info("removing %s" % f)
                remove_tree(f, dry_run=self.dry_run)
        _clean.run(self)


class build(_build):
    sub_commands = _build.sub_commands + [('build_trans', None)]

    def run(self):
        _build.run(self)


class install_data(_install_data):
    def initialize_options(self):
        self.transforms = None
        # Can't use super() because Command isn't a new-style class.
        _install_data.initialize_options(self)

    def finalize_options(self):
        if self.transforms is None:
            self.transforms = []
        _install_data.finalize_options(self)

    def run(self):
        self.add_messages()
        _install_data.run(self)
        self.transform_files()

    def transform_files(self):
        for file_glob, new_extension in self.transforms:
            matches = fnmatch.filter(self.outfiles, file_glob)
            for f in matches:
                out_dir = os.path.dirname(f)
                out_name = os.path.basename(f).split('.')[0] + new_extension
                self.move_file(f, os.path.join(out_dir, out_name))

    def add_messages(self):
        for lang in os.listdir('build/locale/'):
            lang_dir = os.path.join('share', 'locale', lang, 'LC_MESSAGES')
            lang_file = os.path.join('build', 'locale', lang, 'LC_MESSAGES', 'rhsm.mo')
            self.data_files.append((lang_dir, [lang_file]))

setup_requires = ['flake8']

install_requires = []

test_require = [
      'mock',
      'nose',
      'coverage',
      'polib',
      'freezegun',
    ] + install_requires + setup_requires

cmdclass = {
    'build': build,
    'build_trans': build_trans,
    'clean': clean,
    'install_data': install_data,
}

transforms=[
    ('*.completion.sh', '.sh'),
    ('*.pam', ''),
    ('*.console', ''),
]

setup(name="subscription-manager",
    version='1.13.3',
    url="http://candlepinproject.org",
    description="Manage subscriptions for Red Hat products.",
    license="GPLv2",
    author="Adrian Likins",
    author_email="alikins@redhat.com",
    cmdclass=cmdclass,
    packages=find_packages('src', exclude=['subscription_manager.gui.firstboot']),
    package_dir={'': 'src'},
    data_files=[
        ('sbin', ['bin/subscription-manager', 'bin/subscription-manager-gui', 'bin/rhn-migrate-classic-to-rhsm']),
        ('bin', ['bin/rct', 'bin/rhsm-debug']),
        ('share/man/man8', glob('man/*.8')),
        ('share/gnome/help/subscription-manager/C', glob('docs/*.xml')),
        ('share/gnome/help/subscription-manager/C/figures', glob('docs/figures/*.png')),
        ('share/omf/subscription-manager', glob('docs/*.omf')),
        ('/etc/rhsm', ['etc-conf/rhsm.conf']),
        ('/etc/pam.d', glob('etc-conf/*.pam')),
        ('/etc/logrotate.d/subscription-manager', ['etc-conf/logrotate.conf']),
        ('/etc/yum/pluginconf.d', glob('etc-conf/plugin/*.conf')),
        ('/etc/bash_completion.d', glob('etc-conf/*.completion.sh')),
        ('/etc/security/console.apps', glob('etc-conf/*.console')),

    ],
    command_options={
        'install_data': {
            'transforms': ('setup.py', transforms),
        },
        'egg_info': {
            'egg_base': ('setup.py', os.curdir),
        },
    },
    include_package_data=True,
    setup_requires=setup_requires,
    install_requires=install_requires,
    tests_require=test_require,
    test_suite='nose.collector',
)
