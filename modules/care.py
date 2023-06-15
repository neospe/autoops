
import os, sys
from pyinfra import host
from pyinfra.operations import apt, files, server


# update system

apt.update(name='update apt repositories')
apt.upgrade(name='upgrade apt repositories')

