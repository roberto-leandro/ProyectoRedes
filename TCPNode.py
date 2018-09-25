import struct
import sys
import socket
import threading
import selectors
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"
    SELECTOR_TIMEOUT = .5

    def __init__(self, ip, port):
        super().__init__(ip, port)
        self.connections = {}

    def handle_connection(self, connection, address):
        print(f"CONNECTION: New connection with {address}")
        self.connections[address] = connection
        connection.setblocking(False)
        connection_selector = selectors.DefaultSelector()
        connection_selector.register(connection, selectors.EVENT_READ)

        while not self.stopper.is_set():
            if address not in self.connections:
                # The socket is disconnected, close the thread
                break
            events = connection_selector.select(TCPNode.SELECTOR_TIMEOUT)
            for _ in events:
                message = self.receive_message(connection, address)
                self.decode_message(message, address)
        connection.close()

    def handle_incoming_connections(self):
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)
        self.sock.setblocking(False)
        main_selector = selectors.DefaultSelector()
        main_selector.register(self.sock, selectors.EVENT_READ)

        while not self.stopper.is_set():
            events = main_selector.select(TCPNode.SELECTOR_TIMEOUT)
            # Ignore (key, value) as we only have one way of handling
            for _ in events:
                if self.stopper.is_set():
                    # Closing sockets registers as an event
                    break
                connection_handler = \
                    threading.Thread(target=self.handle_connection,
                                     args=(self.sock.accept()))
                connection_handler.start()

    def disconnect_address(self, address):
        # Pop is atomic, therefore it doesn't need locks
        connection = self.connections.pop(address, None)
        if connection is not None:
            connection.close()

        self.reachability_table_lock.acquire()
        # Generate a new list without address
        self.reachability_table = \
            {key: value
             for key, value in self.reachability_table.items()
             if value[0] != address}
        self.reachability_table_lock.release()

        print(f"DISCONNECT: Disconnected from {address}")
        print(f"DISCONNECT: Deleting {address} table entries")

    def receive_message(self, connection, address):
        # Header is the first 2 bytes, it contains the length
        header = connection.recv(2)
        triplet_count = struct.unpack('!H', header)[0]

        if triplet_count == 0:
            self.disconnect_address(address)
            return []

        print(f"MESSAGE: Received message with {triplet_count} triplets.")
        return connection.recv(self.TRIPLET_SIZE*triplet_count)

    def send_message(self, ip, port, message):
        address = (ip, port)
        print(f"MESSAGE: Sending {len(message)} bytes to {ip}:{port}")

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
            print(f"ERROR: Connection with {address} was closed.")

    def stop_node(self):
        print("EXIT: Deleting node, all connections will close")

        # Set this flag to false, stopping all loops
        self.stopper.set()

        # Close all the connections that had been opened
        for address, connection in self.connections.items():
            # send stop message
            connection.sendall(struct.pack("!H", 0))
            connection.close()
            print(f"EXIT: Connection with {address} has closed")

        self.sock.close()
        print("EXIT: All connections are closed")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = TCPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()

sys.exit(0)
