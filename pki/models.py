import textwrap
import mongoengine
import logging
import binascii
import OpenSSL
from bson import Binary
from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from datetime import datetime

logger = logging.getLogger(__name__)


class PrivateKeyField(mongoengine.fields.BaseField):
    """
    cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey
    """

    def to_mongo(self, value):
        pass

        return Binary(
            value.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(b"passphrase"),
            )
        )

    def to_python(self, value):
        pass

        if value is not None:
            return serialization.load_der_private_key(
                value,
                password=b"passphrase",
                backend=default_backend()
            )


class CertField(mongoengine.fields.BaseField):
    """
    cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey
    """

    def to_mongo(self, value):
        pass

        return Binary(
            value.public_bytes(serialization.Encoding.DER)
        )

    def to_python(self, value):
        pass

        if value is not None:
            return x509.load_der_x509_certificate(
                value,
                backend=default_backend()
            )


class Certificate(mongoengine.DynamicDocument):
    pid = mongoengine.ObjectIdField()
    created = mongoengine.DateTimeField(default=datetime.utcnow)
    key = PrivateKeyField()
    cert = CertField()

    @property
    def sha1(self):
        return ":".join(textwrap.wrap(binascii.hexlify(self.cert.fingerprint(hashes.SHA1())).decode(), 2)).upper()

    @property
    def sha256(self):
        return ":".join(textwrap.wrap(binascii.hexlify(self.cert.fingerprint(hashes.SHA256())).decode(), 2)).upper()

    @property
    def cn(self):
        for item in self.cert.subject:
            if item.oid == x509.NameOID.COMMON_NAME:
                return item.value

    @property
    def is_ca(self):
        for item in self.cert.extensions:
            if item.oid == x509.ExtensionOID.BASIC_CONSTRAINTS:
                return item.value._ca

    @property
    def is_server(self):
        for item in self.cert.extensions:
            if item.oid == x509.ExtensionOID.EXTENDED_KEY_USAGE:
                return x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in item.value

    @property
    def is_client(self):
        for item in self.cert.extensions:
            if item.oid == x509.ExtensionOID.EXTENDED_KEY_USAGE:
                return x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in item.value

    @property
    def pkcs12(self):
        """
        可以简单的认为 PKCS12 就是把 key, cert, ca certs 全部都打包到一起
        :return:
        """
        pkcs = OpenSSL.crypto.PKCS12()

        pkcs.set_privatekey(OpenSSL.crypto.load_privatekey(
            OpenSSL.crypto.FILETYPE_PEM,
            self.key.private_bytes(
                serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        ))

        pkcs.set_certificate(OpenSSL.crypto.load_certificate(
            OpenSSL.crypto.FILETYPE_PEM,
            self.cert.public_bytes(
                serialization.Encoding.PEM
            )
        ))

        ca_certificates = []
        crt = self
        while crt.pid:
            crt = Certificate.objects(id=crt.pid).get()
            ca_certificates.append(
                OpenSSL.crypto.load_certificate(
                    OpenSSL.crypto.FILETYPE_PEM,
                    crt.cert.public_bytes(
                        serialization.Encoding.PEM
                    )
                )
            )
        if len(ca_certificates):
            pkcs.set_ca_certificates(ca_certificates)

        return pkcs