#!/usr/bin/env python3
"""Aray Solucoes: provisiona Ubuntu Server LTS + Samba no VirtualBox (Windows).
Requer Python 3.10+, VirtualBox 7.x e pycdlib (instalado automaticamente se ausente).
"""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

VERSION = '26.04'
RELEASE = '26.04.1'
BASE = f'https://cloud-images.ubuntu.com/releases/{VERSION}/release/'
IMAGE = f'ubuntu-{VERSION}-server-cloudimg-amd64.vmdk'
VM_NAME = 'Aray-Samba-Server'
USER = 'aray'
HOSTNAME = 'aray-samba'
RAM_MB = 4096
CPUS = 2
DISK_GB = 30


def log(message):
    print(f'\n[ARAY] {message}', flush=True)


def run(*args, check=True, capture=False):
    args = [str(x) for x in args]
    result = subprocess.run(args, text=True, encoding='utf-8', errors='replace',
                            capture_output=capture, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'Falha ({result.returncode}): {args[0]} {args[1] if len(args)>1 else ""}\n{detail}')
    return result


def locate_vbox():
    options = [shutil.which('VBoxManage.exe'), shutil.which('VBoxManage'),
               os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Oracle', 'VirtualBox', 'VBoxManage.exe')]
    return next((p for p in options if p and Path(p).is_file()), None)


def interfaces(vbox):
    """Somente interfaces bridge reconhecidas pelo proprio VirtualBox."""
    result = run(vbox, 'list', 'bridgedifs', capture=True)
    # VBoxManage retorna blocos com "Name: ..."; evita regex e problemas de escape.
    names = [line.split(':', 1)[1].strip() for line in result.stdout.splitlines()
             if line.startswith('Name:') and line.split(':', 1)[1].strip()]
    if not names:
        raise RuntimeError(
            'VirtualBox nao encontrou interfaces bridge. Verifique o driver '
            'VirtualBox NDIS6 Bridged Networking Driver nas propriedades '
            'do adaptador do Windows e execute VBoxManage list bridgedifs.')
    return names


def download(url, path):
    if path.exists():
        log(f'Arquivo existente: {path.name}')
        return
    tmp = path.with_suffix(path.suffix + '.part')
    log(f'Baixando {url}')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'AraySambaProvisioner/1.0'}), timeout=60) as src, tmp.open('wb') as out:
        length = int(src.headers.get('Content-Length') or 0)
        total = 0
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
            if length:
                print(f'\r    {total/1024**2:.0f} / {length/1024**2:.0f} MiB ({total/length:.0%})', end='', flush=True)
    print()
    tmp.replace(path)


def checksum(path, checksums):
    entries = (line.strip().split(maxsplit=1) for line in checksums.splitlines())
    expected = next((parts[0].lower() for parts in entries
                     if len(parts) == 2 and len(parts[0]) == 64
                     and all(c in '0123456789abcdefABCDEF' for c in parts[0])
                     and parts[1].lstrip('*').removeprefix('./') == path.name), None)
    if not expected:
        raise RuntimeError(f'Arquivo {path.name} nao consta no manifesto SHA256 oficial. Verifique a versao da imagem.')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise RuntimeError('SHA256 divergente. O arquivo local pode estar incompleto ou a imagem oficial pode ter sido atualizada. Renomeie o VMDK local para backup e baixe novamente; nao desative a verificacao.')
    log('Imagem verificada com SHA256 oficial.')


def yaml_quote(value):
    return "'" + value.replace("'", "''") + "'"


