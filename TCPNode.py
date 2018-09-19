import struct
import sys
import socket
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"

    @staticmethod
    def listen_to_connection(connection):
        while True:
            try:
                TCPNode.receive_and_decode_message(connection)
            except Exception:
                # A socket disconnection may throw a non defined exception
                # this will catch all exceptions and blame it in a
                # socket disconnecting abruptly
                connection.close()
                print("A connection was closed")
                return  # stop the thread not-so gracefully

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while True:
            conn, addr = self.sock.accept()
            print(f"CONNECTED WITH {addr}")
            connection_listener = \
                threading.Thread(
                    target=self.listen_to_connection,
                    args=(conn,))
            connection_listener.start()

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
        print(f"SENDING {len(message)} BYTES TO {ip}:{port}")
        address = (ip, port)
        if address in self.connections:
            host_socket = self.connections[address]
        else:
            host_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            host_socket.connect(address)
            self.connections[address] = host_socket

        try:
            host_socket.sendall(message)
        except BrokenPipeError:
            self.connections[address].close()
            del self.connections[address]
            print(f"Conection with {address} closed")

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
