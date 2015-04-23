#
# Copyright (c) 2012 Red Hat, Inc.
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
import mock

from subscription_manager import managercli
from subscription_manager import injection as inj

from stubs import StubEntitlementDirectory, StubProductDirectory, StubEntActionInvoker, \
        StubEntitlementCertificate, StubProduct
import fixture


# This is a copy of CliUnSubscribeTests for the new name.
class CliRemoveTests(fixture.SubManFixture):

    def setUp(self):
        super(CliRemoveTests, self).setUp()
        self.ent_cert_patcher = mock.patch("subscription_manager.managercli.EntCertActionInvoker")
        self.mock_ent_action = self.ent_cert_patcher.start()
        self.mock_ent_action.return_value = StubEntActionInvoker()

    def tearDown(self):
        super(CliRemoveTests, self).tearDown()
        self.ent_cert_patcher.stop()

    def test_remove_all(self):
        cmd = managercli.RemoveCommand()

        mock_identity = self._inject_mock_valid_consumer()

        cmd.main(['--all'])
        self.assertEquals(cmd.cp.called_unbind_uuid,
                          mock_identity.uuid)

    def test_remove_one_serial(self):
        # Need to create a new Command for each main() invocation,
        # the optparse options that accumulate (action='append') add
        # to the parse instance, so calling main multiple times keeps
        # adding to the list the option points at.
        cmd = managercli.RemoveCommand()
        serial1 = '123456'
        cmd.main(['--serial=%s' % serial1])

        self.assertEquals(cmd.cp.called_unbind_serial, [serial1])

    def test_remove_two_serials(self):
        cmd = managercli.RemoveCommand()
        serial1 = '123456'
        serial2 = '789012'
        cmd.main(['--serial=%s' % serial1, '--serial=%s' % serial2])

        self.assertEquals(cmd.cp.called_unbind_serial, [serial1, serial2])

    def test_remove_unregistered_all(self):
        prod = StubProduct('stub_product')
        ent = StubEntitlementCertificate(prod)

        inj.provide(inj.ENT_DIR,
                StubEntitlementDirectory([ent]))
        inj.provide(inj.PROD_DIR,
                StubProductDirectory([]))
        cmd = managercli.RemoveCommand()

        self._inject_mock_invalid_consumer()

        cmd.main(['--all'])

        self.assertTrue(cmd.entitlement_dir.list_called)
        self.assertTrue(ent.is_deleted)

    def test_remove_unregistered_two(self):
        prod = StubProduct('stub_product')
        ent1 = StubEntitlementCertificate(prod)
        ent2 = StubEntitlementCertificate(prod)
        ent3 = StubEntitlementCertificate(prod)

        inj.provide(inj.ENT_DIR,
                StubEntitlementDirectory([ent1, ent2, ent3]))
        inj.provide(inj.PROD_DIR,
                StubProductDirectory([]))

        cmd = managercli.RemoveCommand()
        cmd.main(['--serial=%s' % ent1.serial, '--serial=%s' % ent3.serial])

        self.assertTrue(ent1.is_deleted)
        self.assertFalse(ent2.is_deleted)
        self.assertTrue(ent3.is_deleted)