def seed_iso(folder, password):
    try:
        import pycdlib
    except ImportError:
        log('Instalando dependencia pycdlib...')
        # Instalar no interpretador atual. Em alguns Windows, --user instala
        # em diretorio nao presente no sys.path da sessao ja iniciada.
        import site
        user_site = site.getusersitepackages()
        run(sys.executable, '-m', 'pip', 'install', '--user', 'pycdlib')
        if user_site not in sys.path:
            site.addsitedir(user_site)
        import importlib
        importlib.invalidate_caches()
        try:
            pycdlib = importlib.import_module('pycdlib')
        except ImportError as exc:
            raise RuntimeError(
                'pycdlib foi instalado, mas nao ficou acessivel no Python atual. '
                'Execute: py -m pip show pycdlib; py -m site; '
                'ou instale em um ambiente virtual (venv).'
            ) from exc

    # Cloud-init NoCloud; senha armazenada em texto claro no ISO de seed.
    # O arquivo ISO permanece LOCAL. Proteja o acesso a pasta e exclua apos provisionar.
    samba_password = password.replace("'", "'\\''")
    script = f'''#!/bin/bash
set -euo pipefail
id {USER} >/dev/null
mkdir -p /srv/samba/empresa
chown {USER}:{USER} /srv/samba/empresa
chmod 0700 /srv/samba/empresa
cat >> /etc/samba/smb.conf <<'SAMBA_CONFIG'

[Empresa]
    comment = Compartilhamento Aray
    path = /srv/samba/empresa
    browseable = yes
    read only = no
    guest ok = no
    valid users = {USER}
    create mask = 0600
    directory mask = 0700
SAMBA_CONFIG
printf '%s\\n%s\\n' '{samba_password}' '{samba_password}' | smbpasswd -s -a {USER}
smbpasswd -e {USER}
testparm -s >/dev/null
systemctl enable --now smbd
systemctl restart smbd
ufw allow from 192.168.0.0/16 to any port 445 proto tcp || true
ufw allow from 10.0.0.0/8 to any port 445 proto tcp || true
ufw allow from 172.16.0.0/12 to any port 445 proto tcp || true
ufw allow 22/tcp || true
printf '%s\\n' 'CONFIGURACAO_ARAY_SAMBA_CONCLUIDA' > /var/log/aray-samba-status
'''
    user_data = f'''#cloud-config
hostname: {HOSTNAME}
manage_etc_hosts: true
users:
  - default
  - name: {USER}
    gecos: Administrador Aray
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) ALL
    lock_passwd: false
ssh_pwauth: true
chpasswd:
  expire: false
  users:
    - name: {USER}
      password: {yaml_quote(password)}
      type: text
package_update: true
package_upgrade: true
packages:
  - samba
  - openssh-server
write_files:
  - path: /usr/local/sbin/aray-configure-samba.sh
    permissions: '0700'
    owner: root:root
    content: |
'''+''.join('      '+line+'\n' for line in script.rstrip('\n').splitlines())+'''runcmd:
  - [bash, /usr/local/sbin/aray-configure-samba.sh]
final_message: 'Ubuntu Server + Samba finalizado. Confira /var/log/aray-samba-status.'
'''
    userdata = folder / 'user-data'
    metadata = folder / 'meta-data'
    userdata.write_text(user_data, encoding='utf-8')
    metadata.write_text(f'instance-id: {VM_NAME}-001\nlocal-hostname: {HOSTNAME}\n', encoding='utf-8')
    iso_path = folder / 'cloud-init-seed.iso'
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, vol_ident='CIDATA', joliet=3, rock_ridge='1.09')
    iso.add_file(str(userdata), iso_path='/USERDATA.;1', joliet_path='/user-data', rr_name='user-data')
    iso.add_file(str(metadata), iso_path='/METADATA.;1', joliet_path='/meta-data', rr_name='meta-data')
    iso.write(str(iso_path))
    iso.close()
    # Nao preservar user-data avulso; ISO ainda contem segredo ate sua remocao.
    userdata.unlink()
    metadata.unlink()
    return iso_path


def backup_existing_vm(vbox, folder):
    """Desregistra a VM antiga SEM apagar arquivos e arquiva seu diretorio."""
    known = run(vbox, 'list', 'vms', capture=True).stdout
    if not re.search(r'^"' + re.escape(VM_NAME) + r'"\s', known, re.M):
        raise RuntimeError('Nao existe VM registrada para reconstruir.')
    if not folder.is_dir():
        raise RuntimeError('Diretorio antigo da VM nao encontrado; nada foi alterado.')
    state = run(vbox, 'showvminfo', VM_NAME, '--machinereadable', capture=True).stdout
    if 'VMState="running"' in state or 'VMState="paused"' in state:
        log('Solicitando desligamento da VM antiga...')
        run(vbox, 'controlvm', VM_NAME, 'acpipowerbutton', check=False)
        for _ in range(20):
            time.sleep(1)
            state = run(vbox, 'showvminfo', VM_NAME, '--machinereadable', capture=True).stdout
            if 'VMState="poweroff"' in state or 'VMState="aborted"' in state:
                break
        else:
            log('Desligamento normal nao respondeu; desligando a VM para preservar o disco como backup.')
            run(vbox, 'controlvm', VM_NAME, 'poweroff')
    elif 'VMState="saved"' in state:
        raise RuntimeError('VM em estado salvo. Descarte o estado salvo no VirtualBox antes de reconstruir.')
    log('Desregistrando VM antiga SEM excluir seu disco...')
    run(vbox, 'unregistervm', VM_NAME)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = folder.with_name(f'{VM_NAME}-backup-{stamp}')
    if backup.exists():
        raise RuntimeError(f'Backup ja existe: {backup}; arquivos antigos permanecem no local.')
    folder.rename(backup)
    log(f'Backup preservado em: {backup}')
    return backup


