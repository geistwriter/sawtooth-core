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

import logging
import time

from sawtooth.exceptions import ManagementError
from sawtooth.manage.node import NodeArguments
from sawtooth.manage.simple import SimpleNodeCommandGenerator
from sawtooth.manage.subproc import SubprocessNodeController
from sawtooth.manage.wrap import WrappedNodeController
from sawtooth.manage.vnm import ValidatorNetworkManager

LOGGER = logging.getLogger(__name__)


class DeclarativeNode(NodeArguments):
    def __init__(self, node_name, http_port=None, gossip_port=None,
                 currrency_home=None, config_files=None, genesis=False):
        super(DeclarativeNode, self).\
            __init__(node_name, http_port=http_port, gossip_port=gossip_port,
                     currency_home=currrency_home, config_files=config_files,
                     genesis=False)
        self.activated = False


class IndexedNodeCommandGenerator(SimpleNodeCommandGenerator):
    def __init__(self):
        super(IndexedNodeCommandGenerator, self).__init__()
        self._nodes = []

    def append_node(self):
        idx = len(self._nodes)
        node_name = "validator-{:0>3}".format(idx)
        genesis = (idx == 0)
        gossip_port = 5500 + idx
        http_port = 8800 + idx
        node = DeclarativeNode(node_name, http_port=http_port,
                               gossip_port=gossip_port, genesis=genesis)
        self._nodes.append(node)

    def _get_node(self, idx):
        if not idx < len(self._nodes):
            raise ManagementError('index {} out of range'.format(idx))
        return self._nodes[idx]

    def _index_to_name(self, idx):
        nd = self._get_node(idx)
        return nd.node_name

    def genesis_by_idx(self, idx):
        nd = self._get_node(idx)
        nd.genesis = True
        self.genesis(nd)

    def start_by_idx(self, idx):
        nd = self._get_node(idx)
        self.start(nd)
        nd.activated = True

    def stop_by_idx(self, idx):
        nd = self._get_node(idx)
        self.stop(nd.node_name)
        nd.activated = False

    def kill_by_idx(self, idx):
        nd = self._get_node(idx)
        self.kill(nd.node_name)
        nd.activated = False

    def append_nodes(self, num_nodes):
        for _ in xrange(num_nodes):
            self.append_node()

    def launch(self):
        for idx in range(len(self._nodes)):
            self.start_by_idx(idx)

    def urls(self):
        url_str = 'http://localhost:{}'
        return {x.node_name: url_str.format(x.http_port) for x in self._nodes}

    def declaration(self):
        return {x.node_name: {'Activated': x.activated} for x in self._nodes}


class IndexedValidatorNetworkManager(ValidatorNetworkManager):
    def __init__(self, node_controller, node_command_generator, num_nodes=0):
        super(IndexedValidatorNetworkManager, self).\
            __init__(node_controller, node_command_generator)
        self._node_command_generator.append_nodes(num_nodes)

    def do_genesis(self, idx, update=True):
        self._node_command_generator.genesis_by_idx(idx)
        if update:
            self.update()

    def start(self, idx, update=True):
        self._node_command_generator.start_by_index(idx)
        if update:
            self.update()

    def stop(self, idx, update=True):
        self._node_command_generator.start_by_index(idx)
        if update:
            self.update()

    def kill(self, idx, update=True):
        self._node_command_generator.kill_by_index(idx)
        if update:
            self.update()

    def launch(self):
        self._node_command_generator.launch()
        self.update()

    def sit_rep(self, err_on_fail=False):
        declaration = self._node_command_generator.declaration()
        for key in declaration.keys():
            declaration[key]['Running'] = False
        actual = self._node_controller.get_node_names()
        for node_name in actual:
            declaration[node_name]['Running'] = True
        if err_on_fail is True:
            success = True
            for key in declaration.keys():
                x = declaration[key]
                if x['Activated'] != x['Running']:
                    LOGGER.error('%s -- expected: %s; actual: %s', key,
                                 x['Activated'], x['Running'])
                    success = False
            if success is False:
                raise ManagementError('unexpected state')
        return declaration

    def urls(self):
        possible = self._node_command_generator.urls()
        actual = self._node_controller.get_node_names()
        return [possible[x] for x in actual]

    def shutdown(self, timeout=16):
        # pylint: disable=broad-except
        # Shut down the network
        for node_name in self._node_controller.get_node_names():
            self._node_controller.stop(node_name)
        mark = time.time()
        while len(self._node_controller.get_node_names()) > 0:
            if time.time() - mark > timeout:
                break
            time.sleep(1)
        # force kill anything left over
        for node_name in self._node_controller.get_node_names():
            try:
                self._node_controller.kill(node_name)
            except Exception as e:
                print e.message
        self._node_controller.clean()


def get_default_vnm(num_nodes):
    cmd = IndexedNodeCommandGenerator()
    ctrl = WrappedNodeController(SubprocessNodeController())
    return IndexedValidatorNetworkManager(ctrl, cmd, num_nodes=num_nodes)
