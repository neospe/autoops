
import sys
from pyinfra import host
from pyinfra.operations import server


# compose up

print('compose up')

host.run_shell_command('cd /containers/build && docker compose up -d')


# start traefik-kop (installed by services.py on hosts without traefik), now that the containers are up

server.shell(name='start traefik-kop', commands=['if [ -f /etc/systemd/system/traefik-kop.service ]; then systemctl restart traefik-kop; fi'])


# clean up (iff compose not needed for operations anymore)
#host.run_shell_command('rm -rf /containers/build')
