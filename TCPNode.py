import threading
import readline
import socket
import sys


class TCPNode:

    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.routing_table = {}
        self.reachability_table = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("[PseudoBGP Node]")
        print("Address:", ip)
        print("Port:", port)

    def start_node(self):
        """ Create two new threads
        one to handle console commands and
        another to listen to incoming connections. """
        print("START EXECUTED")
        connection_handler_thread =\
            threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while True:
            conn, addr = self.sock.accept()
            print(f"CONNECTED WITH {addr}")
            with conn:
                data = conn.recv(1024)
                if not data:
                    continue
                print("[NODE] ", repr(data))

        self.sock.close

    def send_message(self, ip, port, message):
        print(f"[NODE] SENDING {message} TO {ip}:{port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host_socket:
            host_socket.connect((ip, port))
            host_socket.sendall(message.encode())

    def handle_console_commands(self):
        while True:
            command = input("[NODE] Enter your command...\n> ")
            command = command.strip().split(" ")

            if len(command) != 4:
                print("Unrecognized command, try again.")

            if command[0] == "sendMessage":
                self.send_message(ip=command[1],
                                  port=int(command[2]),
                                  message=command[3])
            else:
                print("Unrecognized command, try again.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = TCPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()
