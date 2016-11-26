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
# from sawtooth.manage.declarative import get_default_vnm

import subprocess
from sawtooth.exceptions import ManagementError
from sawtooth.cli.exceptions import CliException

LOGGER = logging.getLogger(__name__)


'''
sawtooth cluster start --manage docker
    Starting: validator-000
    Starting: validator-001
    Starting: validator-002
    Starting: validator-003
    Starting: validator-004
    Starting: validator-005
    Starting: validator-006
    Starting: validator-007
    Starting: validator-008
    Starting: validator-009

docker ps -a (NB: CONTAINER ID,IMAGE,COMMAND,CREATED,STATUS,PORTS,NAMES)
    CONTAINER ID|PORTS                                           |NAMES
    372ea62a985b|0.0.0.0:32777->5509/udp, 0.0.0.0:32777->8809/tcp|validator-009
    6a412b248878|0.0.0.0:32776->5508/udp, 0.0.0.0:32776->8808/tcp|validator-008
    ce69a5ae22e6|0.0.0.0:32775->5507/udp, 0.0.0.0:32775->8807/tcp|validator-007
    7bcb784e9db1|0.0.0.0:32774->5506/udp, 0.0.0.0:32774->8806/tcp|validator-006
    e2a60875a545|0.0.0.0:32773->5505/udp, 0.0.0.0:32773->8805/tcp|validator-005
    2b407b3789c0|0.0.0.0:32772->5504/udp, 0.0.0.0:32772->8804/tcp|validator-004
    e27eb2a0b1cc|0.0.0.0:32771->5503/udp, 0.0.0.0:32771->8803/tcp|validator-003
    f069d686ee01|0.0.0.0:32770->5502/udp, 0.0.0.0:32770->8802/tcp|validator-002
    3ac9b73e793d|0.0.0.0:32769->5501/udp, 0.0.0.0:32769->8801/tcp|validator-001
    3ed8e3eb70b7|0.0.0.0:32768->5500/udp, 0.0.0.0:32768->8800/tcp|validator-000

'''


def call_and_check_subprocess(args):
    '''
    Args:
        args (list<str>):
    '''
    try:
        output = subprocess.check_output(args)
    except subprocess.CalledProcessError as e:
        raise ManagementError(str(e))


class Spike(object):
    def _get_port_info(self, node_name):
        args = [
            'docker',
            'ps',
            '-a',
            '--no-trunc',
            '--format',
            '{{.Ports}}',
            '--filter',
            'name={}'.format(node_name),
        ]
        try:
            output = subprocess.check_output(args)
        except subprocess.CalledProcessError as e:
            raise CliException(str(e))
        rslt = [x.strip() for x in output.split('\n') if x]
        if len(rslt) != 1:
            raise CliException('expected exactly one entry regarding ports for'
                               '{}; got {}'.format(node_name, rslt))
        rslt = [x.strip() for x in rslt[0].split(',')]
        if len(rslt) != 2:
            raise CliException('expected exactly two port entries in ports '
                               'for {}; got {}'.format(node_name, rslt))
        return rslt

    def get_http_port(self, node_name):
        rslt = self._get_port_info(node_name)
        rslt = [x for x in rslt if x.endswith('tcp')]
        if len(rslt) != 1:
            raise CliException('expected exactly one tcp entry for'
                               '{}; got {}'.format(node_name, rslt))
        rslt = rslt[0].split(':')[1]
        rslt = rslt.split('-')[0]
        return int(rslt)

from sawtooth.manage.utils import get_executable_script
class StubIndexedDockerVNM(object):
    def __init__(self, num_nodes):
        self._num_nodes = num_nodes
        self._node_controller = Spike()

    def do_genesis(self, idx):
        pass

    def launch(self):
        cmd = get_executable_script('sawtooth')
        cmd += ['cluster', 'start']
        cmd += ['--manage', 'docker']
        cmd += ['--count', str(self._num_nodes)]
        call_and_check_subprocess(cmd)
        print 'executed', ' '.join(cmd)

    def shutdown(self):
        cmd = get_executable_script('sawtooth')
        cmd += ['cluster', 'stop']
        call_and_check_subprocess(cmd)
        print 'executed', ' '.join(cmd)

    def _get_name(self, idx):
        assert idx < self._num_nodes
        return 'validator-00{}'.format(idx)

    def _get_url(self, idx):
        name = self._get_name(idx)
        port = self._node_controller.get_http_port(name)
        return 'http://localhost:{}'.format(port)

    def urls(self):
        return [self._get_url(idx) for idx in xrange(self._num_nodes)]

class SawtoothDockerClusterTestSuite(unittest.TestCase):
    def _do_setup(self):
        print 'creating', str(self.__class__.__name__)
#       self.vnm = get_default_vnm(2)
        self.vnm = StubIndexedDockerVNM(2)
        self.vnm.do_genesis(0)
        self.vnm.launch()

    def _do_teardown(self):
        if hasattr(self, 'vnm') and self.vnm is not None:
            print 'destroying', str(self.__class__.__name__)
            self.vnm.shutdown()

    def test_suite(self):
        success = False
        try:
            print
            self._do_setup()
            urls = self.vnm.urls()
            print urls
#           print json.dumps(self.vnm.sit_rep(err_on_fail=True), indent=4)
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
