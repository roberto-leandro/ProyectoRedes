import struct
import socket
import sys
from AbstractNode import AbstractNode


class UDPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_DGRAM
    NODE_TYPE_STRING = "[IntAS Node]"
    BUFFER_SIZE = 2048  # Will be used when reading from a socket

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))

        while True:
            message = self.receive_message(self.sock)
            self.decode_message(message)

    def receive_message(self, connection):
        # Read enough bytes for the message, a standard packet does not exceed 1500 bytes
        message, address = connection.recvfrom(self.BUFFER_SIZE)
        print(f"CONNECTED WITH {address}")

        # Get the header, located in the first 2 bytes
        triplet_count = struct.unpack('!H', message[0:2])[0]
        print(f"RECEIVED A MESSAGE WITH {triplet_count} TRIPLETS.")

        # Return a buffer with only the triplets, omitting the header
        return message[2:]

    def send_message(self, ip, port, message):
        print(f"SENDING {len(message)} BYTES TO {ip}:{port}")
        self.sock.sendto(message, (ip, port))

    def stop_node(self):
        # TODO
        # Close open connection and terminate all threads
        sys.exit()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = UDPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()
