
import sys
from pyinfra import host
from pyinfra.operations import server, files, apt


# setup system

apt.update(name='update apt repositories')
apt.upgrade(name='upgrade apt repositories')
apt.packages(name='install packages', packages=['ufw', 'grep', 'sed'])

if host.data.get('hostname'):
    server.hostname(name='set hostname', hostname=host.data.get('hostname'))

files.line(
    name='update logrotate config',
    path='/etc/logrotate.conf',
    line='rotate 4',
    replace='rotate 2'  # keep 2 weeks instead of 4
)

files.line(
    name='update journald config',
    path='/etc/systemd/journald.conf',
    line='#SystemMaxUse=',
    replace='SystemMaxUse=100M'  # keep max. 100mb of logs
)
server.shell(name='restart journald', commands=['systemctl restart systemd-journald'])

server.shell(
    name='setting up ufw',
    commands=[
        'ufw default deny incoming',
        'ufw default allow outgoing',
        'ufw allow '+str(host.data.get('ssh_port', 22))+'/tcp',  # before enabling, or we lock ourselves out
        'ufw allow http',
        'ufw allow https',
        'ufw allow 7946',
        'ufw allow 51820',
        'ufw allow in on wgoverlay',  # the overlay network is trusted: services, redis, garage rpc
        'ufw --force enable'
        ]
)
