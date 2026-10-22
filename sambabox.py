#!/usr/bin/env python3
"""SambaBox: VirtualBox + Ubuntu cloud image + verificacao remota SSH/SMB."""
import getpass
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

VM_PREFIX = "Aray-Samba-Server"
VERSION = "26.04"
IMAGE = f"ubuntu-{VERSION}-server-cloudimg-amd64.vmdk"
BASE = f"https://cloud-images.ubuntu.com/releases/{VERSION}/release/"
VM_ROOT = Path.home() / "VirtualBox VMs"
CACHE = VM_ROOT / "SambaBox-cache"
USER = "aray"


def msg(s):
    print("[SambaBox]", s, flush=True)


def cmd(*args, ok=True):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if ok and p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return p


def vbox_path():
    candidates = [shutil.which("VBoxManage.exe"),
                  Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                  "Oracle/VirtualBox/VBoxManage.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("VBoxManage.exe nao encontrado.")


def ensure_module(name):
    try:
        return __import__(name)
    except ImportError:
        msg("Instalando dependencia Python: " + name)
        cmd(sys.executable, "-m", "pip", "install", "--user", name)
        import importlib
        import site
        site.addsitedir(site.getusersitepackages())
        importlib.invalidate_caches()
        return importlib.import_module(name)


def list_vms(vbox):
    out = cmd(vbox, "list", "vms").stdout
    names = re.findall(r'^"([^"]+)"\s+\{[a-fA-F0-9-]+\}', out, flags=re.M)
    return [name for name in names if "samba" in name.lower()]


def vm_state(vbox, name):
    result = cmd(vbox, "showvminfo", name, "--machinereadable")
    match = re.search(r'^VMState="([^"]+)"', result.stdout, flags=re.M)
    return match.group(1) if match else "unknown"


def choose_adapter(vbox):
    raw = cmd(vbox, "list", "bridgedifs").stdout
    blocks = re.split(r"\n\s*\n", raw)
    ranked = []
    for block in blocks:
        data = {}
        for line in block.splitlines():
            if ":" in line:
                k, value = line.split(":", 1)
                data[k.strip()] = value.strip()
        if not data.get("Name") or data.get("Status", "").lower() != "up":
            continue
        name = data["Name"]
        ip = data.get("IPAddress", "")
        score = (100 if data.get("MediumType", "").lower() == "ethernet" else 20)
        score += 15 if data.get("Wireless", "").lower() == "no" else 0
        try:
            score += 50 if ipaddress.ip_address(ip).is_private else 0
        except ValueError:
            pass
        ranked.append((score, name, ip))
    if not ranked:
        raise RuntimeError("Nenhuma interface bridge ativa identificada pelo VirtualBox.")
    ranked.sort(reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        msg("Adaptadores equivalentes: " + ", ".join(row[1] for row in ranked))
        raise RuntimeError("Selecao automatica ambigua; desative interface nao utilizada.")
    msg(f"Interface selecionada: {ranked[0][1]} ({ranked[0][2]})")
    return ranked[0][1], ranked[0][2]


def get_image():
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / IMAGE
    if not path.exists():
        # Reutiliza a imagem anteriormente baixada sem mover arquivos de backup.
        others = sorted(VM_ROOT.glob("Aray-Samba-Server*/" + IMAGE))
        if others:
            msg("Reutilizando imagem local existente.")
            shutil.copy2(others[0], path)
        else:
            msg("Baixando imagem oficial do Ubuntu Server...")
            req = urllib.request.Request(BASE + IMAGE, headers={"User-Agent": "SambaBox/2"})
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(req, timeout=90) as source, tmp.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            tmp.replace(path)
    msg("Validando SHA-256 com manifesto oficial...")
    manifest = urllib.request.urlopen(BASE + "SHA256SUMS", timeout=40).read().decode()
    digest = next((row.split()[0] for row in manifest.splitlines()
                   if len(row.split()) == 2 and row.split()[1].lstrip("*").removeprefix("./") == IMAGE), None)
    if not digest:
        raise RuntimeError("Imagem nao encontrada no manifesto oficial SHA256SUMS.")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(part)
    if h.hexdigest().lower() != digest.lower():
        raise RuntimeError("SHA256 divergente. Imagem invalida; nada sera provisionado.")
    return path


def seed(folder, password, instance):
    pycdlib = ensure_module("pycdlib")
    # Senha alfanumerica aleatoria: evita divergencias por layout do teclado do console.
    userdata = f"""#cloud-config
hostname: aray-samba
manage_etc_hosts: true
users:
  - default
  - name: aray
    gecos: Aray Administrator
    groups: [adm, sudo]
    sudo: "ALL=(ALL) ALL"
    shell: /bin/bash
    lock_passwd: false
disable_root: false
ssh_pwauth: true
chpasswd:
  expire: false
  users:
    - name: root
      password: "{password}"
      type: text
    - name: aray
      password: "{password}"
      type: text
package_update: true
packages: [openssh-server, samba]
runcmd:
  - [systemctl, enable, --now, ssh]
  - [systemctl, enable, --now, smbd]
"""
    # Root continua bloqueado no SSH. O login root via console fica disponivel.
    metadata = f"instance-id: {instance}\nlocal-hostname: aray-samba\n"
    user_file, meta_file = folder / "user-data", folder / "meta-data"
    user_file.write_text(userdata, encoding="utf-8")
    meta_file.write_text(metadata, encoding="utf-8")
    iso_path = folder / "cloud-init-seed.iso"
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, vol_ident="CIDATA", joliet=3, rock_ridge="1.09")
    iso.add_file(str(user_file), iso_path="/USERDATA.;1", joliet_path="/user-data", rr_name="user-data")
    iso.add_file(str(meta_file), iso_path="/METADATA.;1", joliet_path="/meta-data", rr_name="meta-data")
    iso.write(str(iso_path))
    iso.close()
    user_file.unlink()
    meta_file.unlink()
    return iso_path


def clone(vbox, image, disk):
    outcome = cmd(vbox, "clonemedium", "disk", image, disk, "--format", "VDI", ok=False)
    if not outcome.returncode:
        return
    detail = (outcome.stderr or "") + (outcome.stdout or "")
    marker = " stored in the media registry"
    before, found, _ = detail.partition(marker)
    candidate = before.rsplit("value {", 1)[-1].split("}", 1)[0] if "value {" in before else ""
    if found:
        import uuid
        try:
            old = str(uuid.UUID(candidate))
        except ValueError:
            old = None
        if old:
            msg("Liberando registro VMDK obsoleto sem excluir imagem.")
            cmd(vbox, "closemedium", "disk", old)
            cmd(vbox, "clonemedium", "disk", image, disk, "--format", "VDI")
            return
    raise RuntimeError(detail)


def delete_vm(vbox, name):
    print("ATENCAO: esta acao exclui a VM e seus discos registrados.")
    if input(f"Digite EXCLUIR {name} para confirmar: ").strip() != f"EXCLUIR {name}":
        raise RuntimeError("Exclusao cancelada.")
    state = vm_state(vbox, name)
    if state == "running":
        msg("Solicitando desligamento ACPI...")
        cmd(vbox, "controlvm", name, "acpipowerbutton")
        for _ in range(25):
            if vm_state(vbox, name) == "poweroff":
                break
            time.sleep(1)
        if vm_state(vbox, name) != "poweroff":
            raise RuntimeError("VM nao desligou normalmente; exclusao cancelada.")
    cmd(vbox, "unregistervm", name, "--delete")
    msg("VM excluida. Backups independentes nao foram removidos.")


def mac_of(vbox, name):
    info = cmd(vbox, "showvminfo", name, "--machinereadable").stdout
    m = re.search(r'^macaddress1="([0-9A-Fa-f]{12})"', info, re.M)
    return m.group(1).lower() if m else None


def guest_ip(vbox, name, host_ip):
    # Prioriza MAC especifico da VM, sem confundir com outros dispositivos da LAN.
    mac = mac_of(vbox, name)
    if mac:
        raw = cmd("arp", "-a", ok=False).stdout
        for row in raw.splitlines():
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:-]{17})", row)
            if match and match.group(2).replace("-", "").replace(":", "").lower() == mac:
                return match.group(1)
    return None


