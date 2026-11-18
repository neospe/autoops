
WESHER_VERSION = v0.2.6
GARAGE_VERSION = v2.5.0
TRAEFIK_KOP_VERSION = v0.21.0

PYINFRA = pyinfra
LIMIT = $(if $(GROUP),--limit "$(GROUP)")
SHA256 = $(shell command -v sha256sum || echo shasum -a 256)

nodes:
	$(PYINFRA) inventory.py modules/basic.py $(LIMIT)
	$(PYINFRA) inventory.py modules/docker.py $(LIMIT)
	FIRST_IP=$(FIRST_IP) $(PYINFRA) inventory.py modules/wesher.py $(LIMIT)
	FIRST_IP=$(FIRST_IP) $(PYINFRA) inventory.py modules/garage.py $(LIMIT)
	FIRST_IP=$(FIRST_IP) $(PYINFRA) inventory.py modules/garage-layout.py $(LIMIT)

services:
	DOCKERFILES_PATH=$(DOCKERFILES_PATH) $(PYINFRA) inventory.py modules/services.py $(LIMIT)

services-up:
	$(PYINFRA) inventory.py modules/services-up.py $(LIMIT)

deploy:
	SERVICE=$(SERVICE) $(PYINFRA) inventory.py modules/deploy.py $(LIMIT)

care:
	$(PYINFRA) inventory.py modules/care.py $(LIMIT)

# prebuilt binaries for assets/x86_64 and assets/aarch64, checked against assets/SHA256SUMS
# (curl honours ALL_PROXY, e.g. ALL_PROXY=socks5h://127.0.0.1:9050 make assets)
assets:
	for arch in x86_64:amd64 aarch64:arm64; do \
		a=$${arch%:*}; g=$${arch#*:}; mkdir -p assets/$$a; \
		curl -fsSL --retry 5 --retry-all-errors -C - -o assets/$$a/wesher https://github.com/costela/wesher/releases/download/$(WESHER_VERSION)/wesher-$$g && \
		curl -fsSL --retry 5 --retry-all-errors -C - -o assets/$$a/garage https://garagehq.deuxfleurs.fr/_releases/$(GARAGE_VERSION)/$$a-unknown-linux-musl/garage && \
		curl -fsSL --retry 5 --retry-all-errors -C - -o assets/$$a/traefik-kop.tar.gz https://github.com/jittering/traefik-kop/releases/download/$(TRAEFIK_KOP_VERSION)/traefik-kop_linux_$$g.tar.gz || exit 1; \
	done
	cd assets && $(SHA256) -c SHA256SUMS
	for a in x86_64 aarch64; do tar -xzf assets/$$a/traefik-kop.tar.gz -C assets/$$a traefik-kop && rm assets/$$a/traefik-kop.tar.gz; done
	chmod +x assets/*/wesher assets/*/garage assets/*/traefik-kop

check:
	python3 -m py_compile modules/*.py

.PHONY: nodes services services-up deploy care assets check
