
import os
import sys
import json
from pyinfra import host

SERVICE = os.environ.get('SERVICE')
if not SERVICE:
    print('NOTICE: please set the SERVICE environment variable.')
    exit(1)

print('collecting info')
con_names = []
img_names = []
cmd_stdout = host.run_shell_command('docker ps --filter "name='+SERVICE+'" --format "{{json . }}"')
if cmd_stdout[0]:
    for line in cmd_stdout[1]:
        line_dict = json.loads(line)
        con_names.append(line_dict['Names'])
        img_names.append(line_dict['Image'])
else:
    print('no running container found:', SERVICE)
    exit(1)

img_names = list(set(img_names))
assert len(img_names) == 1  # we seek to replace exactly one image and its containers
img_name = img_names[0]
img_name_tmp = img_names[0]+'-x'
con_names_str = ' '.join(con_names)


print('building new')
host.run_shell_command('cd /containers/build/'+SERVICE+' && docker build --no-cache -t '+img_name_tmp+' -f Dockerfile .')
if not cmd_stdout[0]:
    print('build failed.')
    exit(1)


print('removing old')
host.run_shell_command('docker rm -f '+con_names_str+' && docker rmi '+img_name)
if not cmd_stdout[0]:
    print('removing failed.')
    exit(1)


print('starting new')
host.run_shell_command('docker image tag '+img_name_tmp+':latest '+img_name+':latest && docker rmi '+img_name_tmp+' && cd /containers/build && docker compose up -d '+SERVICE)
if not cmd_stdout[0]:
    print('starting failed.')
    exit(1)


if SERVICE in ['traefik', 'webapp']:
    print('clearing cache')
    host.run_shell_command('rm -rf /containers/traefik/traefik-cache/*')
