
import sys
from pyinfra import host
from pyinfra.operations import server


# compose up

print('compose up')

host.run_shell_command('cd /containers/build && docker compose up -d')


# start traefik-kop (installed by services.py on hosts without traefik, one per bastion), now that the containers are up

server.shell(name='start traefik-kop', commands=['for f in /etc/traefik-kop/*.env; do [ -e "$f" ] && systemctl restart traefik-kop@$(basename "$f" .env); done; true'])


# clean up (iff compose not needed for operations anymore)
#host.run_shell_command('rm -rf /containers/build')