def discover_ip(vbox, name, host_ip):
    found = guest_ip(vbox, name, host_ip)
    if found:
        return found
    try:
        subnet = ipaddress.ip_network(f"{host_ip}/24", strict=False)
        if not ipaddress.ip_address(host_ip).is_private:
            return None
    except ValueError:
        return None
    def probe(ip):
        try:
            with socket.create_connection((str(ip), 22), timeout=0.3):
                pass
        except OSError:
            pass
    with ThreadPoolExecutor(max_workers=48) as executor:
        list(executor.map(probe, (addr for addr in subnet.hosts() if str(addr) != host_ip)))
    return guest_ip(vbox, name, host_ip)


def ssh_connect(ip, password):
    paramiko = ensure_module("paramiko")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username=USER, password=password, timeout=5,
                   auth_timeout=5, banner_timeout=5, look_for_keys=False, allow_agent=False)
    return client


def provision_ssh(client, password):
    # Usa sudo com senha por stdin, nao concatena a senha em comandos do shell.
    script = """set -eu
id aray
id root
command -v sshd
command -v smbd
mkdir -p /srv/samba/empresa
chown aray:aray /srv/samba/empresa
chmod 0700 /srv/samba/empresa
if ! grep -q '^\\[Empresa\\]' /etc/samba/smb.conf; then
cat >> /etc/samba/smb.conf <<'SMBCONF'

[Empresa]
    path = /srv/samba/empresa
    browseable = yes
    read only = no
    guest ok = no
    valid users = aray
    create mask = 0600
    directory mask = 0700
SMBCONF
fi
testparm -s >/dev/null
systemctl enable --now smbd
systemctl enable --now ssh
systemctl is-active --quiet smbd
"""
    import base64
    encoded = base64.b64encode(script.encode()).decode()
    # sudo -S le senha uma vez; comando recebe somente payload base64 inerte.
    command = f"sudo -S -p '' bash -c 'echo {encoded} | base64 -d | bash'"
    channel = client.get_transport().open_session()
    channel.exec_command(command)
    channel.sendall((password + "\n").encode())
    channel.shutdown_write()
    exit_code = channel.recv_exit_status()
    output = channel.makefile("r").read()
    errors = channel.makefile_stderr("r").read()
    if exit_code:
        raise RuntimeError(f"Falha configurando Samba via SSH: {output[-800:]} {errors[-800:]}")
    # Define root e aray no Linux usando stdin; nao imprime credenciais.
    channel = client.get_transport().open_session()
    channel.exec_command("sudo -S -p '' chpasswd")
    channel.sendall((password + "\n" + "root:" + password + "\n" + "aray:" + password + "\n").encode())
    channel.shutdown_write()
    if channel.recv_exit_status():
        raise RuntimeError("Nao foi possivel aplicar as senhas Linux.")
    # Senha Samba pelo stdin, fora dos argumentos e logs.
    channel = client.get_transport().open_session()
    channel.exec_command("sudo -S -p '' smbpasswd -s -a aray")
    channel.sendall((password + "\n" + password + "\n" + password + "\n").encode())
    channel.shutdown_write()
    rc = channel.recv_exit_status()
    if rc:
        raise RuntimeError("Nao foi possivel definir senha Samba.")
    stdin, stdout, stderr = client.exec_command("systemctl is-active smbd && id aray")
    if stdout.channel.recv_exit_status():
        raise RuntimeError("Servico Samba nao esta ativo.")
    return stdout.read().decode().strip()


