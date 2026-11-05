"""Setup-only local veth pair: both ends in the disposable network-none namespace."""
import json
import os
from pathlib import Path
import socket
import struct


def attr(kind: int, data: bytes) -> bytes:
    size = 4 + len(data)
    return struct.pack('=HH', size, kind) + data + bytes((-size) % 4)


def send(kind: int, body: bytes, flags: int = 0x605) -> None:
    # REQUEST|ACK|CREATE|EXCL for creation; REQUEST|ACK for an existing link.
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE) as net:
        net.settimeout(5)
        net.bind((0, 0))
        net.send(struct.pack('=IHHII', 16 + len(body), kind, flags, 1, 0) + body)
        reply = net.recv(65536)
        assert len(reply) >= 20 and struct.unpack_from('=H', reply, 4)[0] == 2
        error = struct.unpack_from('=i', reply, 16)[0]
        if error:
            raise OSError(-error, os.strerror(-error))


names = {name for _, name in socket.if_nameindex()}
if names == {'lo'}:
    empty_link = struct.pack('=BBHiII', 0, 0, 0, 0, 0, 0)
    peer = attr(1, empty_link + attr(3, b'wp2c-peer\0'))
    info = attr(18, attr(1, b'veth\0') + attr(2, peer))
    send(16, empty_link + attr(3, b'wp2c-local\0') + info)
    for name in ('wp2c-local', 'wp2c-peer'):
        send(16, struct.pack('=BBHiII', 0, 0, 0, socket.if_nametoindex(name), 1, 1), 5)
    address = socket.inet_aton('192.0.2.254')  # RFC5737, this namespace's own /32 only.
    send(20, struct.pack('=BBBBI', socket.AF_INET, 32, 0, 253, socket.if_nametoindex('wp2c-local'))
         + attr(1, address) + attr(2, address) + attr(8, struct.pack('=I', 0x200)))  # NOPREFIXROUTE
assert {name for _, name in socket.if_nameindex()} == {'lo', 'wp2c-local', 'wp2c-peer'}
for own, peer in (('wp2c-local', 'wp2c-peer'), ('wp2c-peer', 'wp2c-local')):
    assert int(Path('/sys/class/net', own, 'iflink').read_text()) == socket.if_nametoindex(peer)
assert len(Path('/proc/net/route').read_text().splitlines()) == 1
with socket.socket() as probe:
    probe.settimeout(0.2)
    assert probe.connect_ex(('198.51.100.1', 1883)) != 0
print(json.dumps({'qualification': 'PASS_ISOLATED', 'local_test_link': 'both ends in same namespace',
                  'interfaces': socket.if_nameindex(), 'ipv4_routes': [], 'external_transport': 'DENIED'}))
