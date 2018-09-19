import struct
import sys
import socket
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while True:
            conn, address = self.sock.accept()
            print(f"CONNECTED WITH {address}")
            with conn:
                message = self.receive_message(conn)
                self.decode_message(message)

    def receive_message(self, connection):
        # Header is the first 2 bytes, it contains the length
        header = connection.recv(2)
        triplet_count = struct.unpack('!H', header)[0]
        print(f"RECEIVED A MESSAGE WITH {triplet_count} TRIPLETS.")
        return connection.recv(self.TRIPLET_SIZE*triplet_count)

    def send_message(self, ip, port, message):
        print(f"SENDING {len(message)} BYTES TO {ip}:{port}")
        with socket.socket(socket.AF_INET, self.SOCKET_TYPE) as destination_socket:
            destination_socket.connect((ip, port))
            destination_socket.sendall(message)

    def stop_node(self):
        # TODO
        # Close all open connections and terminate all threads
        sys.exit()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = TCPNode(sys.argv[1], int(sys.argv[2]))
    node.connections = {}
    node.start_node()
