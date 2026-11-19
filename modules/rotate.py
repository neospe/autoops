
import os
import sys
from datetime import date
from pyinfra import host, inventory, state
from pyinfra.operations import server


# rotate a cluster secret: KEY=garage-rpc (all nodes at once) or KEY=s3 (first node)
# the redis password is rotated by running services and services-up with a new REDIS_PWD

KEY = os.environ.get('KEY')
if KEY not in ('garage-rpc', 's3'):
    print('NOTICE: please set KEY to garage-rpc or s3.')
    exit(1)


if KEY == 'garage-rpc':

    # one new secret for all hosts (hosts are prepared in parallel, the first one writes it)
    if not hasattr(state, 'autoops_rpc_secret'):
        state.autoops_rpc_secret = os.urandom(32).hex()
        with os.fdopen(os.open('./assets/garage-rpc-secret', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
            f.write(state.autoops_rpc_secret)

    # nodes with different secrets can't talk: change and restart on all nodes in the same step
    server.shell(
        name='rotate garage rpc secret',
        commands=["sed -i 's/^rpc_secret = .*/rpc_secret = \""+state.autoops_rpc_secret+"\"/' /etc/garage.toml",
                  'systemctl restart garage',
                  'for i in $(seq 30); do garage status >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1']
    )


if KEY == 's3':

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

    if str(host) == first_node.name:

        RETIRE = os.environ.get('RETIRE')
        if RETIRE:  # second step, once the services use the new key
            print('deleting key:', RETIRE)
            cmd_stdout = host.run_shell_command('garage key delete --yes '+RETIRE)
            print('\n'.join(cmd_stdout[1]))
            if not cmd_stdout[0]:
                exit(1)

        else:  # first step: a new key next to the old one
            name = 'autoops-'+date.today().strftime('%Y%m%d')
            print('creating key: garage key create', name)
            cmd_stdout = host.run_shell_command('garage key create '+name)
            if not cmd_stdout[0]:
                print('creating key failed.')
                exit(1)
            print('\n'.join(cmd_stdout[1]) + '\n\n+++++++ SAVE THIS KEY NOW +++++++\n\n')
            cmd_stdout = host.run_shell_command('garage bucket allow --read --write --owner autoops --key '+name)[1]
            print('\n'.join(cmd_stdout))
