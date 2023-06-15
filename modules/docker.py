
import os
import sys
import requests
from bs4 import BeautifulSoup
from pyinfra import host
from pyinfra.operations import files


# install docker

print('collecting files')

# find out debian codename
cmd_stdout = host.run_shell_command('lsb_release -a')[1]
for line in cmd_stdout:
    if line.startswith('Codename:'):
        codename = line.split()[1]
assets_path = 'assets/'+codename+'/'

# assert path
if not os.path.exists(assets_path):
    os.mkdir(assets_path)

# parse release directory listing
url = 'https://download.docker.com/linux/debian/dists/'+codename+'/pool/stable/amd64/'
response = requests.get(url).text
soup = BeautifulSoup(response, 'html.parser')

packages = ['containerd.io', 'docker-ce', 'docker-ce-cli', 'docker-compose-plugin']
selected_packages = {}
for a in soup.select('pre > a'):
    if '_' in a.text:
        name, version, _ = a.text.split('_')
        if name in packages:
            if name in selected_packages.keys():
                vv = version.split('.')
                vv_pre = selected_packages[name].split('_')[1].split('.')
                if int(vv[0]) >= int(vv_pre[0]) and int(vv[1]) >= int(vv_pre[1]):  # compare maj and min version numbers
                    selected_packages[name] = a.text  # save latest version
            else:
                selected_packages[name] = a.text

# assert we found all packages
if not all(p in selected_packages.keys() for p in packages):
    print('error finding docker packages')
    exit(1)

# cache packages in assets dir
for filename in selected_packages.values():
    if not os.path.exists(assets_path+filename):
        err = os.system('wget -P '+assets_path+' '+url+filename)
        if err == 1:
            print('error downloading packages:', url+filename)
            exit(1)

# copy packages to host
files.sync(
    name='uploading files',
    src=assets_path,
    dest='/root',
    add_deploy_dir=False
)

# install packages
host.run_shell_command('dpkg -i /root/*.deb && rm /root/*.deb')
