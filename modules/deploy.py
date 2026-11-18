
import os
import sys
import json
from time import sleep
from gevent.lock import Semaphore
from pyinfra import host, state

SERVICE = os.environ.get('SERVICE')
if not SERVICE:
    print('NOTICE: please set the SERVICE environment variable.')
    exit(1)

# hosts are prepared in parallel; swap containers one host at a time, so a service running on
# several hosts behind traefik stays reachable (builds still run in parallel)
if not hasattr(state, 'autoops_deploy_lock'):
    state.autoops_deploy_lock = Semaphore()

if SERVICE not in host.data.get('services', []):
    print('skipping, not a service of this host:', SERVICE)

else:

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
    cmd_stdout = host.run_shell_command('cd /containers/build/'+SERVICE+' && docker build --no-cache -t '+img_name_tmp+' -f Dockerfile .')
    if not cmd_stdout[0]:
        print('build failed.')
        exit(1)


    with state.autoops_deploy_lock:

        print('removing old')
        cmd_stdout = host.run_shell_command('docker rm -f '+con_names_str+' && docker rmi '+img_name)
        if not cmd_stdout[0]:
            print('removing failed.')
            exit(1)


        print('starting new')
        cmd_stdout = host.run_shell_command('docker image tag '+img_name_tmp+':latest '+img_name+':latest && docker rmi '+img_name_tmp+' && cd /containers/build && docker compose up -d '+SERVICE)
        if not cmd_stdout[0]:
            print('starting failed.')
            exit(1)

        # wait until the new container runs (and is healthy, if it has a healthcheck)
        for _ in range(30):
            cmd_stdout = host.run_shell_command("docker inspect -f '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "+con_names_str)[1]
            if cmd_stdout and all(line.split()[0] == 'true' and line.split()[1:] in ([], ['healthy']) for line in cmd_stdout):
                break
            sleep(2)
        else:
            print('new container not running, stopping here:', con_names_str)
            exit(1)


    if SERVICE == 'traefik':
        print('clearing cache')
        host.run_shell_command('rm -rf /containers/traefik/traefik-cache/*')