def wait_for_ssh(vbox, name, password, host_ip, max_seconds=600):
    msg("Aguardando IP da VM e autenticacao SSH automatica...")
    end = time.monotonic() + max_seconds
    while time.monotonic() < end:
        ip = discover_ip(vbox, name, host_ip)
        if ip:
            try:
                client = ssh_connect(ip, password)
                return ip, client
            except Exception:
                pass
        time.sleep(5)
    raise RuntimeError("Nao foi possivel autenticar por SSH. Verifique cloud-init no console. A VM foi preservada.")


def create(vbox, name, adapter, host_ip):
    image = get_image()
    password = secrets.token_urlsafe(18).replace("-", "A").replace("_", "b")
    folder = VM_ROOT / name
    if folder.exists():
        raise RuntimeError(f"Pasta {folder} ja existe. Nenhum dado sera sobrescrito.")
    folder.mkdir(parents=True)
    iso = seed(folder, password, f"sambabox-{secrets.token_hex(10)}")
    msg("Criando VM: " + name)
    cmd(vbox, "createvm", "--name", name, "--ostype", "Ubuntu_64",
        "--basefolder", VM_ROOT, "--register")
    try:
        cmd(vbox, "modifyvm", name, "--memory", "4096", "--cpus", "2",
            "--firmware", "efi", "--graphicscontroller", "vmsvga",
            "--nic1", "bridged", "--bridgeadapter1", adapter,
            "--cableconnected1", "on")
        cmd(vbox, "storagectl", name, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci")
        disk = folder / "ubuntu-server.vdi"
        clone(vbox, image, disk)
        cmd(vbox, "modifymedium", "disk", disk, "--resize", str(30 * 1024))
        cmd(vbox, "storageattach", name, "--storagectl", "SATA", "--port", "0",
            "--device", "0", "--type", "hdd", "--medium", disk)
        cmd(vbox, "storageattach", name, "--storagectl", "SATA", "--port", "1",
            "--device", "0", "--type", "dvddrive", "--medium", iso)
        cmd(vbox, "startvm", name, "--type", "headless")
        ip, client = wait_for_ssh(vbox, name, password, host_ip)
        with client:
            check = provision_ssh(client, password)
        with socket.create_connection((ip, 445), timeout=5):
            pass
        msg("SSH e SMB/445 verificados: " + check)
        print("\n" + "=" * 60)
        print("SAMBABOX - PROVISIONAMENTO CONCLUIDO")
        print("VM:", name, "| IP:", ip)
        print("Usuario SSH e console: aray")
        print("Usuario root: root (somente console; SSH root desativado)")
        print("Senha Linux/Samba para ambos:", password)
        print("SSH: ssh aray@" + ip)
        print("SMB: \\\\" + ip + "\\Empresa")
        print("IMPORTANTE: ISO cloud-init contem credenciais; desmonte e exclua apos verificar.")
        print("=" * 60)
    except Exception:
        msg("Instalacao incompleta. Disco e VM preservados para diagnostico.")
        # Exibe senha para possibilitar recuperacao mesmo com falha de SSH.
        print("Senha de provisionamento gerada para recuperacao:", password)
        raise


def main():
    if os.name != "nt":
        raise RuntimeError("Requer Windows e Oracle VirtualBox.")
    vbox = vbox_path()
    msg("VirtualBox " + cmd(vbox, "--version").stdout.strip())
    all_vms = list_vms(vbox)
    print("\nVMs Samba encontradas:")
    for index, item in enumerate(all_vms, 1):
        print(f"  {index}. {item} [{vm_state(vbox, item)}]")
    if not all_vms:
        print("  Nenhuma.")
    print("\n1 - Criar uma nova VM")
    print("2 - Reaproveitar uma VM existente (diagnostico SSH)")
    print("3 - Excluir uma VM e criar outra")
    option = input("Opcao [1]: ").strip() or "1"
    if option not in ("1", "2", "3"):
        raise RuntimeError("Opcao invalida.")
    if option in ("2", "3") and not all_vms:
        raise RuntimeError("Nenhuma VM Samba registrada.")
    selected = None
    if option in ("2", "3"):
        raw = input("Numero da VM [1]: ").strip() or "1"
        if not raw.isdigit() or int(raw) not in range(1, len(all_vms) + 1):
            raise RuntimeError("VM invalida.")
        selected = all_vms[int(raw) - 1]
    if option == "2":
        ip = input("IP da VM existente (se conhecido): ").strip()
        if not ip:
            raise RuntimeError("Reaproveitamento requer IP existente; nao altera credenciais.")
        password = getpass.getpass("Senha atual da VM: ")
        with ssh_connect(ip, password) as client:
            print(provision_ssh(client, password))
        msg("VM reaproveitada e Samba validado.")
        return
    adapter, host_ip = choose_adapter(vbox)
    if option == "3":
        delete_vm(vbox, selected)
        name = selected
    else:
        name = VM_PREFIX
        index = 2
        while name in all_vms or (VM_ROOT / name).exists():
            name = f"{VM_PREFIX}-{index}"
            index += 1
    create(vbox, name, adapter, host_ip)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, urllib.error.URLError) as exc:
        print("\nERRO:", exc, file=sys.stderr)
        sys.exit(1)
