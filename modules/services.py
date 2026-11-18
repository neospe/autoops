
import os
import re
import sys
import subprocess
from io import StringIO
from time import sleep
from pyinfra import host, inventory
from pyinfra.operations import files, server, apt


# get data

TARGET_GROUP = host.groups[0]
CURRENT_IP = str(host)
CURRENT_HOSTNAME = host.data.get('hostname', False)
ARCH = host.run_shell_command('uname -m')[1][0]
SERVICES = host.data.get('services', [])
if 'traefik' not in SERVICES:
    TRAEFIK_IP = host.data.get('traefik_host', False)
DOCKERFILES_PATH = os.environ.get('DOCKERFILES_PATH')
if not DOCKERFILES_PATH:
    print('NOTICE: please set the DOCKERFILES_PATH environment variable.')
    exit(1)
DOCKERFILES_TARGET_PATH = '/containers/build'


# get overlay ip

cmd_stdout = host.run_shell_command('ip -4 -o addr show wgoverlay')[1]
OVERLAY_IP = cmd_stdout[0].split()[3].split('/')[0] if cmd_stdout else False
if not OVERLAY_IP:
    print('ABORTED: failed to look up overlay ip.')
    exit(1)


# put files

print('put service files')

files.directory(
    path=DOCKERFILES_TARGET_PATH,
    present=True
)

# configure log directory

files.directory(
    path='/containers/log',
    present=True
)

files.put(
    src='./assets/logrotate-containers',
    dest='/etc/logrotate.d/containers',
)

# configure services

for service in SERVICES:

    if os.path.exists(DOCKERFILES_PATH+'/'+service):
        files.sync(
            name=service,
            src=DOCKERFILES_PATH+'/'+service,
            dest=DOCKERFILES_TARGET_PATH+'/'+service,
            delete=True,
            add_deploy_dir=False
        )

    if service == 'traefik':
        server.shell(name='traefik files', commands=['mkdir -p /containers/traefik && touch /containers/log/access.log /containers/log/traefik.log /containers/traefik/acme.json && chmod 600 /containers/traefik/acme.json && if [ -f /containers/build/traefik/traefik-dynamic.toml ]; then mv /containers/build/traefik/traefik-dynamic.toml /containers/traefik/traefik-dynamic.toml; fi'])

        # install crowdsec

        apt.packages(name='install packages', packages=['crowdsec'])

        # install crowdsec bouncer if available (crowdsec repo or debian), else download
        cmd_stdout = host.run_shell_command('apt-cache search --names-only "^crowdsec-firewall-bouncer"')[1]
        bouncers = [line.split()[0] for line in cmd_stdout]
        if 'crowdsec-firewall-bouncer-iptables' in bouncers:
            apt.packages(packages=['crowdsec-firewall-bouncer-iptables'])
        elif 'crowdsec-firewall-bouncer' in bouncers:
            apt.packages(packages=['crowdsec-firewall-bouncer'])  # debian's package runs in nftables mode (set in its .yaml.local), which also covers host-network containers
        else:

            # find out debian codename
            cmd_stdout = host.run_shell_command('lsb_release -a')[1]
            for line in cmd_stdout:
                if line.startswith('Codename:'):
                    codename = line.split()[1]
            assets_path = 'assets/'+codename+'/'

            # assert path
            if not os.path.exists(assets_path):
                os.mkdir(assets_path)

            # parse packagecloud results page (curl honours ALL_PROXY)
            url = 'https://packagecloud.io/app/crowdsec/crowdsec/search?q=crowdsec-firewall-bouncer-iptables&filter=all&filter=all&dist='+codename
            response = subprocess.run(['curl', '-fsSL', url], capture_output=True, text=True).stdout
            versions = re.findall(r'crowdsec-firewall-bouncer-iptables_([^_<"]+)_amd64\.deb', response)
            if not versions:
                print('error finding crowdsec-firewall-bouncer-iptables:', url)
                exit(1)
            version = versions[0]

            # cache package in assets dir
            filename = 'crowdsec-firewall-bouncer-iptables_'+version+'_amd64.deb'
            url = 'https://packagecloud.io/crowdsec/crowdsec/packages/debian/'+codename+'/'+filename+'/download.deb'
            if not os.path.exists(assets_path+filename):
                err = os.system('curl -fsSL -o '+assets_path+filename+' '+url)
                if err != 0:
                    print('error downloading packages:', url)
                    exit(1)

            # copy package to host
            files.put(
                src=assets_path+filename,
                dest='/root/'+filename,
            )

            # install package
            server.shell(name='install crowdsec bouncer', commands=['dpkg -i /root/'+filename+' && rm /root/'+filename])

        # update config
        files.put(
            src='./assets/crowdsec-acquis.yaml',
            dest='/etc/crowdsec/acquis.yaml',
        )

        # restart service
        server.shell(name='restart crowdsec', commands=['systemctl restart crowdsec'])

        # for docker services: add crowdsec blacklist to DOCKER-USER chain (iptables mode)
        files.line(
            name='update crowdsec-firewall-bouncer config',
            path='/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml',
            line='disable_ipv6: false',
            replace='disable_ipv6: true'
        )
        files.line(
            name='update crowdsec-firewall-bouncer config',
            path='/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml',
            line='#  - DOCKER-USER',
            replace='  - DOCKER-USER'
        )
        server.shell(name='restart crowdsec bouncer', commands=['systemctl restart crowdsec-firewall-bouncer'])

    if service == 'postgres':
        server.shell(name='postgres files', commands=['touch /containers/log/postgresql.log && mkdir -p /containers/postgres/init'])

    if service == 'redis':
        server.shell(name='redis files', commands=['mkdir -p /containers/redis && touch /containers/log/redis.log && if [ -f /containers/build/redis/redis.rdb ]; then mv /containers/build/redis/redis.rdb /containers/redis/redis.rdb && chmod 644 /containers/redis/redis.rdb; fi'])

    if service == 'webapp':
        server.shell(name='webapp files', commands=['touch /containers/log/webapp.log && mv /containers/build/webapp/webapp.sql /containers/postgres/init && chown 70:70 /containers/postgres/init/webapp.sql'])

    if service == 'torchserve':
        server.shell(name='torchserve files', commands=['touch /containers/log/access_log.log /containers/log/ts_log.log'])

    if service == 'mattermost':
        server.shell(name='mattermost files', commands=['mkdir -p /containers/mattermost/config && mkdir -p /containers/mattermost/data && mkdir -p /containers/mattermost/logs && mkdir -p /containers/mattermost/plugins && mkdir -p /containers/mattermost/client/plugins && mkdir -p /containers/mattermost/bleve-indexes && chown -R 2000:2000 /containers/mattermost && mv /containers/build/mattermost/mattermost.sql /containers/postgres/init && chown 70:70 /containers/postgres/init/mattermost.sql && chmod +x /containers/build/mattermost/entrypoint.sh'])

        if os.path.exists('./assets/mattermost-config.json'):
            files.put(
                src='./assets/mattermost-config.json',
                dest='/containers/mattermost/config/config.json',
            )
            server.shell(name='mattermost config', commands=['chown -R 2000:2000 /containers/mattermost/config/config.json'])


