
# pyinfra inventory: copy to ./inventory.py and fill in your hosts.
# every group is a list of (host, data) tuples; services.py compiles DOCKERFILES_PATH/<group>.yml for its hosts,
# so if you have pets rather than cattle, give every host its own group.

bastion = [
    ('203.0.113.10', {
        'ssh_user': 'root',
        'ssh_port': 22,
        'ssh_key': '~/.ssh/id_ed25519',
        'hostname': 'bastion',          # system and overlay hostname
        'zone': 'dc1',                  # garage replication zone
        'services': ['traefik', 'redis'],
    }),
]

worker = [
    ('203.0.113.20', {
        'ssh_user': 'root',
        'ssh_port': 22,
        'ssh_key': '~/.ssh/id_ed25519',
        'hostname': 'worker',
        'zone': 'dc2',
        'services': ['whoami'],
        'traefik_host': '203.0.113.10',  # registers its services with traefik via traefik-kop; a list for several bastions
    }),
]

# a node behind NAT (needs the custom wesher build, see README):
#   ('192.168.1.10', {..., 'behind_nat': True, 'public_ip': '198.51.100.5'})   # or 'public_dns': 'home.example.org'
