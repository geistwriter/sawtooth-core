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
from txnintegration.integer_key_load_cli import IntKeyLoadTest
from txnintegration.utils import sit_rep
from txnintegration.utils import is_convergent

from txnintegration.utils import TimeOut
from txnintegration.utils import Progress

RUN_TEST_SUITES = True \
    if os.environ.get("RUN_TEST_SUITES", False) == "1" else False


class TestValidatorRestart(unittest.TestCase):
    def __init__(self, test_name, urls=None, node_controller=None, nodes=None):
        super(TestValidatorRestart, self).__init__(test_name)
        self.urls = urls
        self.node_ctrl = node_controller
        self.nodes = nodes

    def get_running_nodes(self):
        return sorted(self.node_ctrl.get_node_names())

    @unittest.skipUnless(RUN_TEST_SUITES, "test suites")
    def test_sigterm(self):
        print
        print '{}.{}:'.format(self.__class__.__name__, inspect.stack()[0][3])
        # Parameters:
        keys = 10
        rounds = 2
        txn_intv = 0
        test = IntKeyLoadTest()
        # Preconditions:
        self.assertGreater(len(self.urls), 2,
                           'validator restart tests require more than 2 '
                           'validators to analyze convergence')
        self.assertEqual(len(self.nodes), len(self.urls))
        self.assertTrue(is_convergent(self.urls, standard=2, tolerance=1,
                                      verbose=True))
        node_names = self.get_running_nodes()
        self.assertEqual(len(self.nodes), len(node_names))
        # Stage 1: send SIGTERM to 'last' node
        intent_str = 'halting {} with SIGTERM'.format(node_names[-1])
        with Progress(intent_str) as p:
            self.node_ctrl.stop(node_names[-1])
            to = TimeOut(16)
            while self.get_running_nodes() != node_names[:-1]:
                self.assertFalse(to.is_timed_out(),
                                 'Timed out {}'.format(intent_str))
                time.sleep(1)
                p.step()
        print 'validator situation report:'
        sit_rep(self.urls[:-1], verbosity=2)
        # Stage 2: advance remaining network and check that states converge
        print "sending more txns after SIGTERM"
        test.setup(self.urls[:-1], keys)
        test.run(keys, rounds, txn_intv)
        test.validate()
        # Stage 3: resurrect 'last' node, and let it catch up
        intent_str = 'restarting {}'.format(node_names[-1])
        with Progress(intent_str) as p:
            self.node_ctrl.start(self.nodes[-1])
            to = TimeOut(64)
            ready = False
            # restarted node sends EPR txn, which forces progress...
            while ready is False:
                try:
                    ready = is_convergent(self.urls, tolerance=2, standard=1)
                except MessageException:
                    self.assertFalse(
                        to.is_timed_out(),
                        'Timed out {}'.format(intent_str))
                    time.sleep(1)
                    p.step()

        print 'validator situation report:'
        sit_rep(self.urls, verbosity=2)
        # Stage 4: advance network and check that states converge
        print "sending more txns after relaunching validator 4"
        test.setup(self.urls, keys)
        test.run(keys, rounds, txn_intv)
        test.validate()
        # Stage 5: check convergence on chain
        self.assertTrue(is_convergent(self.urls, verbose=True))