# compile compose file

print('compile compose file')

with open(DOCKERFILES_PATH+'/'+TARGET_GROUP+'.yml', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('<< OVERLAY_IP >>', OVERLAY_IP)
if CURRENT_HOSTNAME:
    content = content.replace('<< HOSTNAME >>', CURRENT_HOSTNAME)
for name in set(re.findall(r'<< (\w+) >>', content)):  # everything else from the environment
    if name in os.environ:
        content = content.replace('<< '+name+' >>', os.environ[name])
    else:
        print('NOTICE: << '+name+' >> in '+TARGET_GROUP+'.yml is not set in the environment.')

files.put(
    src=StringIO(content),
    dest=DOCKERFILES_TARGET_PATH+'/docker-compose.yml',
    force=True
)


# install traefik-kop

if 'traefik' not in SERVICES:

    REDIS_PWD = os.environ.get('REDIS_PWD')

    if not TRAEFIK_IP or not CURRENT_HOSTNAME or not REDIS_PWD:
        print('NOTICE: for traefik-kop, set hostname and traefik_host in the inventory, as well as the REDIS_PWD environment variable.')
        exit(1)

    # get traefik overlay ip

    traefik_node = inventory.get_host(TRAEFIK_IP)
    if not traefik_node.connected:
        traefik_node.connect()
    cmd_stdout = traefik_node.run_shell_command('ip -4 -o addr show wgoverlay')[1]
    TRAEFIK_OVERLAY_IP = cmd_stdout[0].split()[3].split('/')[0] if cmd_stdout else False

    if not TRAEFIK_OVERLAY_IP:
        print('ABORTED: failed to look up overlay ip.')
        exit(1)

    # setup traefik-kop

    files.put(
        name='setup traefik-kop',
        src='./assets/'+ARCH+'/traefik-kop',
        dest='/usr/local/bin/traefik-kop',
        mode='755',
    )

    with open('./assets/traefik-kop.service', 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('<< HOSTNAME >>', CURRENT_HOSTNAME).replace('<< TRAEFIK_IP >>', TRAEFIK_OVERLAY_IP).replace('<< REDIS_IP >>', TRAEFIK_OVERLAY_IP+':6379').replace('<< REDIS_PWD >>', REDIS_PWD).replace('<< OVERLAY_IP >>', OVERLAY_IP)

    files.put(
        src=StringIO(content),
        dest='/etc/systemd/system/traefik-kop.service',
        force=True
    )

    server.shell(name='enable traefik-kop', commands=['systemctl daemon-reload', 'systemctl enable traefik-kop'])


# install docker-rollout (currently handled by deploy.py)
"""
print('setup docker-rollout')

files.directory(
    name='setup docker-rollout',
    path='/root/.docker/cli-plugins',
    present=True,
)

files.put(
    src='./assets/docker-rollout',
    dest='/root/.docker/cli-plugins/docker-rollout',
)

host.run_shell_command('chmod +x /root/.docker/cli-plugins/docker-rollout')
"""
