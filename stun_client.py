import logging
import os
import socket
import struct

logger = logging.getLogger(__name__)


def discover_public_coordinates(
    sock: socket.socket, stun_host: str = "stun.l.google.com", stun_port: int = 19302
) -> tuple[str, int]:
    """
    Queries a STUN server to find the public IP and port mapped to the provided socket.
    """
    # 1. Craft STUN Binding Request (RFC 5389)
    # Type (0x0001), Length (0), Magic Cookie (0x2112A442), Transaction ID (12 bytes)
    transaction_id = os.urandom(12)
    request = struct.pack("!HHI12s", 0x0001, 0, 0x2112A442, transaction_id)

    sock.settimeout(2.0)
    sock.sendto(request, (stun_host, stun_port))

    try:
        data, _ = sock.recvfrom(1024)
    except socket.timeout:
        raise RuntimeError("STUN server unreachable or blocked by firewall.")
    finally:
        # Clear the timeout so the socket returns to blocking/normal mode for the AudioEngine
        sock.settimeout(None)

    # 2. Parse the STUN Response
    # The first 20 bytes are the STUN header; attributes start immediately after.
    offset = 20
    while offset < len(data):
        attr_type, attr_length = struct.unpack_from("!HH", data, offset)
        offset += 4

        # 0x0020 is the attribute type for XOR-MAPPED-ADDRESS
        if attr_type == 0x0020:
            # Unpack the network family, port, and IP address integer
            _, port, ip_int = struct.unpack_from("!cxHI", data, offset)

            # Undo the XOR obfuscation required by the STUN protocol
            public_port = port ^ 0x2112
            public_ip = socket.inet_ntoa(struct.pack("!I", ip_int ^ 0x2112A442))

            logger.info(f"STUN discovery successful: {public_ip}:{public_port}")
            return public_ip, public_port

        offset += attr_length

    raise RuntimeError("STUN response did not contain public coordinates.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Quick local test
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_sock.bind(("0.0.0.0", 5001))

    try:
        ip, port = discover_public_coordinates(test_sock)
        print(f"\nSuccess! Your router maps local port 5001 to Public {ip}:{port}")
    finally:
        test_sock.close()
