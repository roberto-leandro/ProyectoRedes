import struct
import sys
import socket
import threading
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"

    def __init__(self, ip, port):
        super().__init__(ip, port)
        self.connections = {}

    def handle_connection(self, connection, address):
        print("Connected to:", address)
        while not self.stopper.is_set():
            self.connections[address] = connection
            try:
                message = self.receive_message(connection, address)
            except OSError:
                self.disconnect_address(address)
                print(f"Connection with address: {address} has disconnected")
                return
            self.decode_message(message, address)
        connection.close()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while not self.stopper.is_set():
            try:
                connection_handler = \
                    threading.Thread(target=self.handle_connection,
                                     args=(self.sock.accept()))
                connection_handler.start()
            except OSError:
                print("Main socket has closed")

    def disconnect_address(self, address):
        # Pop is atomic, therefore it doesn't need locks
        connection = self.connections.pop(address, None)
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

        self.reachability_table_lock.acquire()
        # Generate a new list without address
        self.reachability_table = \
            {key: value
             for key, value in self.reachability_table.items()
             if value[0] != address}
        self.reachability_table_lock.release()

        print(f"Disconnected from {address}")
        print(f"Deleting {address} table entries")

    def receive_message(self, connection, address):
        # Header is the first 2 bytes, it contains the length
        header = connection.recv(2)
        triplet_count = struct.unpack('!H', header)[0]

        if triplet_count == 0:
            self.disconnect_address(address)
            return []

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
        except:  # OS specific exception
            self.disconnect_address(address)
            print(f"Connection with {address} was closed.")

    def stop_node(self):
        print("Deleting node...")

        # Set this flag to false, stopping all loops
        self.stopper.set()

        # Close all the connections that had been opened
        for connection in self.connections.values():
            # send stop message
            print("Closing", connection)
            connection.sendall(struct.pack("!H", 0))
            connection.shutdown(socket.SHUT_RDWR)
            connection.close()
            print(connection, "closed")

        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass  # this is a forceful shutdown
        self.sock.close()
        print("Closed everything")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = TCPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()

sys.exit(0)
