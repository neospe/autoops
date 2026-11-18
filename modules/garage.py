
import os
import sys
from io import StringIO
from time import sleep
from pyinfra import host, inventory
from socket import gethostbyname


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

CURRENT_IP = str(host)
CURRENT_IS_FIRST = (str(host) == first_node.name)
CURRENT_ZONE = host.data.get('zone')
CURRENT_BEHIND_NAT = host.data.get('behind_nat', False)
CURRENT_HOSTNAME = host.data.get('hostname', False)
if not CURRENT_HOSTNAME or not CURRENT_ZONE:
    print('ABORTED: a hostname and a zone are needed in the inventory.')
    exit(1)
FIRST_DATA = first_node.data
FIRST_BEHIND_NAT = FIRST_DATA.get('behind_nat', False)
ARCH = host.run_shell_command('uname -m')[1][0]

if FIRST_BEHIND_NAT:
    FIRST_LOCAL_IP = first_node.name
    if FIRST_DATA.get('public_ip'):
        FIRST_IP = FIRST_DATA.get('public_ip')

if FIRST_DATA.get('public_dns'):
    FIRST_IP = gethostbyname(FIRST_DATA.get('public_dns'))

cmd_stdout = host.run_shell_command('ip -4 -o addr show wgoverlay')[1]
WESHER_IP = cmd_stdout[0].split()[3].split('/')[0] if cmd_stdout else False

# one rpc secret for the whole cluster, kept next to the other local state in assets/
if not os.path.exists('./assets/garage-rpc-secret'):
    with open('./assets/garage-rpc-secret', 'w') as f:
        f.write(os.urandom(32).hex())
with open('./assets/garage-rpc-secret', 'r') as f:
    RPC_SECRET = f.read().strip()


# place binary (immediately: the steps below run it while the deploy is still being prepared)

host.put_file('./assets/'+ARCH+'/garage', '/usr/local/bin/garage.new')  # a running binary can't be overwritten, only replaced
host.run_shell_command('chmod +x /usr/local/bin/garage.new && mv -f /usr/local/bin/garage.new /usr/local/bin/garage')
host.run_shell_command('mkdir -p /var/lib/garage')


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

config = config.replace('<< GARAGE_ADDR >>', GARAGE_ADDR).replace('<< RPC_SECRET >>', RPC_SECRET)

if ARCH == 'aarch64' and 'rpi' in CURRENT_HOSTNAME:
    config = config.replace('db_engine = "lmdb"', 'db_engine = "sqlite"')

host.put_file(StringIO(config), '/etc/garage.toml')


# enable systemd service

host.put_file('./assets/garage.service', '/etc/systemd/system/garage.service')

host.run_shell_command('systemctl daemon-reload')
host.run_shell_command('systemctl enable garage')
host.run_shell_command('systemctl restart garage')

for _ in range(30):
    status, cmd_stdout, _ = host.run_shell_command('garage node id -q')
    if status:
        current_node_id = cmd_stdout[0].strip()
        break
    sleep(2)
else:
    print('ABORTED: garage did not start.')
    exit(1)


# connect to the cluster

if not CURRENT_IS_FIRST:

    # wait for the first node; all hosts are prepared in parallel

    if not first_node.connected:
        first_node.connect()
    for _ in range(60):
        status, cmd_stdout, _ = first_node.run_shell_command('garage node id -q')
        if status:
            break
        sleep(5)
    else:
        print('ABORTED: garage is not running on the first node.')
        exit(1)

    print('connect to the first node')
    host.run_shell_command('garage node connect '+cmd_stdout[0].strip())


# stage this node in the layout; garage-layout.py applies it on the first node

print('update node layout')

host.run_shell_command('garage layout assign '+current_node_id.split('@')[0][:16]+' -z '+CURRENT_ZONE+' -c 1GB -t '+CURRENT_HOSTNAME)  # capacity is a relative weight
