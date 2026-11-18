
import os
import re
import sys
import subprocess
from pyinfra import host
from pyinfra.operations import files, server


# install docker

# pinned versions (tested); DOCKER_LATEST=1 takes the newest from download.docker.com instead
VERSIONS = {
    'containerd.io': '2.4.2',
    'docker-ce': '29.10.0',
    'docker-ce-cli': '29.10.0',
    'docker-buildx-plugin': '0.39.0',
    'docker-compose-plugin': '5.8.0',
}
LATEST = os.environ.get('DOCKER_LATEST')

print('collecting files')

# find out debian codename and architecture
cmd_stdout = host.run_shell_command('lsb_release -a')[1]
for line in cmd_stdout:
    if line.startswith('Codename:'):
        codename = line.split()[1]
ARCH = {'x86_64': 'amd64', 'aarch64': 'arm64'}[host.run_shell_command('uname -m')[1][0]]
assets_path = 'assets/'+codename+'/'

# assert path
if not os.path.exists(assets_path):
    os.mkdir(assets_path)

# parse release directory listing (curl honours ALL_PROXY)
url = 'https://download.docker.com/linux/debian/dists/'+codename+'/pool/stable/'+ARCH+'/'
response = subprocess.run(['curl', '-fsSL', url], capture_output=True, text=True).stdout

packages = list(VERSIONS)
selected_packages = {}
selected_versions = {}
for filename in set(re.findall(r'href="([^"/]+\.deb)"', response)):
    name, version, _ = filename.split('_')
    if name in packages and (LATEST or version.split(':')[-1].split('-')[0] == VERSIONS[name]):
        vv = [int(n) for n in re.findall(r'\d+', version.split('-')[0].split(':')[-1])]  # compare version numbers
        if name not in selected_packages or vv > selected_versions[name]:
            selected_packages[name] = filename  # save latest version
            selected_versions[name] = vv

# assert we found all packages
if not all(p in selected_packages.keys() for p in packages):
    print('error finding docker packages:', url)
    exit(1)

# cache packages in assets dir
for filename in selected_packages.values():
    if not os.path.exists(assets_path+filename):
        err = os.system('curl -fsSL -o '+assets_path+filename+' '+url+filename)
        if err != 0:
            print('error downloading packages:', url+filename)
            exit(1)

# copy packages to host
for filename in selected_packages.values():
    files.put(
        name='uploading '+filename,
        src=assets_path+filename,
        dest='/root/'+filename,
    )

# install packages (apt-get -f pulls in their dependencies from debian)
server.shell(
    name='installing packages',
    commands=['dpkg -i '+' '.join('/root/'+f for f in selected_packages.values())+' || apt-get -f -y install',
              'rm '+' '.join('/root/'+f for f in selected_packages.values())]
)