def clone_vmdk(vbox, image, disk):
    """Corrige apenas registro obsoleto da imagem-fonte, sem excluir dados."""
    result = run(vbox, 'clonemedium', 'disk', str(image), str(disk), '--format', 'VDI', check=False, capture=True)
    if result.returncode == 0:
        return
    detail = (result.stderr or '') + (result.stdout or '')
    stale = re.search(r'stored in the media registry', detail, re.I)
    uuid = re.search(r'value \\{([0-9a-fA-F-]{36})\\} stored in the media registry', detail)
    if not stale or not uuid:
        raise RuntimeError('Falha ao clonar disco: ' + detail)
    log('Registro obsoleto do VMDK detectado. Removendo apenas a referencia antiga do VirtualBox...')
    # closemedium sem --delete: nunca exclui a imagem ou o backup.
    close = run(vbox, 'closemedium', 'disk', uuid.group(1), check=False, capture=True)
    if close.returncode:
        raise RuntimeError('Nao foi possivel liberar registro do VMDK. Nenhum disco foi excluido. ' + (close.stderr or close.stdout or ''))
    run(vbox, 'clonemedium', 'disk', str(image), str(disk), '--format', 'VDI')


def resume_incomplete(vbox):
    """Retoma VM com controlador criado e disco ainda nao conectado."""
    folder = Path.home() / 'VirtualBox VMs' / VM_NAME
    image = folder / IMAGE
    seed = folder / 'cloud-init-seed.iso'
    disk = folder / 'ubuntu-server.vdi'
    if not image.is_file() or not seed.is_file():
        raise RuntimeError('Arquivos de origem ou seed ausentes. Reconstrucao nao pode ser retomada.')
    info = run(vbox, 'showvminfo', VM_NAME, '--machinereadable', capture=True).stdout
    if 'VMState="poweroff"' not in info and 'VMState="aborted"' not in info:
        raise RuntimeError('A VM precisa estar desligada para retomar.')
    if 'SATA-0-0=' in info and not ('SATA-0-0="none"' in info):
        raise RuntimeError('A VM ja possui disco conectado. Nada foi alterado.')
    log('Retomando a VM parcial sem reconstruir ou alterar o backup...')
    if disk.exists():
        raise RuntimeError(f'Disco parcial existente: {disk}. Nao sera sobrescrito automaticamente.')
    clone_vmdk(vbox, image, disk)
    run(vbox, 'modifymedium', 'disk', str(disk), '--resize', str(DISK_GB * 1024))
    run(vbox, 'storageattach', VM_NAME, '--storagectl', 'SATA', '--port', '0', '--device', '0', '--type', 'hdd', '--medium', str(disk))
    run(vbox, 'storageattach', VM_NAME, '--storagectl', 'SATA', '--port', '1', '--device', '0', '--type', 'dvddrive', '--medium', str(seed))
    run(vbox, 'startvm', VM_NAME, '--type', 'gui')
    log('VM iniciada. Confira cloud-init e usuario apos o boot.')


