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
        self.handle_console_commands()git clone

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))

    def handle_console_commands(self):
        while True:
            command = input("Enter your command...\n").strip()
            print(command)

