
import sys
from pyinfra import host


# compose up

print('compose up')

host.run_shell_command('cd /containers/build && docker compose up -d')


# clean up (iff compose not needed for operations anymore)
#host.run_shell_command('rm -rf /containers/build')
