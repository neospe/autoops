nodes:
	pyinfra inventory.py modules/basic.py --limit $(GROUP)
	pyinfra inventory.py modules/docker.py --limit $(GROUP)
	FIRST_IP=$(FIRST_IP) pyinfra inventory.py modules/wesher.py --limit $(GROUP)
	FIRST_IP=$(FIRST_IP) pyinfra inventory.py modules/garage.py --limit $(GROUP)

services:
	DOCKERFILES_PATH=$(DOCKERFILES_PATH) pyinfra inventory.py modules/services.py --limit $(GROUP)

services-up:
	pyinfra inventory.py modules/services-up.py --limit $(GROUP)

deploy:
	SERVICE=$(SERVICE) pyinfra inventory.py modules/deploy.py --limit $(GROUP)

care:
	pyinfra inventory.py modules/care.py --limit $(GROUP)
