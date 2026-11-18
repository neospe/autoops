
import os
import sys
from pyinfra import host, inventory


# constants

FIRST_IP = os.environ.get('FIRST_IP')
if not FIRST_IP:
    print('NOTICE: please set the FIRST_IP environment variable.')
    exit(1)

first_node = None
for node in inventory:
    if node.name == FIRST_IP or node.data.get('public_ip') == FIRST_IP:
        first_node = node
        break
if not first_node:
    print('ABORTED: FIRST_IP is not in the inventory.')
    exit(1)


# apply the staged layout once all nodes are in, then create key and bucket (first node only)

if str(host) == first_node.name:

    if not host.run_shell_command('garage status')[0]:
        print('ABORTED: garage is not running on the first node.')
        exit(1)

    print('apply node layout')

    cmd_stdout = host.run_shell_command('garage layout show')[1]
    version = [line for line in cmd_stdout if '--version' in line]
    if version:
        host.run_shell_command('garage layout apply --version '+version[-1].split()[-1])
    else:
        print('no staged layout changes')

    cmd_stdout = host.run_shell_command('garage key info autoops')
    if not cmd_stdout[0]:
        print('creating key: garage key create autoops')
        cmd_stdout = host.run_shell_command('garage key create autoops')[1]
        print('\n'.join(cmd_stdout) + '\n\n+++++++ SAVE THIS KEY NOW +++++++\n\n')
        print('creating bucket: garage bucket create autoops')
        host.run_shell_command('garage bucket create autoops')
        cmd_stdout = host.run_shell_command('garage bucket allow --read --write --owner autoops --key autoops')[1]
        print('\n'.join(cmd_stdout))
