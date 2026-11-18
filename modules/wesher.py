
import os
import sys
import json
from time import sleep
from pyinfra import host, inventory
from socket import gethostbyname


cmd_stdout = host.run_shell_command('systemctl is-active wesher')[1]
if cmd_stdout == ['active']:
    print('NOTICE: wesher service is already running.')
    exit(1)


# constants

STATE_PATH = '/var/lib/wesher/state.json'  # upstream wesher; adjust if your build keeps state elsewhere

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

CURRENT_IP = str(host)
CURRENT_IS_FIRST = (str(host) == first_node.name)
CURRENT_BEHIND_NAT = host.data.get('behind_nat', False)
FIRST_DATA = first_node.data
FIRST_BEHIND_NAT = FIRST_DATA.get('behind_nat', False)

if FIRST_BEHIND_NAT:
    FIRST_LOCAL_IP = first_node.name
    if FIRST_DATA.get('public_ip'):
        FIRST_IP = FIRST_DATA.get('public_ip')

if FIRST_DATA.get('public_dns'):
    FIRST_IP = gethostbyname(FIRST_DATA.get('public_dns'))

if not CURRENT_IS_FIRST and CURRENT_BEHIND_NAT:
    CURRENT_LOCAL_IP = str(host)
    if host.data.get('public_ip'):
        CURRENT_IP = host.data.get('public_ip')

if not CURRENT_IS_FIRST and host.data.get('public_dns'):
    CURRENT_IP = gethostbyname(host.data.get('public_dns'))

ARCH = host.run_shell_command('uname -m')[1][0]


# place binary (immediately: the steps below run it while the deploy is still being prepared)

host.put_file('./assets/'+ARCH+'/wesher', '/usr/local/bin/wesher')
host.run_shell_command('chmod +x /usr/local/bin/wesher')


# start or connect to cluster

if CURRENT_IS_FIRST:  # setup the first node

    if FIRST_BEHIND_NAT:
        host.run_shell_command('(wesher --advertise-addr='+FIRST_IP+' &) && sleep 5 && pkill wesher')  # behind a NAT -> advertise public ip (needs neospe/wesher)
    else:
        host.run_shell_command('(wesher &) && sleep 5 && pkill wesher')

else:  # setup another node

    # wait for the first node; all hosts are prepared in parallel
    if not first_node.connected:
        first_node.connect()
    for _ in range(60):
        status, cmd_stdout, _ = first_node.run_shell_command('systemctl is-active wesher && cat '+STATE_PATH)
        if status:
            break
        sleep(5)
    else:
        print('ABORTED: wesher is not running on the first node.')
        exit(1)
    w_config = json.loads('\n'.join(cmd_stdout[1:]))

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

host.put_file('./assets/wesher.service', '/etc/systemd/system/wesher.service')

if FIRST_BEHIND_NAT and CURRENT_IS_FIRST:

    # update wesher state file
    host.run_shell_command("sed -i 's/\"Addr\": \""+FIRST_LOCAL_IP+"\"/\"Addr\": \""+FIRST_IP+"\"/' "+STATE_PATH)

    # update wesher service file
    host.run_shell_command("sed -i 's|^ExecStart=/usr/local/bin/wesher$|ExecStart=/usr/local/bin/wesher --advertise-addr="+FIRST_IP+"|' /etc/systemd/system/wesher.service")

# start service
host.run_shell_command('systemctl daemon-reload && systemctl enable wesher && systemctl start wesher')
