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

from argparse import Namespace
import logging
import os
import time
import yaml

from sawtooth.cli.exceptions import CliException
from sawtooth.exceptions import ManagementError
from sawtooth.manage.daemon import DaemonNodeController
from sawtooth.manage.docker import DockerNodeController
from sawtooth.manage.node import NodeArguments
from sawtooth.manage.simple import SimpleNodeCommandGenerator
from sawtooth.manage.subproc import SubprocessNodeController
from sawtooth.manage.wrap import WrappedNodeController
from sawtooth.manage.vnm import ValidatorNetworkManager

LOGGER = logging.getLogger(__name__)


def add_cluster_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('cluster', parents=[parent_parser])

    cluster_subparsers = parser.add_subparsers(
        title='subcommands',
        dest='cluster_command')

    add_cluster_start_parser(cluster_subparsers, parent_parser)
    add_cluster_status_parser(cluster_subparsers, parent_parser)
    add_cluster_stop_parser(cluster_subparsers, parent_parser)
    add_cluster_extend_parser(cluster_subparsers, parent_parser)
    add_cluster_reset_parser(cluster_subparsers, parent_parser)


def add_cluster_status_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('status', parents=[parent_parser])

    parser.add_argument(
        'node_names',
        metavar='NODE_NAME',
        help='report status of specific node(s)',
        nargs='*')


def add_cluster_start_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('start', parents=[parent_parser])

    parser.add_argument(
        '--count',
        help='number of nodes to start',
        type=int,
        default=10)

    parser.add_argument(
        '-m', '--manage',
        help='style of validator management',
        choices=['subprocess', 'daemon', 'docker'],
        default='subprocess')

    parser.add_argument('--wrap', nargs='?', const=None, default=False,
                        help='use WRAP as CURRENCYHOME (create/use a temp '
                             'directory if WRAP is unspecified)')


def add_cluster_stop_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('stop', parents=[parent_parser])

    parser.add_argument(
        'node_names',
        metavar='NODE_NAME',
        help='stop specific node(s)',
        nargs='*')


def add_cluster_extend_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('extend', parents=[parent_parser])

    parser.add_argument(
        '--count',
        help='number of nodes to add to network',
        type=int,
        default=1)

def add_cluster_reset_parser(subparsers, parent_parser):
    help_str='Reset the state of sawtooth cluster.  If --wrap was initially ' \
             'called without a concrete directory, reset deletes all ' \
             'associated data (including blockchains).'
    subparsers.add_parser('reset', parents=[parent_parser],
                          description=help_str)


def do_cluster(args):
    if args.cluster_command == 'start':
        do_cluster_start(args)
    elif args.cluster_command == 'status':
        do_cluster_status(args)
    elif args.cluster_command == 'stop':
        do_cluster_stop(args)
    elif args.cluster_command == 'extend':
        do_cluster_extend(args)
    elif args.cluster_command == 'reset':
        do_cluster_reset(args)
    else:
        raise CliException("invalid cluster command: {}".format(
            args.cluster_command))


def get_state_file_name():
    home = os.path.expanduser("~")
    return os.path.join(home, '.sawtooth', 'cluster', "state.yaml")


def load_state(start=False):
    file_name = get_state_file_name()
    if os.path.isfile(file_name):
        with open(file_name, 'r') as state_file:
            state = yaml.load(state_file)
    elif start is True:
        state = dict()
        state["DesiredState"] = "Stopped"
    else:
        raise CliException("Missing state file")
    return state


def save_state(state):
    file_name = get_state_file_name()
    with open(file_name, 'w') as state_file:
        yaml.dump(state, state_file, default_flow_style=False)


def get_node_controller(state, args):
    # pylint: disable=redefined-variable-type

    # Get base controller:
    node_controller = None
    if state['Manage'] == 'subprocess':
        node_controller = SubprocessNodeController()
    elif state['Manage'] == 'docker':
        node_controller = DockerNodeController()
    elif state['Manage'] == 'daemon':
        node_controller = DaemonNodeController()
    else:
        raise CliException('invalid management type:'
                           ' {}'.format(state['Manage']))

    # Optionally decorate with WrappedNodeController
    args_wrap = False if not hasattr(args, 'wrap') else args.wrap
    if 'Wrap' not in state.keys():
        # if wrap has not been set in state, set it
        state['Wrap'] = args_wrap
    else:
        # state already knows about a wrapper
        if args_wrap != False and args_wrap != state['Wrap']:
            raise CliException("Already wrapped to %s." % state["Wrap"])
    if state['Wrap'] != False:
        # either args or state have indicated a WrappedNodeController
        if 'ManageWrap' not in state.keys():
            state['ManageWrap'] = None
        node_controller = WrappedNodeController(
                              node_controller, data_dir=state['Wrap'],
                              manage_data_dir=state['ManageWrap'])
        if state['Wrap'] is None:
            state['Wrap'] = node_controller._data_dir
            state['ManageWrap'] = True
        print '{} wrapped to {}'.format(args.cluster_command, state['Wrap'])

    # Return out construction:
    return node_controller


