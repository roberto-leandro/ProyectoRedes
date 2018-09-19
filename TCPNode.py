import struct
import sys
import socket
import threading
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_STREAM
    NODE_TYPE_STRING = "[PseudoBGP Node]"

    def handle_connection(self, connection):
        while True:
            try:
                message = self.receive_message(connection)
                self.decode_message(message)

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
            connection, address = self.sock.accept()
            print(f"CONNECTED WITH {address}")
            connection_listener = \
                threading.Thread(
                    target=self.handle_connection,
                    args=(connection,))
            connection_listener.start()

    def receive_message(self, connection):
        # Header is the first 2 bytes, it contains the length
        header = connection.recv(2)
        triplet_count = struct.unpack('!H', header)[0]
        print(f"RECEIVED A MESSAGE WITH {triplet_count} TRIPLETS.")
        return connection.recv(self.TRIPLET_SIZE*triplet_count)

    def send_message(self, ip, port, message):
        print(f"SENDING {len(message)} BYTES TO {ip}:{port}")
        address = (ip, port)
        if address in self.connections:
            destination_socket = self.connections[address]
        else:
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect(address)
            self.connections[address] = destination_socket

        try:
            destination_socket.sendall(message)
        except BrokenPipeError:
            self.connections[address].close()
            del self.connections[address]
            print(f"Connection with {address} closed.")

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
    node.start_node()
