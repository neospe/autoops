
import os
import sys
import json
from time import sleep
from pyinfra import host
from pyinfra.operations import files, server
from socket import gethostbyname


cmd_stdout = host.run_shell_command('systemctl status wesher')[1]
if 'Active: active' in '\n'.join(cmd_stdout):
    print('NOTICE: wesher service is already running.')
    exit(1)


# constants

FIRST_IP = os.environ['FIRST_IP']
if FIRST_IP is None:
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
CURRENT_IS_FIRST = (str(host) == first_node[0][0])
CURRENT_BEHIND_NAT = host.data.get('behind_nat', False)
FIRST_DATA = first_node[0][1]
FIRST_BEHIND_NAT = FIRST_DATA.get('behind_nat', False)

if FIRST_BEHIND_NAT:
    FIRST_LOCAL_IP = first_node[0][0]
    if 'public_ip' in FIRST_DATA:
        FIRST_IP = FIRST_DATA['public_ip']

if 'public_dns' in FIRST_DATA:
    FIRST_IP = gethostbyname(FIRST_DATA['public_dns'])

if not CURRENT_IS_FIRST and CURRENT_BEHIND_NAT:
    CURRENT_LOCAL_IP = str(host)
    if 'public_ip' in host.data:
        FIRST_IP = host.data.get('public_ip')

if not CURRENT_IS_FIRST and 'public_dns' in host.data:
    CURRENT_IP = gethostbyname(host.data.get('public_dns'))

ARCH = host.run_shell_command('uname -m')[1][0]


# place binary

files.put(
    name='setup binary',
    src='./assets/'+ARCH+'/wesher',
    dest='/usr/local/bin/wesher',
)

host.run_shell_command('chmod +x /usr/local/bin/wesher')


# start or connect to cluster

if CURRENT_IS_FIRST:  # setup the first node

    if FIRST_BEHIND_NAT:
        host.run_shell_command('(wesher --advertise-addr='+FIRST_IP+' &) && sleep 5 && pkill wesher')  # behind a NAT -> advertise public ip
    else:
        host.run_shell_command('(wesher &) && sleep 5 && pkill wesher')

else:  # setup another node
    
    with open('./assets/wgoverlay.json', 'r', encoding='utf-8') as f:
        w_config = json.load(f)

    if not w_config['Nodes']:
        nodes = FIRST_IP
    else:
        nodes = ','.join([node['Addr'] for node in w_config['Nodes'] if node['Addr'] != CURRENT_IP and not node['Addr'].startswith('192.168.')])  # connect to all other nodes
        if nodes == '':
            nodes = FIRST_IP
        else:
            if FIRST_BEHIND_NAT:
                if FIRST_LOCAL_IP in nodes:
                    nodes = nodes.replace(FIRST_LOCAL_IP, FIRST_IP)
            if not CURRENT_IS_FIRST and CURRENT_BEHIND_NAT:
                if CURRENT_LOCAL_IP in nodes:
                    nodes = nodes.replace(CURRENT_LOCAL_IP, CURRENT_IP)
            else:
                nodes += ','+FIRST_IP
    
    host.run_shell_command('(wesher --cluster-key '+w_config['ClusterKey']+' --join '+nodes+' &) && sleep 5 && pkill wesher')


# enable systemd service

files.put(
    name='setup service',
    src='./assets/wesher.service',
    dest='/etc/systemd/system/wesher.service',
)

if FIRST_BEHIND_NAT and CURRENT_IS_FIRST:

    # update wesher state file
    w_config = '\n'.join(host.run_shell_command('cat /var/lib/wesher/wgoverlay.json')[1])
    if FIRST_LOCAL_IP in w_config:
        files.line(
            name='patch wgoverlay.json',
            path='/var/lib/wesher/wgoverlay.json',
            line='"Addr": "'+FIRST_LOCAL_IP+'",',
            replace='"Addr": "'+FIRST_IP+'",'
        )
        w_config = w_config.replace(FIRST_LOCAL_IP, FIRST_IP)
    with open('./assets/wgoverlay.json', 'w', encoding='utf-8') as f:
        f.write(w_config)

    # update wesher service file
    files.line(
        name='patch wesher.service',
        path='/etc/systemd/system/wesher.service',
        line='ExecStart=/usr/local/bin/wesher',
        replace='ExecStart=/usr/local/bin/wesher --advertise-addr='+FIRST_IP
    )

host.run_shell_command('ip a show wgoverlay > $HOME/wgoverlay-ip')

# start service
server.shell(
    name='starting',
    commands=[
        'systemctl daemon-reload',
        'systemctl enable wesher',
        'systemctl start wesher',
        ]
)