def main():
    parser = argparse.ArgumentParser(description='Provisionar Samba no VirtualBox')
    parser.add_argument('--rebuild', action='store_true', help='Reconstruir VM, preservando a anterior em pasta backup')
    parser.add_argument('--resume', action='store_true', help='Retomar VM parcialmente criada apos falha no clone VMDK')
    options = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Este script foi desenvolvido para host Windows 10/11 com VirtualBox.')
    vbox = locate_vbox()
    if not vbox:
        raise RuntimeError('VBoxManage nao encontrado. Instale Oracle VirtualBox 7.x.')
    log('Verificando VirtualBox...')
    print(run(vbox, '--version', capture=True).stdout.strip())
    registered = run(vbox, 'list', 'vms', capture=True).stdout
    if options.resume:
        resume_incomplete(vbox)
        return
    exists = bool(re.search(r'^"' + re.escape(VM_NAME) + r'"\s', registered, re.M))
    if exists and not options.rebuild:
        raise RuntimeError(f'A VM {VM_NAME} ja existe. Use --rebuild para preservar backup e recriar.')
    if options.rebuild and not exists:
        raise RuntimeError('A VM nao existe; execute sem --rebuild.')

    adapters = interfaces(vbox)
    print('\nAdaptadores fisicos conectados (rede bridge):')
    for i, item in enumerate(adapters, 1):
        print(f' {i}. {item}')
    selected = input('Numero do adaptador para a rede local [1]: ').strip() or '1'
    if not selected.isdigit() or not 1 <= int(selected) <= len(adapters):
        raise RuntimeError('Adaptador invalido.')
    adapter = adapters[int(selected)-1]
    password = getpass.getpass(f'Senha para Linux/SSH/Samba ({USER}): ')
    if len(password) < 12 or "'" in password or '\n' in password or '\r' in password:
        raise RuntimeError('Use senha com 12+ caracteres, sem aspas simples ou quebras de linha.')
    if password != getpass.getpass('Repita a senha: '):
        raise RuntimeError('Senhas nao conferem.')

    folder = Path.home() / 'VirtualBox VMs' / VM_NAME
    if not options.rebuild:
        folder.mkdir(parents=True, exist_ok=True)
    image = folder / IMAGE
    download(BASE + IMAGE, image)
    log('Consultando somas SHA256 oficiais...')
    manifest = urllib.request.urlopen(BASE + 'SHA256SUMS', timeout=40).read().decode('utf-8')
    checksum(image, manifest)
    if options.rebuild:
        backup = backup_existing_vm(vbox, folder)
        folder.mkdir(parents=True, exist_ok=False)
        shutil.copy2(backup / IMAGE, image)
        log('Imagem Ubuntu reutilizada do backup.')
    seed = seed_iso(folder, password)
    log(f'Criando VM {VM_NAME} / 4GB RAM / 2 vCPU / bridge {adapter}')
    # A VM criada nao interfere em VMs existentes.
    run(vbox, 'createvm', '--name', VM_NAME, '--ostype', 'Ubuntu_64', '--basefolder', str(folder.parent), '--register')
    try:
        run(vbox, 'modifyvm', VM_NAME, '--memory', str(RAM_MB), '--cpus', str(CPUS),
            '--ioapic', 'on', '--firmware', 'efi', '--graphicscontroller', 'vmsvga',
            '--nic1', 'bridged', '--bridgeadapter1', adapter,
            '--nictype1', '82540EM', '--cableconnected1', 'on',
            '--boot1', 'disk', '--boot2', 'dvd', '--boot3', 'none', '--boot4', 'none')
        run(vbox, 'storagectl', VM_NAME, '--name', 'SATA', '--add', 'sata', '--controller', 'IntelAhci')
        disk = folder / 'ubuntu-server.vdi'
        log('Clonando imagem oficial para disco gravavel VDI...')
        clone_vmdk(vbox, image, disk)
        run(vbox, 'modifymedium', 'disk', str(disk), '--resize', str(DISK_GB * 1024))
        run(vbox, 'storageattach', VM_NAME, '--storagectl', 'SATA', '--port', '0', '--device', '0', '--type', 'hdd', '--medium', str(disk))
        run(vbox, 'storageattach', VM_NAME, '--storagectl', 'SATA', '--port', '1', '--device', '0', '--type', 'dvddrive', '--medium', str(seed))
        log('Abrindo VirtualBox e inicializando a VM...')
        gui = Path(vbox).parent / 'VirtualBox.exe'
        if gui.exists():
            subprocess.Popen([str(gui)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(vbox, 'startvm', VM_NAME, '--type', 'gui')
    except Exception:
        log('Falha durante a criacao. Os arquivos da VM foram preservados para diagnostico.')
        raise

    print(f'''\n{'='*65}
VM {VM_NAME} iniciada.
- Ubuntu Server {RELEASE} LTS (imagem cloud oficial)
- RAM: {RAM_MB} MB | CPU: {CPUS} | disco: {DISK_GB} GB
- Rede: bridge ({adapter}), IP obtido via DHCP do roteador
- Usuario: {USER}
- Samba: compartilhamento Empresa (autenticado)

O cloud-init instala e configura Samba automaticamente no primeiro boot.
A inicializacao pode incluir atualizacoes; confira pelo console da VM:
    sudo cloud-init status --wait
    sudo cat /var/log/aray-samba-status
    hostname -I

No Windows, acesse: \\\\<IP_DA_VM>\\Empresa
No terminal: ssh {USER}@<IP_DA_VM>

IMPORTANTE: O ISO cloud-init-seed.iso contem a senha em texto claro.
Depois de confirmar a configuracao, DESLIGUE a VM, remova o ISO
na configuracao de armazenamento do VirtualBox e apague esse ISO.
Guarde a senha com seguranca. SMB nao deve ser exposto a internet.
{'='*65}''')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, urllib.error.URLError) as exc:
        print(f'\nERRO: {exc}', file=sys.stderr)
        sys.exit(1)
