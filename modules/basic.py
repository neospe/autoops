
import sys
from pyinfra import host
from pyinfra.operations import server, files, apt


# setup system

apt.update(name='update apt repositories')
apt.upgrade(name='upgrade apt repositories')
apt.packages(name='install packages', packages=['ufw', 'grep', 'sed'])

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
host.run_shell_command('systemctl restart systemd-journald')

server.shell(
    name='setting up ufw',
    commands=[
        'ufw default deny incoming',
        'ufw default allow outgoing',
        'ufw allow http',
        'ufw allow https',
        'ufw allow 3900',
        'ufw allow 3901',
        'ufw allow 3902',
        'ufw allow 7946',
        'ufw allow 51820',
        'ufw --force enable'
        ]
)

