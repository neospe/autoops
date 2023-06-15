
import os
import sys
import requests
from bs4 import BeautifulSoup
from io import StringIO
from pyinfra import host
from pyinfra.operations import files, ssh, apt


# get data

TARGET_GROUP = host.groups[0]
CURRENT_IP = str(host)
CURRENT_HOSTNAME = host.data.get('hostname', False)
ARCH = host.run_shell_command('uname -m')[1][0]
SERVICES = host.data.get('services')
if 'traefik' not in SERVICES:
    TRAEFIK_IP = host.data.get('traefik_host', False)
DOCKERFILES_PATH = os.environ['DOCKERFILES_PATH']
if DOCKERFILES_PATH is None:
    print('NOTICE: please set the DOCKERFILES_PATH environment variable.')
    exit(1)
DOCKERFILES_TARGET_PATH = '/containers/build'


# get overlay ip

cmd_stdout = host.run_shell_command('ip a show wgoverlay')[1]
OVERLAY_IP = cmd_stdout[2].split('/')[0].split()[-1]
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
        host.run_shell_command('touch /containers/log/access.log /containers/log/traefik.log /containers/traefik/acme.json && chmod 600 /containers/traefik/acme.json && mv /containers/build/traefik/traefik-dynamic.toml /containers/traefik/traefik-dynamic.toml')

        # install crowdsec
        
        apt.packages(name='install packages', packages=['crowdsec'])
        
        # install crowdsec bouncer if available, else download
        cmd_stdout = host.run_shell_command('apt-cache search crowdsec-firewall-bouncer-iptables')[1]
        if cmd_stdout != []:
            apt.packages(packages=['crowdsec-firewall-bouncer-iptables'])
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
            
            # parse packagecloud results page
            url = 'https://packagecloud.io/app/crowdsec/crowdsec/search?q=crowdsec-firewall-bouncer-iptables&filter=all&filter=all&dist='+codename
            response = requests.get(url).text
            soup = BeautifulSoup(response, 'html.parser')
            for a in soup.select('td > span > a'):
                if '_' in a.text:
                    version = a.text.split('_')[-2]
                    break
            
            # cache package in assets dir
            filename = 'crowdsec-firewall-bouncer-iptables_'+version+'_amd64.deb'
            url = 'https://packagecloud.io/crowdsec/crowdsec/packages/debian/'+codename+'/'+filename+'/download.deb'
            if not os.path.exists(assets_path+filename):
                err = os.system('wget --content-disposition -P '+assets_path+' '+url)
                if err == 1:
                    print('error downloading packages:', url)
                    exit(1)
            
            # copy package to host
            files.put(
                src=assets_path+filename,
                dest='/root',
            )

            # install package
            host.run_shell_command('dpkg -i /root/'+filename+' && rm /root/'+filename)

        # update config
        files.put(
            src='./assets/crowdsec-acquis.yaml ',
            dest='/etc/crowdsec/acquis.yaml',
        )

        # restart service
        host.run_shell_command('systemctl restart crowdsec')

        # for docker services: add crowdsec blacklist to DOCKER-USER chain
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
        host.run_shell_command('systemctl restart crowdsec-firewall-bouncer')

    if service == 'postgres':
        host.run_shell_command('touch /containers/log/postgresql.log && mkdir -p /containers/postgres/init')

    if service == 'redis':
        host.run_shell_command('touch /containers/log/redis.log && mv /containers/build/redis/redis.rdb /containers/redis/redis.rdb && chmod 644 /containers/redis/redis.rdb')

    if service == 'webapp':
        host.run_shell_command('touch /containers/log/webapp.log && mv /containers/build/webapp/webapp.sql /containers/postgres/init && chown 70:70 /containers/postgres/init/webapp.sql')

    if service == 'torchserve':
        host.run_shell_command('touch /containers/log/access_log.log /containers/log/ts_log.log')

    if service == 'mattermost':
        host.run_shell_command('mkdir -p /containers/mattermost/config && mkdir -p /containers/mattermost/data && mkdir -p /containers/mattermost/logs && mkdir -p /containers/mattermost/plugins && mkdir -p /containers/mattermost/client/plugins && mkdir -p /containers/mattermost/bleve-indexes && chown -R 2000:2000 /containers/mattermost && mv /containers/build/mattermost/mattermost.sql /containers/postgres/init && chown 70:70 /containers/postgres/init/mattermost.sql && chmod +x /containers/build/mattermost/entrypoint.sh')

        files.put(
            src='./assets/mattermost-config.json',
            dest='/containers/mattermost/config/config.json',
        )
        host.run_shell_command('chown -R 2000:2000 /containers/mattermost/config/config.json')


# compile compose file

print('compile compose file')

with open(DOCKERFILES_PATH+'/'+TARGET_GROUP+'.yml', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('<< OVERLAY_IP >>', OVERLAY_IP)  # you can add all variables here

files.put(
    src=StringIO(content),
    dest=DOCKERFILES_TARGET_PATH+'/docker-compose.yml',
    force=True
)


# install traefik-kop

if 'traefik' not in SERVICES:

    REDIS_PWD = os.environ['REDIS_PWD']

    if not TRAEFIK_IP or not CURRENT_HOSTNAME or not REDIS_PWD:
        print('NOTICE: for traefik-kop, set hostname and traefik_ip in the inventory, as well as the REDIS_PWD environment variable.')
        exit(1)

    # get traefik overlay ip

    inv = importlib.import_module('inventory')
    for group in [getattr(inv, a) for a in dir(inv) if not a.startswith('_')]:
        if group[0][0] == TRAEFIK_IP:
            traefik_node = group
            break

    ssh.download(
         hostname: TRAEFIK_IP,
         filename: '$HOME/wgoverlay-ip',
         local_filename: '$HOME/traefik-wgoverlay-ip',
         port=22,
         user: traefik_node[0][1]['ssh_user'],
         ssh_keyscan=True
    )
    cmd_stdout = host.run_shell_command('cat $HOME/traefik-wgoverlay-ip')[1]
    TRAEFIK_OVERLAY_IP = cmd_stdout[2].split('/')[0].split()[-1]

    if not TRAEFIK_OVERLAY_IP:
        print('ABORTED: failed to look up overlay ip.')
        exit(1)

    # setup traefik-kop
    
    files.put(
        name='setup traefik-kop',
        src='./assets/'+ARCH+'/traefik-kop',
        dest='/usr/local/bin/traefik-kop',
    )

    host.run_shell_command('chmod +x /usr/local/bin/traefik-kop')

    with open('./assets/traefik-kop.service', 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('<< HOSTNAME >>', CURRENT_HOSTNAME).replace('<< TRAEFIK_IP >>', TRAEFIK_OVERLAY_IP).replace('<< REDIS_IP >>', TRAEFIK_OVERLAY_IP).replace('<< REDIS_PWD >>', REDIS_PWD).replace('<< CURRENT_IP >>', CURRENT_IP)

    files.put(
        src=StringIO(content),
        dest='/etc/systemd/system/traefik-kop.service',
        force=True
    )

    host.run_shell_command('systemctl daemon-reload')
    host.run_shell_command('systemctl enable traefik-kop')


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

