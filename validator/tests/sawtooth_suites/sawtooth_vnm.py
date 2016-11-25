# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

import json
import logging
import traceback
import unittest

from integration.test_convergence import TestConvergence
from sawtooth.manage.declarative import get_default_vnm

LOGGER = logging.getLogger(__name__)


class SawtoothVnmTestSuite(unittest.TestCase):
    def _do_teardown(self):
        if hasattr(self, 'vnm') and self.vnm is not None:
            print 'destroying', str(self.__class__.__name__)
            self.vnm.shutdown()

    def _do_setup(self):
        print 'creating', str(self.__class__.__name__)
        self.vnm = get_default_vnm(2)
        self.vnm.do_genesis(0)
        self.vnm.launch()

    def test_suite(self):
        success = False
        try:
            print
            self._do_setup()
            print json.dumps(self.vnm.sit_rep(err_on_fail=True), indent=4)
            urls = self.vnm.urls()
            suite = unittest.TestSuite()
            suite.addTest(TestConvergence('test_bootstrap', urls))
            runner = unittest.TextTestRunner()
            result = runner.run(suite)
            if len(result.failures) == 0 and len(result.errors) == 0:
                success = True
        except:
            traceback.print_exc()
            raise
        finally:
            self._do_teardown()
            if success is False:
                self.fail(self.__class__.__name__)
