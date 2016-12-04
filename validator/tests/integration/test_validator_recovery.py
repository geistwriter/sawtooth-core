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
import os
import time
import unittest

from sawtooth.exceptions import MessageException
from txnintegration.utils import sit_rep
from txnintegration.utils import is_convergent
from txnintegration.utils import TimeOut
from txnintegration.utils import Progress

RUN_TEST_SUITES = True \
    if os.environ.get("RUN_TEST_SUITES", False) == "1" else False


class TestValidatorRecovery(unittest.TestCase):
    def __init__(self, test_name, urls=None, node_controller=None, nodes=None):
        super(TestValidatorRecovery, self).__init__(test_name)
        self.urls = urls
        self.node_ctrl = node_controller
        self.nodes = nodes

    def _kill_or_term_and_restore(self, sigkill=False):
        try:
            # Preconditions:
            self.assertGreater(len(self.urls), 2,
                               'validator restart tests require more than 2 '
                               'validators to analyze convergence')
            self.assertEqual(len(self.nodes), len(self.urls))
            self.assertTrue(is_convergent(self.urls, standard=2, tolerance=1,
                                          verbose=True))
            node_names = sorted(self.node_ctrl.get_node_names())
            self.assertEqual(len(self.nodes), len(node_names))
            # Parameters
            target = self.nodes[-1]
            target_url = self.urls[-1]
            # Stage 1:  Get initial blocklist
            blocks_before = sit_rep(self.urls)[-1]['Status']['Blocks']
            print "blocks before restart: {}".format(blocks_before)
            # Stage 2:  Shut down entire network
            intent_str = 'shutting down network'
            found_target = False
            with Progress(intent_str) as p:
                for node in self.node_ctrl.get_node_names():
                    if node != target.node_name:
                        print "Stopping {}".format(node)
                        self.node_ctrl.stop(node)
                    else:
                        found_target = True
                        if sigkill is True:
                            print "Killing {}".format(node)
                            self.node_ctrl.kill(node)
                        else:
                            print "Stopping {}".format(node)
                            self.node_ctrl.stop(node)
                self.assertTrue(found_target)
                to = TimeOut(16)
                while len(self.node_ctrl.get_node_names()) != 0:
                    self.assertFalse(to.is_timed_out(),
                                     'Timed out {}'.format(intent_str))
                    time.sleep(1)
                    p.step()
            # Stage 3:  Restore the target node
            intent_str = 'restarting {}'.format(target.node_name)
            with Progress(intent_str) as p:
                target.genesis = True
                self.node_ctrl.start(target)
                to = TimeOut(64)
                ready = False
                while ready is False:
                    try:
                        ready = is_convergent([self.urls[-1]], tolerance=2,
                                              standard=1)
                    except MessageException:
                        self.assertFalse(
                            to.is_timed_out(),
                            'Timed out {}'.format(intent_str))
                        time.sleep(1)
                        p.step()
            # Stage 4: Verify that blocks_before prefixes blocks_after
            blocks_after = sit_rep([self.urls[-1]])[0]['Status']['Blocks']
            print "blocks after restart: {}".format(blocks_after)
            # ...the length of blocks_after might be bigger than blocks_before
            self.assertGreaterEqual(len(blocks_after), len(blocks_before))
            for i in range(0, len(blocks_before)):
                self.assertEqual(blocks_after[i],
                                 blocks_before[i],
                                 "mismatch in post-shutdown validator blocks. "
                                 "Validator didn't restore fr local db")
        finally:
            intent_str = 'restarting network'
            with Progress(intent_str) as p:
                for node in self.nodes:
                    self.node_ctrl.start(node)
                to = TimeOut(64)
                ready = False
                while ready is False:
                    try:
                        ready = is_convergent(self.urls, tolerance=2,
                                              standard=1)
                    except MessageException:
                        self.assertFalse(
                            to.is_timed_out(),
                            'Timed out {}'.format(intent_str))
                        time.sleep(1)
                        p.step()

    @unittest.skipUnless(RUN_TEST_SUITES, "test suites")
    def test_sigterm(self):
        print
        print '{}.{}:'.format(self.__class__.__name__, inspect.stack()[0][3])
        self._kill_or_term_and_restore()

    @unittest.skipUnless(RUN_TEST_SUITES, "test suites")
    @unittest.skip('needs ACID stores to guarantee no corruption')
    def test_sigkill(self):
        print
        print '{}.{}:'.format(self.__class__.__name__, inspect.stack()[0][3])
        self._kill_or_term_and_restore(sigkill=True)
