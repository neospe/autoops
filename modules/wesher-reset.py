
import sys
from pyinfra import host
from pyinfra.operations import server


# stop wesher and remove its state, so the wesher module builds a new overlay with a new cluster key
# (overlay ips come from the hostname and stay the same; run on all nodes, then the wesher module)

server.shell(
    name='reset wesher',
    commands=['systemctl stop wesher || true',
              'rm -f /var/lib/wesher/state.json',
              'ip link del wgoverlay 2>/dev/null || true']
)
