import struct
import sys
import socket
import threading
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"

    def __init__(self, ip, port):
        super.__init__(ip, port):
        self.connections = {}

    def handle_connection(self, connection, address):
        print("Connected to:", address)
        while not self.stopper.is_set():
            try:
                message = self.receive_message(connection)
                self.decode_message(message)

            except Exception:
                # A socket disconnection may throw a non defined exception
                # this will catch all exceptions and blame it in a
                # socket disconnecting abruptly
                connection.close()
                print(f"The connection with {address} was closed.")
                print("worker thread died")
                return  # stop the thread not-so gracefully
        print("worker thread died")
        connection.close()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while not self.stopper.is_set():
            connection_handler = \
                threading.Thread(target=self.handle_connection,
                                 args=(self.sock.accept()))
            connection_handler.start()

        self.sock.close()
        print("maker of threads died")

    def receive_message(self, connection):
        # Header is the first 2 bytes, it contains the length
        header = connection.recv(2)
        triplet_count = struct.unpack('!H', header)[0]
        print(f"RECEIVED A MESSAGE WITH {triplet_count} TRIPLETS.")
        return connection.recv(self.TRIPLET_SIZE*triplet_count)

    def send_message(self, ip, port, message):
        address = (ip, port)
        print(f"SENDING {len(message)} BYTES TO {ip}:{port} to {address}")

        if address in self.connections:
            destination_socket = self.connections[address]
        else:
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.settimeout(self.SOCKET_TIMEOUT)
            destination_socket.connect(address)
            self.connections[address] = destination_socket

        try:
            destination_socket.sendall(message)
        except BrokenPipeError:
            self.connections[address].close()
            del self.connections[address]
            print(f"Connection with {address} was closed.")

    def stop_node(self):
        print("Deleting node...")

        # Set this flag to false, stopping all loops
        self.stopper.set()

        # Close all the connections that had been opened
        for connection in self.connections.values():
            connection.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = TCPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()

sys.exit(0)
