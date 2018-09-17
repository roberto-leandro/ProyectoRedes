# Copyright CARACORACLE

import socket
import threading


class TCPNode:

    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.routing_table = {}
        self.reachability_table = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("CONSTRUCTOR EXECUTED")

    def start_node(self):
        """ Create two new threads, one to handle console commands and another to listen to incoming connections. """
        print("START EXECUTED")
        connection_handler_thread = threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while True:
            conn, addr = self.sock.accept()
            print('CONNECTED WITH ', conn, ':', addr)
            with conn:
                data = conn.recv(1024)
                if not data:
                    continue
                print("[NODE] "+repr(data))

        self.sock.close

    def send_message(self, ip, port, message):
        print("[NODE] SENDING ", message, " TO ", ip, ":", port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host_socket:
            host_socket.connect((ip, port))
            host_socket.sendall(b'Hello, world')

    def handle_console_commands(self):
        while True:
            command = input("[NODE] Enter your command...\n").strip().split(" ")
            if command[0] == "sendMessage":
                self.send_message(ip=command[1], port=int(command[2]), message=command[3])

