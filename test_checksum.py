"""Testes locais do parser SHA256SUMS do SambaBox (stdlib unittest)."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from aray_samba_virtualbox import checksum


class ChecksumTests(unittest.TestCase):
    def test_manifesto_formato_texto(self):
        with tempfile.TemporaryDirectory() as root:
            image = Path(root) / "ubuntu-26.04-server-cloudimg-amd64.vmdk"
            image.write_bytes(b"imagem de teste")
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            checksum(image, f"{digest}  {image.name}\n")

    def test_manifesto_formato_binario(self):
        with tempfile.TemporaryDirectory() as root:
            image = Path(root) / "ubuntu-26.04-server-cloudimg-amd64.vmdk"
            image.write_bytes(b"imagem de teste")
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            checksum(image, f"{digest} *{image.name}\n")

    def test_digest_incorreto(self):
        with tempfile.TemporaryDirectory() as root:
            image = Path(root) / "ubuntu-26.04-server-cloudimg-amd64.vmdk"
            image.write_bytes(b"imagem de teste")
            with self.assertRaises(RuntimeError):
                checksum(image, f"{'0'*64}  {image.name}\n")


if __name__ == "__main__":
    unittest.main()
