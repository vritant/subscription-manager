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

import base64
import gettext
import os
import sys

from rhsm import certificate, _certificate
from rhsm.certificate2 import EntitlementCertificate

from rct.commands import RCTCliCommand
from rct.printing import printc, type_to_string

from subscription_manager.cli import InvalidCLIOptionError

_ = gettext.gettext


class RCTCertCommand(RCTCliCommand):

    def __init__(self):
        super(RCTCertCommand, self).__init__()

    # TODO: make class attr
    def _get_usage(self):
        return _("%%prog %s [OPTIONS] CERT_FILE") % self.name

    def _create_cert(self, cert_file):
        if not os.path.isfile(cert_file):
            raise InvalidCLIOptionError(_("The specified certificate file does not exist."))

        try:
            return certificate.create_from_file(cert_file)
        except certificate.CertificateException, ce:
            raise InvalidCLIOptionError(
                    _("Unable to read certificate file '%s': %s") % (cert_file,
                        ce))

    def certs_and_filenames(self):
        certs_and_filenames = []
        for cert_filename in self.filenames():
            try:
                cert = self._create_cert(cert_filename)
                certs_and_filenames.append((cert, cert_filename))
            except InvalidCLIOptionError, e:
                sys.stderr.write('%s\n' % e)
                continue
        return certs_and_filenames

    def certs(self):
        certs_and_filenames = self.certs_and_filenames()
        return [x[0] for x in certs_and_filenames]

    def _validate_options(self):
        cert_files = self.filenames()
        if not cert_files:
            raise InvalidCLIOptionError(_("You must specify a certificate file."))


class CatCertCommand(RCTCertCommand):
    name = "cat-cert"
    aliases = ['cc']
    shortdesc = _("Print certificate information"),
    primary = True

    def _add_options(self):
        super(CatCertCommand, self)._add_options()

        self.parser.add_option("--no-products", dest="no_products", action="store_true",
                               help=_("do not show the cert's product information"))
        self.parser.add_option("--no-content", dest="no_content", action="store_true",
                               help=_("do not show the cert's content info"))

    def _do_command(self):
        """
        Does the work that this command intends.
        """
        certs = self.certs()
        for cert in certs:
            printc(cert, skip_content=self.options.no_content,
                   skip_products=self.options.no_products)


class StatCertCommand(RCTCertCommand):
    name = "stat-cert"
    aliases = ['sc']
    shortdesc = _("Print certificate statistics and sizes"),
    primary = True

    def _do_command(self):
        certs = self.certs()

        # TODO: better support multiple certs in a file.
        for cert in certs:
            self.print_cert_stat(cert)

    def print_cert_stat(self, cert):
        pem = cert.x509.as_pem()
        print _("Type: %s") % type_to_string(cert)
        print _("Version: %s") % cert.version
        print _("DER size: %db") % self._get_der_size(pem)

        subject_key_id = self._get_subject_key_id(pem)
        if subject_key_id is not None:
            print _("Subject Key ID size: %db") % len(subject_key_id)

        if isinstance(cert, EntitlementCertificate):
            content_len = 0
            if cert.content:
                content_len = len(cert.content)
            print _("Content sets: %s") % content_len

    def _get_pem(self, filename):
        return open(filename, 'r',).read()

    def _get_der_size(self, pem):
        parts = pem.split("-----BEGIN CERTIFICATE-----\n")
        cert = parts[1].split("-----END CERTIFICATE-----")[0]
        return len(base64.b64decode(cert))

    def _get_subject_key_id(self, pem):
        cert = _certificate.load(pem=pem)
        subject_key_id = cert.get_extension(oid="2.5.29.14")
        return subject_key_id