def do_cluster_start(args):
    state = load_state(start=True)

    # Check State for Running validators, if stopped clear out nodes.
    if state["DesiredState"] == "Stopped":
        state["Nodes"] = {}

    if "Manage" not in state:
        if args.manage == "subprocess" or args.manage is None:
            state["Manage"] = "subprocess"
        elif args.manage == "docker":
            state["Manage"] = "docker"
        elif args.manage == "daemon":
            state["Manage"] = "daemon"
    elif args.manage is not None and state['Manage'] != args.manage\
            and state["DesiredState"] == "Running":
        raise CliException("Cannot use two different Manage types.  Already "
                           "running {}.  Try again after running 'sawtooth "
                           "cluster reset'".format(state["Manage"]))

    state["DesiredState"] = "Running"

    node_controller = get_node_controller(state, args)
    node_command_generator = SimpleNodeCommandGenerator()
    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    try:
        existing_nodes = vnm.get_node_names()
    except ManagementError as e:
        raise CliException(str(e))

    for i in xrange(0, args.count):
        node_name = "validator-{:0>3}".format(i)

        if node_name in existing_nodes and vnm.is_running(node_name):
            print "Already running: {}".format(node_name)
            continue

        # genesis is true for the first node
        genesis = (i == 0)
        gossip_port = 5500 + i
        http_port = 8800 + i

        node_args = NodeArguments(node_name, http_port=http_port,
                                  gossip_port=gossip_port, genesis=genesis)
        if node_args.genesis is True:
            node_controller.create_genesis_block(node_args)
        print "Starting: {}".format(node_name)
        node_command_generator.start(node_args)

        state["Nodes"][node_name] = {"Status": "Running", "Index": i}

    save_state(state)

    try:
        vnm.update()
    except ManagementError as e:
        raise CliException(str(e))

    if state["Manage"] == 'subprocess':
        try:
            while True:
                time.sleep(128)
        except KeyboardInterrupt:
            print
            ns = Namespace(cluster_command='stop', command='cluster',
                           node_names=[], verbose=None)
            do_cluster_stop(ns)
            mark = time.time()
            while len(node_controller.get_node_names()) > 0:
                if time.time() - mark > 16:
                    break
                time.sleep(1)
            # force kill anything left over
            for node_name in node_controller.get_node_names():
                try:
                    node_controller.kill(node_name)
                except Exception as e:
                    print e.message


def do_cluster_reset(args):
    state = load_state()

    node_controller = get_node_controller(state, args)
    node_command_generator = SimpleNodeCommandGenerator()
    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    running = node_controller.get_node_names()
    if len(running) != 0:
        raise CliException("Cannot reset with running nodes.  The following "
                           "nodes are still running: {}.  Rerun after calling"
                           "'sawtooth cluster stop'.".format(running))

    if 'ManageWrap' in state.keys() and state['ManageWrap'] is True:
        # node_controller owns CURRENCYHOME; remove it
        node_controller.clean()

    os.remove(get_state_file_name())


def do_cluster_stop(args):
    state = load_state()

    node_controller = get_node_controller(state, args)
    node_command_generator = SimpleNodeCommandGenerator()
    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    if len(args.node_names) > 0:
        node_names = args.node_names
    else:
        node_names = vnm.get_node_names()

    nodes = state["Nodes"]
    for node_name in node_names:
        print "Stopping: {}".format(node_name)
        node_command_generator.stop(node_name)
        # Update status of Nodes
        if node_name in nodes:
            nodes[node_name]["Status"] = "Stopped"
        else:
            nodes[node_name] = {"Status": "Unknown"}

    if len(args.node_names) == 0 and len(node_names) == 0:
        for node_name in nodes:
            nodes[node_name]["Status"] = "Unknown"

    # If none of the nodes are running set overall State to Stopped
    state["DesiredState"] = "Stopped"
    for node in nodes:
        if nodes[node]["Status"] == "Running":
            state["DesiredState"] = "Running"

    # Update state of nodes
    state["Nodes"] = nodes
    save_state(state)

    vnm.update()


def do_cluster_status(args):
    state = load_state()

    node_controller = get_node_controller(state, args)
    node_command_generator = SimpleNodeCommandGenerator()
    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    if len(args.node_names) > 0:
        node_names = args.node_names
    else:
        node_names = vnm.get_node_names()

    # Check expected status of nodes vs what is returned from vnm
    print "NodeName Expected Current"
    nodes = state["Nodes"]
    for node_name in nodes:
        if node_name not in node_names and \
                (nodes[node_name]["Status"] == "Running" or
                    nodes[node_name]["Status"] == "No Response"):
            print "{} {} {}".format(
                node_name, nodes[node_name]["Status"], "Not Running")
        else:
            status = vnm.status(node_name)
            if status == "UNKNOWN" and \
                    nodes[node_name]["Status"] == "Stopped":
                print "{} {} {}".format(node_name, nodes[node_name]["Status"],
                                        status)
            else:
                print "{} {} {}".format(node_name, nodes[node_name]["Status"],
                                        status)


def do_cluster_extend(args):
    state = load_state()

    node_controller = get_node_controller(state, args)
    node_command_generator = SimpleNodeCommandGenerator()
    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    existing_nodes = state["Nodes"]

    desired_stated = state["DesiredState"]

    if desired_stated != "Running":
        raise CliException(
            "You must have a running network.\n" +
            "Use the cluster start command to start a validator network.")

    print "Extending network by {} nodes.".format(args.count)

    index_offset = len(existing_nodes)

    for i in xrange(0, args.count):
        j = i + index_offset
        node_name = "validator-{:0>3}".format(j)

        if node_name in existing_nodes and vnm.is_running(node_name):
            print "Already running: {}".format(node_name)
            continue

        # genesis is true for the first node
        genesis = (j == 0)
        gossip_port = 5500 + j
        http_port = 8800 + j

        print "Starting: {}".format(node_name)
        node_args = NodeArguments(node_name, http_port=http_port,
                                  gossip_port=gossip_port, genesis=genesis)
        node_command_generator.start(node_args)

        state["Nodes"][node_name] = {"Status": "Running", "Index": j}

    save_state(state)

    try:
        vnm.update()
    except ManagementError as e:
        raise CliException(str(e))
