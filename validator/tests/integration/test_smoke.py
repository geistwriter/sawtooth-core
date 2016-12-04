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

import inspect
import logging
import os
import unittest

from txnintegration.integer_key_load_cli import IntKeyLoadTest
from txnintegration.utils import is_convergent

logger = logging.getLogger(__name__)

ENABLE_INTEGRATION_TESTS = True \
    if os.environ.get("ENABLE_INTEGRATION_TESTS", False) == "1" else False

RUN_TEST_SUITES = True \
    if os.environ.get("RUN_TEST_SUITES", False) == "1" else False


class TestSmoke(unittest.TestCase):
    def __init__(self, test_name, urls=None):
        super(TestSmoke, self).__init__(test_name)
        self.urls = urls

    @unittest.skipUnless(ENABLE_INTEGRATION_TESTS, "integration test")
    @unittest.skipUnless(RUN_TEST_SUITES, "test suites")
    def test_intkey_load(self):
        print
        print '{}.{}:'.format(self.__class__.__name__, inspect.stack()[0][3])
        test = IntKeyLoadTest()
        print "Testing transaction load."
        test.setup(self.urls, 100)
        test.run(2)
        test.validate()
        self.assertTrue(is_convergent(self.urls, verbose=True))
        print "No Validator data and logs to preserve"

#   @unittest.skipUnless(RUN_TEST_SUITES, "test suites")
#   def test_intkey_load_dev_mode(self):
#       self._run_int_load(1, "TestSmokeResultsDevMode", None,
#                          urls=["http://localhost:8800"])
