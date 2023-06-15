
import os
import sys
import json
from io import StringIO
from pyinfra import host
from pyinfra.operations import files, ssh
import importlib


# constants

FIRST_IP = os.environ['FIRST_IP']
if not FIRST_IP:
    print('NOTICE: please set the FIRST_IP environment variable.')
    exit(1)

inv = importlib.import_module('inventory')
for group in [getattr(inv, a) for a in dir(inv) if not a.startswith('_')]:
    if group[0][0] == FIRST_IP:
        first_node = group
        break
    if group[0][1]['public_ip'] == FIRST_IP:
        first_node = group
        break

CURRENT_IP = str(host)
CURRENT_ZONE = host.data.get('zone')
CURRENT_BEHIND_NAT = host.data.get('behind_nat', False)
CURRENT_HOSTNAME = host.data.get('hostname', False)
if not CURRENT_HOSTNAME:
    print('ABORTED: a hostname is needed in the inventory.')
    exit(1)
FIRST_DATA = first_node[0][1]
FIRST_BEHIND_NAT = FIRST_DATA.get('behind_nat', False)
ARCH = host.run_shell_command('uname -m')[1][0]

if FIRST_BEHIND_NAT:
    FIRST_LOCAL_IP = first_node[0][0]
    if 'public_ip' in FIRST_DATA:
        FIRST_IP = FIRST_DATA['public_ip']

if 'public_dns' in FIRST_DATA:
    FIRST_IP = gethostbyname(FIRST_DATA['public_dns'])

cmd_stdout = host.run_shell_command('ip a show wgoverlay')[1]
WESHER_IP = cmd_stdout[2].split('/')[0].split()[-1]


# place binary

files.put(
    name='setup binary',
    src='./assets/'+ARCH+'/garage',
    dest='/usr/local/bin/garage',
)

host.run_shell_command('chmod +x /usr/local/bin/garage')
host.run_shell_command('mkdir /var/lib/garage')


# determine bind address

# outside the overlay network: make a LAN connection if possible
GARAGE_ADDR = False
if CURRENT_BEHIND_NAT and CURRENT_IP != FIRST_IP and FIRST_BEHIND_NAT:
    GARAGE_ADDR = CURRENT_IP

# else: get overlay network ip
if not GARAGE_ADDR:
    GARAGE_ADDR = WESHER_IP

# catch-all
if not GARAGE_ADDR:
    GARAGE_ADDR = '[::]'


# patch config

with open('./assets/garage.toml', 'r') as f:
    config = f.read()

config = config.replace('<< GARAGE_ADDR >>', GARAGE_ADDR).replace('<< RPC_SECRET >>', os.urandom(32).hex())

if ARCH == 'aarch64' and 'rpi' in CURRENT_HOSTNAME:
    config = config.replace('db_engine = "lmdb"', 'db_engine = "sled"')

files.put(
    name='configuring',
    src=StringIO(config),
    dest='/etc/garage.toml',
)


# enable systemd service

files.put(
    name='setup service',
    src='./assets/garage.service',
    dest='/etc/systemd/system/garage.service',
)

host.run_shell_command('systemctl daemon-reload')
host.run_shell_command('systemctl enable garage')
host.run_shell_command('systemctl start garage')


# connect to the cluster

if CURRENT_IP != FIRST_IP: 

    # get cluster status

    ssh.command(
        name='get garage cluster status',
        hostname=FIRST_IP,
        command="garage status > $HOME/garage-status",
        port=22,
        user=FIRST_DATA['ssh_user']
    )

    ssh.download(
         hostname: FIRST_IP,
         filename: 'garage-status',
         local_filename: '$HOME/garage-status',
         port=22,
         user: FIRST_DATA['ssh_user'],
         ssh_keyscan=True
    )
    
    g_status = host.run_shell_command('cat $HOME/garage-status')[1]
    nodes = {}
    for line in g_status:
        if line == '':
            break
        if not line.startswith('==') and not line.startswith('ID'):
            node_info = line.split()  # node id, hostname, ..
            nodes[node_info[1]] = node_info[0]

    # connect to all other nodes

    print('connect to other nodes')

    for node_name, node_id in nodes.items():
        host.run_shell_command('garage node connect '+node_id+'@'+node_name+':3901')

    # update node layout

    print('update node layout')

    cmd_stdout = host.run_shell_command('garage node id')[1]
    if cmd_stdout != []:  # we have to ignore empty output for pyinfra's dry run / fact gathering phase to work
        current_node_id = cmd_stdout[0].strip()

        cmd_stdout = host.run_shell_command('garage layout assign '+current_node_id[:4]+' -z '+CURRENT_ZONE+' -c 1 -t '+CURRENT_HOSTNAME)[1]
        version = cmd_stdout[-1].split()[-1]
        host.run_shell_command('garage layout apply --version '+version)

else:

    # this is the first node

    print('creating key: garage key new --name autoops')
    cmd_stdout = host.run_shell_command('garage key new --name autoops')[1]
    print(cmd_stdout + '\n\n+++++++ SAVE THIS KEY NOW +++++++\n\n')
    print('creating bucket: garage bucket allow --read --write --owner autoops --key autoops')
    cmd_stdout = host.run_shell_command('garage bucket allow --read --write --owner autoops --key autoops')[1]
    print(cmd_stdout)
    
