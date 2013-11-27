#
# Copyright (c) 2013 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#

from mock import Mock, patch, NonCallableMock

import stubs
from fixture import SubManFixture
from subscription_manager import upgrade
from subscription_manager import injection as inj


@patch('rhsm.config', new_callable=stubs.StubConfig)
class TestRepoBuilder(SubManFixture):
    def setUp(self):
        super(TestRepoBuilder, self).setUp()
        self.conduit = Mock()
        self.builder = upgrade.RepoBuilder(self.conduit)
        self.content = []
        self.mock_dir = NonCallableMock()
        self.mock_dir.list_valid.return_value = [Mock(content=self.content)]
        inj.provide(inj.ENT_DIR, self.mock_dir)

    def test_empty_list_when_no_content(self, mock_cfg):
        result = self.builder.build_repos(['blah_tag'])
        self.assertEquals([], result)

    def test_duplicate_content(self, mock_cfg):
        c = stubs.StubContent('1', 'blah', required_tags='blah_tag')
        self.mock_dir.list_valid.return_value = [Mock(content=[c], serial=1), Mock(content=[c], serial=2)]
        result = self.builder._matching_content(['blah_tag'])
        self.assertEquals(1, len(result))

    def test_no_content(self, mock_cfg):
        result = self.builder._matching_content(['foo_tag'])
        self.assertEquals(set(), result)

    def test_not_allowed_content(self, mock_cfg):
        self.content.append(stubs.StubContent('foo_label', content_type='foo_type'))
        result = self.builder._matching_content(['foo_tag'])
        self.assertEquals(set(), result)

    def test_mismatching_content(self, mock_cfg):
        self.content.append(stubs.StubContent('1', 'blah', required_tags='blah_tag,blah2_tag'))
        result = self.builder._matching_content(['blah_tag, foo_tag'])
        self.assertEquals(set(), result)

    def test_subset_of_content(self, mock_cfg):
        self.content.append(stubs.StubContent('1', 'blah', required_tags='blah_tag,blah2_tag,blah3_tag'))
        result = self.builder._matching_content(['blah_tag'])
        self.assertEquals(set(), result)

    def test_matching_content(self, mock_cfg):
        c = stubs.StubContent('1', 'blah', required_tags='blah_tag')
        self.content.append(c)
        result = self.builder._matching_content(['blah_tag']).pop()
        self.assertEquals(c, result.content)

    def test_superset_of_content(self, mock_cfg):
        c = stubs.StubContent('1', 'blah', required_tags='blah_tag,blah2_tag')
        self.content.append(c)
        result = self.builder._matching_content(['blah_tag', 'blah2_tag', 'blah3_tag']).pop()
        self.assertEquals(c, result.content)
